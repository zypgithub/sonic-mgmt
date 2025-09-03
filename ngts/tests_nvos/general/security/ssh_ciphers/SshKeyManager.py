import re
import tempfile
import allure
import subprocess
import os
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.SecuritySshTool import SecuritySshTool
from ngts.nvos_tools.system.System import System
import logging
from ngts.tools.test_utils import allure_utils as allure


class SshKeyManager:
    def __init__(self, server_engine):
        self.server_engine = server_engine
        self.keys_dir = tempfile.mkdtemp(prefix='ssh_keys_')
        self.keys = dict()
        self.ca_keys = []

    def get_key(self, key: str):
        return self.keys[key]

    def get_key_path(self, pubkey: str):
        return f'{self.keys_dir}/id_{self.keys[pubkey]}'

    def clean_keys(self):
        with allure.step(f'Clean trusted CA keys'):
            while self.ca_keys:
                System().ssh_server.trusted_ca_keys.unset(op_param=self.ca_keys.pop(), apply=False, ask_for_confirmation='-y')
        with allure.step(f'Clean keys'):
            while self.keys:
                pubkey, key_id = self.keys.popitem()
                key_path = f'{self.keys_dir}/id_{key_id}'
                if 'cert' not in pubkey:
                    try:
                        SecuritySshTool.rm_auth_keypair(key_path)
                    except Exception as e:
                        logging.warning(f'Failed to remove key: {e}')

        with allure.step(f'Remove keys directory'):
            try:
                subprocess.run(f'sudo rm -rf {self.keys_dir}'.split(' '))
                assert not os.path.exists(self.keys_dir), f'Temporary keys directory {self.keys_dir} still exists'
            except Exception as e:
                logging.warning(f'Failed to cleanup temporary keys: {e}')

    def generate_key_and_upload_to_server(self, pubkey: str):
        with allure.step(f'Generate keys for {pubkey}'):
            key_type, key_bits, cert = self.extract_key_info_single_regex(pubkey)
            key_id = f'{key_type}_{key_bits}'
            base_key_path = f'{self.keys_dir}/id_{key_id}'
            if key_id not in self.keys.values():
                with allure.step(f'Generate base key for {key_type} {key_bits} bits'):
                    SecuritySshTool.generate_auth_keypair(
                        key_type=key_type,
                        dst_path=base_key_path,
                        num_bits=key_bits
                    )
                with allure.step(f'Upload public key for {key_id}'):
                    SecuritySshTool.upload_auth_key_to_server(key_path=f'{base_key_path}.pub', server_engine=self.server_engine)
            self.keys[pubkey] = key_id

    def sign_certificate_key(self, pubkey: str, username: str):
        key_id = self.keys.get(pubkey)
        key_path = f'{self.keys_dir}/id_{key_id}'
        with open(f'{key_path}.pub', 'r') as f:
            key_content = f.read().strip().split()
            with allure.step(f'add trusted ca key {key_content[0]} {key_content[1][:10]}...'):
                System().ssh_server.trusted_ca_keys.key_id[f'KEY{len(self.ca_keys)}'].set(op_param_name='key', op_param_value=key_content[1], apply=False, ask_for_confirmation='-y').verify_result()
                System().ssh_server.trusted_ca_keys.key_id[f'KEY{len(self.ca_keys)}'].set(op_param_name='type', op_param_value=key_content[0], apply=False, ask_for_confirmation='-y').verify_result()
                self.ca_keys.append(f'KEY{len(self.ca_keys)}')

        with allure.step(f'Sign certificate for {pubkey}'):
            cmd = f'ssh-keygen -s {key_path} -I {key_id} -n {username} {key_path}.pub'
            subprocess.run(cmd.split(' '))
            if not os.path.exists(f'{key_path}-cert.pub'):
                raise Exception(f'Certificate file was not created: {key_path}-cert.pub')

    @staticmethod
    def extract_key_info_single_regex(pubkey: str):
        """
        @summary: Single regex to extract key type, bits, and certificate status from SSH public key type string
        @param pubkey: SSH public key type
        @return: tuple of (key_type, num_bits, is_certificate) or (None, None, None) if no match
        @raises: Exception if failed to extract key type, bits, and certificate status from SSH public key type string
        """
        # Single comprehensive regex pattern that captures certificate status
        pattern = r'(?:(ecdsa)-sha2-nistp(\d+)(-cert)?|(rsa)-sha2-(\d+)(-cert)?|(ssh-ed25519)(-cert)?|(ssh-rsa)(-cert)?)'

        match = re.search(pattern, pubkey)
        if match:
            if match.group(1) and match.group(2):  # ECDSA: ecdsa-sha2-nistp256/384/521
                return match.group(1), int(match.group(2)), match.group(3)
            elif match.group(4):  # RSA: rsa-sha2-512, rsa-sha2-256
                return match.group(4), 4096, match.group(6)  # int(match.group(5))*8
            elif match.group(7):  # Ed25519: ssh-ed25519
                return match.group(7), 256, match.group(8)
            elif match.group(9):  # RSA: ssh-rsa (legacy format)
                return match.group(9), 4096, match.group(10)
        return (None, None, None)

import logging
import os
import time

from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine

from ngts.nvos_tools.infra.PexpectTool import PexpectTool
from ngts.tests_nvos.general.security.constants import SSN_OPTIONS


class SecuritySshTool:
    @staticmethod
    def rm_auth_key(key_path: str):
        logging.info(f"Remove key: {key_path}")
        rm_cmd = f"rm -f {key_path}"
        pexpect = PexpectTool(spawn_cmd=rm_cmd)
        logging.info("Sleep: 3 seconds")
        time.sleep(3)
        pexpect.expect(expect_msg=".*")

    @staticmethod
    def rm_auth_keypair(key_path: str):
        SecuritySshTool.rm_auth_key(key_path=key_path)
        SecuritySshTool.rm_auth_key(key_path=f"{key_path}.pub")

    @staticmethod
    def generate_auth_keypair(key_type: str, dst_path: str, num_bits: int = 1024):
        """
        @summary: Generate key pair for SSH public key authentication
        @param key_type: type of the key
        @param dst_path: destination path to store the key pair at
        @param num_bits: number of bits for the key (optional)
        @param timeout: timeout to let pexpect wait each time (optional)
        """
        logging.info(f"Generate SSH key-pair of type {key_type} and with {num_bits} bits at {dst_path}")
        keygen_cmd = f"ssh-keygen -t {key_type} -b {num_bits} -f {dst_path}"
        pexpect = PexpectTool(spawn_cmd=keygen_cmd, default_expect_err_msg="Keygen failed")
        try:
            res_index = pexpect.expect(expect_msg=["Enter passphrase \\(empty for no passphrase\\):", "Overwrite \\(y/n\\)\\?"])
            if res_index == 1:
                pexpect.sendline(send_str="y")
                pexpect.expect(expect_msg="Enter passphrase \\(empty for no passphrase\\):")
            pexpect.send(send_str="\r")
            pexpect.expect(expect_msg="Enter same passphrase again:")
            pexpect.send(send_str="\r")
            logging.info("Sleep: 3 seconds")
            time.sleep(3)
            pexpect.expect(expect_msg=".*")

            if not os.path.exists(dst_path) or not os.path.exists(f"{dst_path}.pub"):
                raise Exception(
                    f"ssh-keygen did not create the expected key files at {dst_path}. "
                    f"Private key exists: {os.path.exists(dst_path)}, "
                    f"Public key exists: {os.path.exists(f'{dst_path}.pub')}"
                )

            # SSH requires strict permissions: 600 for private key, 644 for public key
            os.chmod(dst_path, 0o600)
            os.chmod(f"{dst_path}.pub", 0o644)
            logging.info(f"Successfully created key pair at {dst_path} with correct permissions")
        except Exception as e:
            logging.error(f"Got exception during key generation:\n{e}")
            raise e

    @staticmethod
    def upload_auth_key_to_server(key_path: str, server_engine: ProxySshEngine):
        """
        @summary: Upload key (with given path) to the given ssh server
        @param key_path: path of key to upload
        @param server_engine: engine describing the ssh server and user
        """
        logging.info(f"Upload SSH key\nKey: {key_path}\nServer: {server_engine.ip}\nUser: {server_engine.username}")
        ssh_copy_cmd = f"ssh-copy-id {SSN_OPTIONS} -i {key_path} {server_engine.username}@{server_engine.ip}"
        pexpect = PexpectTool(spawn_cmd=ssh_copy_cmd, default_expect_err_msg="ssh-copy-id failed")
        try:
            pexpect.expect(expect_msg="password:")
            pexpect.sendline(send_str=server_engine.password)
            res_index = pexpect.expect(expect_msg=["Number of key\\(s\\) added: 1", "password:"])
            assert res_index != 1, f"Password {server_engine.password} is incorrect"
            logging.info("Sleep: 3 seconds")
            time.sleep(3)
            pexpect.expect(expect_msg=".*")
        except Exception as e:
            logging.info(f"Got exception:\n{e}")
            raise e

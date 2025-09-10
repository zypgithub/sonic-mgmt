import logging
import os
import random
from typing import List, Optional, Tuple

from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.SecuritySshTool import SecuritySshTool
from ngts.tests_nvos.general.security.test_ssh_cert_auth.constants import (
    CERT_VALIDITY_PERIODS,
    SSH_CERT_AUTH_KEYS_PATH,
    TEST_PRINCIPALS
)
from ngts.tests_nvos.general.security.ssh_hardening.constants import SshHardeningConsts
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


class SshCertAuthHelper:
    def __init__(self):
        self.cmd_runner = CmdRunner()
        self.keys_path = SSH_CERT_AUTH_KEYS_PATH

    def ensure_keys_directory(self):
        with allure.step(f"Ensure keys directory: {self.keys_path}"):
            os.makedirs(self.keys_path, exist_ok=True)

    def generate_key_pair(self, key_name: str, key_type: Optional[str] = None, ca: bool = False) -> Tuple[str, str, str]:
        """
        Generate CA key pair for signing certificates.

        Args:
            key_name: Name for the CA key pair
            key_type: Type of key to generate (defaults to random)
            ca: Whether to generate a CA key pair (defaults to False)

        Returns:
            Tuple of (public_key_content, key_type, private_key_path)
        """
        key_type = key_type or random.choice(list(SshHardeningConsts.PUBLIC_KEY_LENGTH_DICT.keys()))
        key_path = f"{self.keys_path}/{key_name}_ca" if ca else f"{self.keys_path}/{key_name}_key"

        with allure.step(f"Generate key pair: {key_name} ({key_type})"):
            self.ensure_keys_directory()

            SecuritySshTool.generate_auth_keypair(
                key_type=key_type,
                dst_path=key_path,
                num_bits=SshHardeningConsts.PUBLIC_KEY_LENGTH_DICT.get(key_type, 2048)
            )

            public_key_content = self.cmd_runner.run_cmd(f'cat {key_path}.pub').strip()
            public_key_hash = self.extract_public_key(public_key_content)

            logger.info(f"Generated key pair: {key_path}")
            return public_key_hash, key_type, key_path

    def generate_ca_key_pair(self, ca_name: str, key_type: Optional[str] = None) -> Tuple[str, str, str]:
        return self.generate_key_pair(ca_name, key_type, ca=True)

    def generate_user_key_pair(self, user_name: str, key_type: Optional[str] = None) -> Tuple[str, str, str]:
        return self.generate_key_pair(user_name, key_type)

    def sign_user_certificate(self, ca_private_key_name: str, user_key_name: str,
                              principals: List[str], cert_id: str = 'cert', validity: Optional[str] = None) -> str:
        """
        Sign user certificate with CA private key.

        Args:
            ca_private_key_name: Name for the CA key pair
            user_key_name: Name for the user key pair
            principals: List of principals for the certificate
            cert_id: Certificate identifier
            validity: Certificate validity period (defaults to +1d)

        Returns:
            Path to the signed certificate
        """
        validity = validity or CERT_VALIDITY_PERIODS['day']
        principals_str = ','.join(principals)
        cert_path = f"{self.keys_path}/{user_key_name}-cert.pub"

        with allure.step(f"Sign certificate: {cert_id} with principals {principals_str}"):
            sign_cmd = (
                f"ssh-keygen -s {self.keys_path}/{ca_private_key_name} "
                f"-I {cert_id} "
                f"-n {principals_str} "
                f"-V {validity} "
                f"{self.keys_path}/{user_key_name}"
            )

            logger.info(f"Signing certificate with command: {sign_cmd}")
            self.cmd_runner.run_cmd(sign_cmd, allowed_err='Signed user key')

            if not os.path.exists(cert_path):
                raise Exception(f"Certificate signing failed: {cert_path} not created")

            logger.info(f"Certificate signed successfully: {cert_path}")
            return cert_path

    def generate_keys_and_sign_certificate(self, key_name: str, key_type: str, principals: List[str]) -> Tuple[str, str]:
        _, _, key_path = self.generate_user_key_pair(key_name, key_type)
        ca_public_key_hash, _, _ = self.generate_ca_key_pair(key_name, key_type)
        _ = self.sign_user_certificate(f"{key_name}_ca", f"{key_name}_key", principals=principals)
        return ca_public_key_hash, key_path

    def extract_public_key(self, public_key_content: str) -> str:
        """
        Extract just the key part from the public key content.

        Args:
            public_key_content: Full public key content

        Returns:
            Just the key part (base64 encoded)
        """
        parts = public_key_content.split()
        if len(parts) >= 2:
            return parts[1]
        return public_key_content

    def cleanup_generated_keys(self, key_name: str):
        """
        Clean up generated key pair, ca key and certificate.

        Args:
            key_name: Base path for the key pair
        """
        with allure.step(f"Cleanup key pair: {key_name}"):
            SecuritySshTool.rm_auth_keypair(f"{self.keys_path}/{key_name}_ca")
            SecuritySshTool.rm_auth_keypair(f"{self.keys_path}/{key_name}_key")
            SecuritySshTool.rm_auth_key(f"{self.keys_path}/{key_name}_key-cert.pub")


def get_random_principals(number_of_values_to_select: int = 1) -> List[str]:
    return RandomizationTool.select_random_values(TEST_PRINCIPALS, number_of_values_to_select=number_of_values_to_select).get_returned_value()


def get_random_principal() -> str:
    return get_random_principals(number_of_values_to_select=1)[0]


def get_random_validity() -> str:
    return random.choice(list(CERT_VALIDITY_PERIODS.values()))


def get_random_key_type(exclude: Optional[List[str]] = None) -> str:
    exclude = exclude or []
    key_types = list(SshHardeningConsts.PUBLIC_KEY_LENGTH_DICT.keys())
    key_types = [key_type for key_type in key_types if key_type not in exclude]
    return random.choice(key_types)


def cleanup_trusted_ca_keys(system: System):
    with allure.step("Clean up trusted CA keys"):
        system.ssh_server.trusted_ca_keys.unset()


def cleanup_user_cert_auth(system: System, username: str):
    with allure.step(f"Clean up cert-auth for user: {username}"):
        system.aaa.user.user_id[username].ssh.cert_auth.unset()

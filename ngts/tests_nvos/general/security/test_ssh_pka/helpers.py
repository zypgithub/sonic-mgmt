import random

from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.tests_nvos.general.security.ssh_hardening.constants import SshHardeningConsts
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.SecuritySshTool import *
from ngts.tools.test_utils import allure_utils as allure

keys_path = "/auto/sw_system_project/NVOS_INFRA/security/verification/ssh_pka/"

public_key_length = {
    'ecdsa-sha2-nistp521': '521',
    'ecdsa-sha2-nistp384': '384',
    'ecdsa-sha2-nistp256': '256',
    'ssh-ed25519': '1024',
    'ssh-rsa': '4096'
}


def _generate_new_key(engine, user_name, key_type=''):
    """
        ssh-keygen -t {type} -b {len} -o -a 100 -f ~/.ssh/{username}
        output: admin, admin.pub
    :return:
    """
    key_type = key_type if key_type else random.choice(list(SshHardeningConsts.PUBLIC_KEY_LENGTH_DICT.keys()))

    with allure.step(f"generate {key_type} pair of keys"):
        SecuritySshTool.generate_auth_keypair(key_type, f"{keys_path}{user_name}", SshHardeningConsts.PUBLIC_KEY_LENGTH_DICT[key_type])

    with allure.step("get the public key"):
        cmd_runner = CmdRunner()
        public_key_data = cmd_runner.run_cmd(f'cat {keys_path}{user_name}.pub')
        public_key = public_key_data.split()[1]
    return public_key, key_type, f"{keys_path}{user_name}"


def _check_password_prompt(private_key_path, username, hostname):
    """
        ssh-keygen -t {type} -b {len} -o -a 100 -f ~/.ssh/{username}
        output: admin, admin.pub
    :return:
    """
    expected_message = f".*You are required to change your password immediately"
    ssh_pka_connection_cmd = f'ssh -i {private_key_path} {username}@{hostname}'
    engine = PexpectTool(spawn_cmd=ssh_pka_connection_cmd)
    engine.expect(expected_message, error_message='Expected login success, but failed')

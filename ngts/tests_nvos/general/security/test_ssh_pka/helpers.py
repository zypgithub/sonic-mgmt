import random


from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.SecuritySshTool import *

keys_path = "./"

public_key_length = {
    'ecdsa-sha2-nistp521': '521',
    'ecdsa-sha2-nistp384': '384',
    'ecdsa-sha2-nistp256': '256',
    'ssh-ed25519': '1024',
    'rsa': '4096'
}


def _generate_new_key(engine, user_name, key_type=''):
    """
        ssh-keygen -t {type} -b {len} -o -a 100 -f ~/.ssh/{username}
        output: admin, admin.pub
    :return:
    """
    key_type = key_type if key_type else random.choice(list(public_key_length.keys()))

    with allure.step(f"generate {key_type} pair of keys"):
        SecuritySshTool.generate_auth_keypair(key_type, f"{keys_path}{user_name}", public_key_length[key_type])

    with allure.step("get the public key"):
        cmd_runner = CmdRunner()
        public_key = cmd_runner.run_cmd(f'cat {keys_path}{user_name}.pub')
    return public_key, key_type, f"{keys_path}{user_name}"

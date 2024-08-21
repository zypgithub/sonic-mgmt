import logging
import random
import socket
import string
import time

from netmiko.ssh_exception import NetmikoAuthenticationException

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from infra.tools.general_constants.constants import DefaultConnectionValues
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.PexpectTool import PexpectTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.conftest import clear_config

logger = logging.getLogger(__name__)


def recover_dut_with_remote_reboot(topology_obj, engines, should_clear_config: bool = True, wait_after_rr=None):
    with allure.step('Execute remote reboot'):
        NvueGeneralCli(engines.dut).remote_reboot(topology_obj)
    if wait_after_rr:
        with allure.step(f'sleep {wait_after_rr} seconds'):
            time.sleep(wait_after_rr)
    with allure.step('Wait for switch to be up'):
        engines.dut.disconnect()
        DutUtilsTool.wait_for_nvos_to_become_functional(engines.dut).verify_result()
    if should_clear_config:
        with allure.step('Clear config again'):
            clear_config()
        #     NvosInstallationSteps.clear_conf(engines.dut)
        # with allure.step('Set base conf again'):
        #     set_base_configurations(dut_engine=engines.dut, timezone=LinuxConsts.JERUSALEM_TIMEZONE, apply=True,
        #                             save_conf=True)


def generate_strong_password(n: int = 10) -> str:
    assert n >= 10, f'Given argument "n" - {n} - is too small. Must be at least 10'

    lower_len: int = random.randint(1, 9)
    upper_len: int = n - lower_len

    lowers_str: str = RandomizationTool.get_random_string(length=lower_len)
    uppers_str: str = RandomizationTool.get_random_string(length=upper_len, ascii_letters=string.ascii_uppercase)
    rand_num_str: str = str(random.randint(0, 999))

    return lowers_str + '_' + uppers_str + rand_num_str


def new_handle_change_password_prompt(engine: ProxySshEngine):
    SUCCESS, FAIL = 'success', 'fail'

    ip, port, username, orig_password = engine.ip, engine.ssh_port, engine.username, engine.password
    # _ssh_command = DefaultConnectionValues.SSH_CMD.copy() + ['-p', str(port)] + ['-l', username, ip]
    # ssh_cmd = ' '.join(_ssh_command)
    ssh_cmd = f'ssh -tt -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o GSSAPIAuthentication=no -o ' \
        f'PubkeyAuthentication=no -p {port} -l {username} {ip}'
    with allure.step('SSH the switch'):
        pexpect_tool = PexpectTool(spawn_cmd=ssh_cmd)
    with allure.step('Expect password prompt'):
        expect = ['New password:', 'password:'] + DefaultConnectionValues.DEFAULT_PROMPTS
        res = pexpect_tool.expect(expect, raise_exception_for_timeout=False)
        if res not in range(len(expect)):
            return FAIL
        if res > 1:
            return SUCCESS
    if res == 1:
        with allure.step('Enter orig password'):
            pexpect_tool.sendline(orig_password)
        with allure.step('Expect new password prompt'):
            expect = ['New password:'] + DefaultConnectionValues.DEFAULT_PROMPTS
            res = pexpect_tool.expect(expect, raise_exception_for_timeout=False)
            if res not in range(len(expect)):
                return FAIL
            if res > 0:
                return SUCCESS
    if res == 0:
        with allure.step('Generate strong password'):
            new_password = generate_strong_password()
        with allure.step(f'Enter "{new_password}" as new password'):
            pexpect_tool.sendline(new_password)
        with allure.step('Expect retype new password prompt'):
            expect = 'Retype new password:'
            res = pexpect_tool.expect(expect, raise_exception_for_timeout=False)
            if res != 0:
                return FAIL
        with allure.step(f'Enter "{new_password}" again and finish'):
            pexpect_tool.sendline(new_password)
        with allure.step('Expect default prompt after login'):
            expect = DefaultConnectionValues.DEFAULT_PROMPTS
            res = pexpect_tool.expect(expect, raise_exception_for_timeout=False)
            if res not in range(len(expect)):
                return FAIL
        with allure.step('Reset password'):
            reset_cmd = f'nv set sys se p st dis ; nv c a ; nv se sys a u {username} pa {orig_password} ; nv c a ; nv ' \
                f'set sys se p st en; nv c a ; nv c save '
            pexpect_tool.sendline(reset_cmd)
        with allure.step('Expect default prompt after login and finish'):
            expect = DefaultConnectionValues.DEFAULT_PROMPTS
            res = pexpect_tool.expect(expect, raise_exception_for_timeout=False)
            if res not in range(len(expect)):
                return FAIL
            return SUCCESS if (pexpect_tool.expect('.*', raise_exception_for_timeout=False) == 0) else FAIL


def check_switch_connectivity(topology_obj, engines):
    NETMIKO_ERR, SOCKET_ERR, SUCCESS = 'Netmiko', 'Socket', 'success'

    def check_connectivity():
        try:
            with allure.step('Check connectivity of local engine with dummy show command'):
                logger.info(System().aaa.show())
                return SUCCESS
        except NetmikoAuthenticationException as e:
            logger.exception(f'Netmiko Exception:\n{e}')
            return NETMIKO_ERR
        except socket.error as e:
            logger.exception(f'Socket Error:\n{e}')
            return SOCKET_ERR
        finally:
            pass

    res = check_connectivity()
    if res == SUCCESS:
        return
    with allure.step(f'Disconnect dut engine and try again'):
        engines.dut.disconnect()
        res = check_connectivity()
        if res == SUCCESS:
            return
    with allure.step(f'Got {res} error. Try recover with new change password handling'):
        res = new_handle_change_password_prompt(engines.dut)
        if res == SUCCESS:
            res = check_connectivity()
            if res == SUCCESS:
                return
    with allure.step(f'Got {res} error. Try recover with remote reboot to dut'):
        recover_dut_with_remote_reboot(topology_obj, engines)

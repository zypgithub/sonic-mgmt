import time

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.BmcSshEngine import BmcSshEngine
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool, RebootParams
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.general.security.bmc.bmc_creds.constants import BmcCliCmd, BmcUsers
from ngts.tools.test_utils import allure_utils as allure


def bmc_factory_reset(bmc_session: BmcSshEngine, dut_engine: LinuxSshEngine, topology_obj):
    with allure.step('run bmc factory reset cmd'):
        bmc_session.run_cmd(BmcCliCmd.factory_reset)
        time.sleep(3)
    with allure.step('check bmc factory reset flag'):
        bmc_session.run_cmd(BmcCliCmd.check_factory_reset_flag)
        # out = bmc_engine.run_cmd(f'{BmcCliCmd.check_factory_reset_flag} | grep "{FACTORY_RESET_FLAG}"')
        # factory_reset_flag_value = out.split(':')[1].strip()
        # assert factory_reset_flag_value == '1', f'bmc factory reset flag is not 1.\nexpected: 1\nout:\n{out}'
    with allure.step('power cycle the switch - run remote reboot'):
        NvueGeneralCli(dut_engine).remote_reboot(topology_obj)
    with allure.step('wait for switch to be ready again'):
        DutUtilsTool.wait_on_system_reboot(dut_engine,
                                           reboot_params=RebootParams(topology_obj=TestToolkit.topology_obj))


def enable_mctp_pcie_ctrl_service_in_bmc(dut_engine: LinuxSshEngine):
    with allure.step(f'ssh to bmc with user "{BmcUsers.root.username}"'):
        bmc_session = BmcSshEngine(dut_engine, BmcUsers.root.username, BmcUsers.root.default_password,
                                   BmcUsers.root.another_password)
    with allure.step('run enable service cmd'):
        bmc_session.run_cmd(BmcCliCmd.enable_mctp_pcie_ctrl_service)
        time.sleep(3)

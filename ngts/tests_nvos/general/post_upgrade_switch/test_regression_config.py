import logging

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.RegressionConfigurations import Configurations
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


def test_regression_config(engines):
    with allure.step("Running required commands"):
        if engines.dut.ip in Configurations.post_install_commands.keys():
            commands_list = Configurations.post_install_commands[engines.dut.ip]

            for command in commands_list:
                with allure.step(f"Running command '{command}'"):
                    engines.dut.run_cmd(command)

        if engines.dut.ip in Configurations.devices_missing_psus:
            Platform().ps_redundancy.set('policy', 'no-redundancy', apply=True)
            NvueGeneralCli.save_config(engines.dut)

        if engines.dut.ip in Configurations.devices_requested_factory_reset:
            with allure.step("Running system factory-default reset"):
                System().factory_default.action_reset(param='force').verify_result()

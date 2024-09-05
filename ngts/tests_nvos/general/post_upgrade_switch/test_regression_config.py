import logging
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.RegressionConfigurations import Configurations

logger = logging.getLogger()


def test_regression_config(engines):
    with allure.step("Running required commands"):
        if engines.dut.ip in Configurations.post_install_commands.keys():
            commands_list = Configurations.post_install_commands[engines.dut.ip]

            for command in commands_list:
                with allure.step(f"Running command '{command}'"):
                    engines.dut.run_cmd(command)

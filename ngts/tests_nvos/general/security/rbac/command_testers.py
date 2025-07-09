import logging
import pytest

from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_constants.constants_nvos import SystemConsts, PlatformConsts
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class CommandTester:
    def __init__(self, user_engine):
        self.user_engine = user_engine
        self.results = {
            'show': False,
            'set': False,
            'unset': False,
            'action': False
        }

    def test_operation(self, operation, func, *args, **kwargs):
        with allure.step(f"Testing {operation} operation"):
            output = func(*args, **kwargs, dut_engine=self.user_engine)
            self.results[operation] = output.result
            output.ignore_result()

    def get_results(self):
        return self.results


class InterfaceCommandTester(CommandTester):
    def __init__(self, user_engine, selected_port):
        super().__init__(user_engine)
        self.selected_port = selected_port

    def test_commands(self):
        with allure.step("Testing commands on interface"):
            NvueGeneralCli.detach_config(self.user_engine)

            self.test_operation('show', self.selected_port.interface.show, if_returned_value=False)
            self.test_operation('set', self.selected_port.interface.set, op_param_name='description',
                                op_param_value='TestDesc', apply=True)
            self.test_operation('unset', self.selected_port.interface.unset, op_param='description', apply=True)
            self.test_operation('action', self.selected_port.interface.action_clear_counter_for_interface,
                                interface_name=self.selected_port.name)

        return self.get_results()


class SystemCommandTester(CommandTester):
    def __init__(self, user_engine):
        super().__init__(user_engine)
        self.system = System()

    def test_commands(self):
        with allure.step("Testing commands on system"):
            NvueGeneralCli.detach_config(self.user_engine)

            self.test_operation('show', self.system.show, if_returned_value=False)
            self.test_operation('set', self.system.message.set, op_param_name=SystemConsts.PRE_LOGIN_MESSAGE,
                                op_param_value='testing_msg', apply=True)
            self.test_operation('unset', self.system.message.unset, op_param=SystemConsts.PRE_LOGIN_MESSAGE, apply=True)
            self.test_operation('action', self.system.stats.action_general, action_str="clear")

            return self.get_results()


class PlatformCommandTester(CommandTester):
    def __init__(self, user_engine, is_nso_system: bool = False):
        super().__init__(user_engine)
        self.platform = Platform()
        self.is_nso_system = is_nso_system

    def test_commands(self):
        with allure.step("Testing commands on platform"):
            NvueGeneralCli.detach_config(self.user_engine)

            self.test_operation('show', self.platform.show, if_returned_value=False)
            self.test_operation('set', self.platform.firmware.asic.set, PlatformConsts.FW_SOURCE,
                                PlatformConsts.FW_SOURCE_CUSTOM, apply=True)
            self.test_operation('unset', self.platform.firmware.asic.unset, PlatformConsts.FW_SOURCE, apply=True)

            if self.is_nso_system:
                logger.info("NSO system detected, skipping transceiver actions")
            else:
                list_of_transceivers = list(self.platform.transceiver.get_dict_of_transceivers(cable_type=None))
                transceiver_name = Tools.RandomizationTool.select_random_value(list_of_transceivers).get_returned_value()
                self.test_operation('action', self.platform.transceiver.action_reset,
                                    transceiver_name=transceiver_name)

        return self.get_results()

import logging
import time
from typing import List

import requests

from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli
from ngts.cli_wrappers.nvue.nvue_platform_clis import NvuePlatformCli
from ngts.cli_wrappers.nvue.nvue_system_clis import NvueSystemCli
from ngts.cli_wrappers.openapi.openapi_base_clis import OpenApiBaseCli
from ngts.cli_wrappers.openapi.openapi_platform_clis import OpenApiPlatformCli
from ngts.cli_wrappers.openapi.openapi_system_clis import OpenApiSystemCli
from ngts.nvos_constants.constants_nvos import ApiType, ActionConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.ib.InterfaceConfiguration.MgmtPort import MgmtPort
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.PortFastRecovery import PortFastRecovery
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.system.Firmware import Firmware
from ngts.nvos_tools.system.Health import Health
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class Fae(BaseComponent):
    def __init__(self, parent_obj=None, port_name='eth0'):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueBaseCli, ApiType.OPENAPI: OpenApiBaseCli}, path='/fae')
        self.system = FaeSystem(self)
        self.firmware = Firmware(self)
        self.ipoibmapping = BaseComponent(self, path='/ipoib-mapping')
        self.health = Health(self)
        self.port = MgmtPort(port_name, self)
        self.fast_recovery = PortFastRecovery(self)
        self.ib = Ib(self)
        self.sonic_cli = SonicCli(self)
        self.interface = Interface(self, port_name)
        self.platform = FaePlatform(self)


class Ib(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/ib')
        self.ufm_mad = BaseComponent(self, path='/ufm-m')  # [L.A] temporary change ('/ufm-mad')


class SonicCli(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueSystemCli, ApiType.OPENAPI: OpenApiSystemCli}, path='/sonic-cli')

    def action_general(self, action_str):
        return SendCommandTool.execute_command(
            self.api_obj[TestToolkit.tested_api].action_general_with_expected_disconnect,
            TestToolkit.engines.dut, action_str, self.get_resource_path())


class FaePlatform(BaseComponent):
    """Represents fae/platform subtree"""

    def __init__(self, parent_obj=None):
        super().__init__(parent_obj, path='/platform',
                         api={ApiType.NVUE: NvuePlatformCli, ApiType.OPENAPI: OpenApiPlatformCli})
        self.firmware = FaeFirmware(self)


class FaeFirmware(BaseComponent):
    """Represents fae/platform/firmware subtree"""

    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/firmware')
        self.asic1 = FaePlatformComponent(self, 'ASIC1')
        # multi-asic devices also have asic2 but our tests don't need it currently
        self.cpld = FaeCpldComponent(self, 'cpld')
        self.bios = FaeBiosComponent(self, 'bios')
        self.ssd = FaePlatformComponent(self, 'ssd')
        self.bmc = FaePlatformComponent(self, 'bmc')  # TODO: Fix after bug closed https://redmine.mellanox.com/issues/3955495
        self.fpga = FaePlatformComponent(self, 'fpga')

    def install_bios_firmware(self, bios_image_path, device):
        with allure.step("installing bios firmware from {action_type}".format(action_type=bios_image_path)):
            return SendCommandTool.execute_command(
                self.api_obj[TestToolkit.tested_api].action_install_fae_bios_firmware,
                TestToolkit.engines.dut, bios_image_path, self.get_resource_path(), device)


class FaeBiosComponent(BaseComponent):
    def __init__(self, parent_obj=None, component_name=None):
        super().__init__(parent=parent_obj, path=f"/{component_name}")


class FaePlatformComponent(BaseComponent):
    def __init__(self, parent_obj=None, component_name=None):
        super().__init__(parent=parent_obj, path=f"/{component_name}")
        # todo: restructure this class (and update relevant tests) to use the Files class
        # todo: self.files = Files(self)

    def show_files(self):
        """nv show fae platform firmware (bios|cpld|ssd) files"""
        return super().show(op_param='files')

    def show_files_as_list(self) -> List[str]:
        return OutputParsingTool.parse_show_files_to_names(self.show_files()).get_returned_value()

    def action_install(self, filename, device, expect_reboot) -> ResultObj:
        """nv action install fae platform firmware (bios|cpld|ssd) files <file-name> [force]"""
        return self.action(ActionConsts.INSTALL, 'files ' + filename, 'force', expect_reboot=expect_reboot)

    def action_delete(self, filename) -> ResultObj:
        """nv action delete fae platform firmware (bios|cpld|ssd) files <file-name> [force]"""
        return self.action(ActionConsts.DELETE, 'files ' + filename, expected_output='File delete successfully')


class FaeCpldComponent(FaePlatformComponent):
    def action_install(self, filename, device, expect_reboot) -> ResultObj:
        # This override is necessary because cpld-fw installation is done in two steps (BURN then REFRESH), and
        # when running action-install on the REFRESH image the system immediately reboots and connection is lost.
        try:
            return super().action_install(filename, device, expect_reboot)
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
            if expect_reboot:
                logger.info(f"GET request failed as expected because of switch reboot")
                with allure.step("Waiting for reboot to finish"):
                    logger.info(f"Waiting 30 seconds to make sure reboot has started")
                    time.sleep(30)
                    engine = TestToolkit.engines.dut
                    engine.disconnect()
                    check_port_status_till_alive(True, engine.ip, engine.ssh_port)
                    return DutUtilsTool.wait_for_nvos_to_become_functional(engine)
            else:
                raise


class FaeSystem(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/system')
        self.events = BaseComponent(self, path='/events')
        self.fatal = BaseComponent(self, path='/fatal')
        self.fatal.monitor = BaseComponent(self.fatal, path='/monitor')

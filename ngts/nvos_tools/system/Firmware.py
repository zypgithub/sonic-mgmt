import logging

from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.system.Files import Files
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.system.Asic import Asic
from ngts.nvos_tools.system.Transceiver import Transceiver
from ngts.nvos_tools.system.Erot import Erot

logger = logging.getLogger()


class Firmware(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/firmware')
        self.asic = Asic(self)
        self.transceiver = Transceiver(self)
        self.bmc = PlatformComponent(self, component_name='BMC')
        self.fpga = PlatformComponent(self, component_name='FPGA')
        self.bios = PlatformComponent(self, component_name='BIOS')
        self.erot = Erot(self)

    def install_bios_firmware(self, bios_image_path, device, topology_obj=None):
        with allure.step("installing bios firmware from {action_type}".format(action_type=bios_image_path)):
            return SendCommandTool.execute_command(
                self.api_obj[TestToolkit.tested_api].action_install_bios_firmware,
                TestToolkit.engines.dut, bios_image_path, self.get_resource_path(), device, topology_obj)


class PlatformComponent(BaseComponent):
    def __init__(self, parent_obj=None, component_name=None):
        super().__init__(parent=parent_obj, path=f"/{component_name}")
        self.files = Files(self)

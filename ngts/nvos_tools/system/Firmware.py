import logging
from typing import List


from ngts.nvos_tools.system.Asic import Asic
from ngts.nvos_tools.system.Transceiver import Transceiver
from ngts.nvos_tools.system.Erot import Erot
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.Files import Files


logger = logging.getLogger()


class Firmware(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/firmware')
        self.asic = Asic(self)
        self.transceiver = Transceiver(self)
        self.bmc = PlatformComponent(self, component_name='BMC')
        self.fpga = PlatformComponent(self, component_name='FPGA')
        self.bios = PlatformComponent(self, component_name='BIOS')
        self.cpld = PlatformComponent(self, component_name='CPLD1')
        self.erot = Erot(self)


class PlatformComponent(BaseComponent):
    def __init__(self, parent_obj=None, component_name=None):
        super().__init__(parent=parent_obj, path=f"/{component_name}")
        self.files = Files(self)

    def show_files_as_list(self) -> List[str]:
        return OutputParsingTool.parse_show_files_to_names(self.files.show()).get_returned_value()

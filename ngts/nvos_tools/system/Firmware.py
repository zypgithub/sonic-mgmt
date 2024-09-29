import logging

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
        self.bmc = BaseComponent(self, path='/BMC')
        self.fpga = BaseComponent(self, path='/FPGA')
        self.bios = BaseComponent(self, path='/BIOS')
        self.erot = Erot(self)

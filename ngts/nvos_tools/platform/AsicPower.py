import logging
from typing import Dict
from typing import List

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.ErotComponent import ErotComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.system.Asic import Asic
from ngts.nvos_tools.system.Files import Files
from ngts.nvos_tools.system.Transceiver import Transceiver
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class AsicPower(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/asic-power')
        self.asic_id: Dict[str, AsicComponent] = DefaultDict(lambda asic_name: AsicComponent(self, asic_name=asic_name))


class AsicComponent(BaseComponent):
    def __init__(self, parent_obj=None, asic_name=None):
        super().__init__(parent=parent_obj, path=f"/{asic_name}")

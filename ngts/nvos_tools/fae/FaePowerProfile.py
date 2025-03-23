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


class FaePowerProfile(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/power-profile")
        self.profile_id: Dict[str, FaeProfileComponent] = DefaultDict(lambda profile_name: FaeProfileComponent(self, profile_name=profile_name))

    def set_active_profile(self, profile_name, apply=False):
        return self.set(op_param_name='active', op_param_value=profile_name, apply=apply)


class FaeProfileComponent(BaseComponent):
    def __init__(self, parent_obj=None, profile_name=None):
        super().__init__(parent=parent_obj, path=f"/{profile_name}")

    def set_attribute(self, attribute_name, value, apply=False):
        return self.set(op_param_name=attribute_name, op_param_value=value, apply=apply)

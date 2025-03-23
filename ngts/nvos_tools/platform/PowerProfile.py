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


class PowerProfile(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/power-profile')
        self.available = Available(self)

    def set_active_profile(self, profile_name, apply=False):
        return self.set(op_param_name='active', op_param_value=profile_name, apply=apply)

    def unset_active_profile(self, apply=False):
        return self.unset(op_param='active', apply=apply)


class Available(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/available')
        self.profile_id: Dict[str, ProfileComponent] = DefaultDict(lambda profile_name: ProfileComponent(self, profile_name=profile_name))


class ProfileComponent(BaseComponent):
    def __init__(self, parent_obj=None, profile_name=None):
        super().__init__(parent=parent_obj, path=f"/{profile_name}")

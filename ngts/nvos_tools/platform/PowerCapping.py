from typing import Dict

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_constants.constants_nvos import PowerCappingConsts


class PowerCapping(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/power-capping')
        self.profiles = Profiles(self)

    def set_active_profile(self, profile_name, apply=False):
        return self.set(op_param_name=PowerCappingConsts.ACTIVE_PROFILE, op_param_value=profile_name, apply=apply)

    def unset_active_profile(self, apply=False):
        return self.unset(op_param=PowerCappingConsts.ACTIVE_PROFILE, apply=apply)


class Profiles(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/profiles')
        self.profile_id: Dict[str, ProfileComponent] = DefaultDict(lambda profile_name: ProfileComponent(self, profile_name=profile_name))


class ProfileComponent(BaseComponent):
    def __init__(self, parent_obj=None, profile_name=None):
        super().__init__(parent=parent_obj, path=f"/{profile_name}")

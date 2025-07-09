from typing import Dict

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_constants.constants_nvos import PowerCappingConsts


class FaePowerCapping(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/power-capping")
        self.profile_id: Dict[str, FaeProfileComponent] = DefaultDict(lambda profile_name: FaeProfileComponent(self, profile_name=profile_name))

    def set_active_profile(self, profile_name, apply=False):
        return self.set(op_param_name=PowerCappingConsts.ACTIVE_PROFILE, op_param_value=profile_name, apply=apply)


class FaeProfileComponent(BaseComponent):
    def __init__(self, parent_obj=None, profile_name=None):
        super().__init__(parent=parent_obj, path=f"/{profile_name}")

    def set_attribute(self, attribute_name, value, apply=False):
        return self.set(op_param_name=attribute_name, op_param_value=value, apply=apply)

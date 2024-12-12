import re

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.RemoteAaaResource import RemoteAaaResource


class Ldap(RemoteAaaResource):

    def __init__(self, parent_obj=None):
        super().__init__(parent_obj=parent_obj, resource_name='/ldap')
        self.ssl = BaseComponent(self, path='/ssl')
        self.filter = LdapFilter(self)
        self.map = LdapMap(self)


class LdapFilter(BaseComponent):

    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/filter')

    def set(self, op_param_name="", op_param_value={}, expected_str='', apply=False, ask_for_confirmation=False,
            dut_engine=None):
        if TestToolkit.tested_api == ApiType.NVUE:
            pattern = r'^"(.*)"$'
            value_wrapped_with_dquotes = isinstance(op_param_value, str) and bool(re.match(pattern, op_param_value))
            if not value_wrapped_with_dquotes:
                op_param_value = f'"{op_param_value}"'  # filter values may contain special chars like '&', '!', etc

        return super().set(op_param_name, op_param_value, expected_str, apply, ask_for_confirmation, dut_engine)


class LdapMap(BaseComponent):

    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/map')
        self.passwd = BaseComponent(self, path='/passwd')
        self.group = BaseComponent(self, path='/group')
        self.shadow = BaseComponent(self, path='/shadow')

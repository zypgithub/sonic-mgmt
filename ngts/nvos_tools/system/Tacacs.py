from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.system.RemoteAaaResource import RemoteAaaResource


class Tacacs(RemoteAaaResource):

    def __init__(self, parent_obj=None, resource_name: str = ''):
        super().__init__(parent_obj=parent_obj, resource_name='/tacacs')
        self.accounting = BaseComponent(self, path='/accounting')

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from typing import Dict


class Hostname(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/hostname')
        self.hostname_id: Dict[str, HostnameId] = DefaultDict(lambda hostname_id: HostnameId(self, hostname_id))


class HostnameId(BaseComponent):
    def __init__(self, parent_obj, hostname_id):
        BaseComponent.__init__(self, parent=parent_obj, path='/' + hostname_id)

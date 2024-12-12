from typing import Dict

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict


class Server(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/server')
        self.server_id: Dict[str, ServerId] = DefaultDict(lambda server_id: ServerId(self, server_id))


class ServerId(BaseComponent):
    def __init__(self, parent_obj, server_id):
        BaseComponent.__init__(self, parent=parent_obj, path='/' + server_id)

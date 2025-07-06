import logging
from typing import Dict
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict

logger = logging.getLogger()


class Server(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/server')
        self.server_id: Dict[str, ServerId] = DefaultDict(
            lambda server_id: ServerId(parent=self, server_id=server_id))


class ServerId(BaseComponent):
    def __init__(self, parent, server_id):
        super().__init__(parent=parent, path=f'/{server_id}')
        self.server_id = server_id
        self.priority = BaseComponent(self, path='/priority')
        self.vrf = BaseComponent(self, path='/vrf')

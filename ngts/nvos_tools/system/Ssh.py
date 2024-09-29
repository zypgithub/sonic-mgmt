import logging
from typing import Dict

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict

logger = logging.getLogger()


class Ssh(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/ssh')
        self.authorized_key = AuthorizedKey(self)


class AuthorizedKey(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/authorized-key')
        self.key_id: Dict[str, BaseComponent] = DefaultDict(
            lambda key_id: BaseComponent(parent=self, path=f'/{key_id}'))

from typing import Dict

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict


class SpiffeId(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/spiffe-id')
        self.spiffe: Dict[str, Spiffe] = DefaultDict(lambda spiffe: Spiffe(self, spiffe))


class Spiffe(BaseComponent):
    def __init__(self, parent_obj, spiffe):
        super().__init__(parent=parent_obj, path='/' + spiffe.replace('/', '%2F'))

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
import logging

logger = logging.getLogger()


class Search(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/search')
        self.search_id: Dict[str, SearchId] = DefaultDict(
            lambda search_id: SearchId(parent=self, search_id=search_id))


class SearchId(BaseComponent):
    def __init__(self, parent, search_id):
        super().__init__(parent=parent, path=f'/{search_id}')
        self.search_id = search_id
        self.priority = BaseComponent(self, path='/priority')

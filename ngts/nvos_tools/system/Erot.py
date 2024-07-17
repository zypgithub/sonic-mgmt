import logging
from typing import List


from ngts.nvos_tools.system.Files import Files
from ngts.nvos_tools.infra.BaseComponent import BaseComponent

logger = logging.getLogger()


class Erot(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/EROT')
        self.files = Files(self)

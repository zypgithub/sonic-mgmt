import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent

logger = logging.getLogger()


class Apps(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/apps')
        self.installed = BaseComponent(self, path='/installed')
        self.running = BaseComponent(self, path='/running')

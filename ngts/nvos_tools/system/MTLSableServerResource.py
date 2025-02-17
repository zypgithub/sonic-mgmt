import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent

logger = logging.getLogger()


class MTLSableServerResource(BaseComponent):
    def __init__(self, parent=None, path=''):
        super().__init__(parent=parent, path=path)
        self.mtls = BaseComponent(self, path='/mtls')

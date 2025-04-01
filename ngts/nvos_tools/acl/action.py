import logging
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_constants.constants_nvos import AclConsts

logger = logging.getLogger()


class Action(BaseComponent):

    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/action')
        self.log = Log(self)
        self.dscp = Dscp(self)


class Log(BaseComponent):

    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/log')

    def set_log_prefix(self, log_prefix):
        return self.set(AclConsts.LOG_PREFIX, log_prefix)


class Dscp(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/set/dscp')

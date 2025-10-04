import logging
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_constants.constants_nvos import AclConsts

logger = logging.getLogger()


class Action(BaseComponent):

    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/action')
        self.log = Log(self)
        self.dscp = Dscp(self)
        self.recent = Recent(self)
        self.permit = Permit(self)
        self.deny = Deny(self)


class Log(BaseComponent):

    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/log')

    def set_log_prefix(self, log_prefix):
        return self.set(AclConsts.LOG_PREFIX, log_prefix)


class Dscp(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/set/dscp')


class Recent(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/recent')


class Permit(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/permit')


class Deny(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/deny')

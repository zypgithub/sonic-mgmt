from typing import Dict

from ngts.nvos_tools.infra.BaseComponent import BaseComponent


class ControlPlane(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/control-plane')
        self.acl = ControlPlaneAcl(self)


class ControlPlaneAcl(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/acl')
        from ngts.nvos_tools.infra.DefaultDict import DefaultDict
        self.acl_id: Dict[str, ControlPlaneAclID] = DefaultDict(lambda acl_id: ControlPlaneAclID(parent_obj=self, acl_id=acl_id))


class ControlPlaneAclID(BaseComponent):
    def __init__(self, acl_id, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path=f'/{acl_id}')
        self.inbound = BaseComponent(self, path='/inbound')
        self.outbound = BaseComponent(self, path='/outbound')
        self.statistics = ControlPlaneAclStatistics(self)


class ControlPlaneAclStatistics(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/statistics')
        from ngts.nvos_tools.infra.DefaultDict import DefaultDict
        self.rule_id: Dict[str, BaseComponent] = DefaultDict(lambda rule_id: BaseComponent(parent=self, path=f'/{rule_id}'))

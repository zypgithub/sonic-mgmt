from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.ib.InterfaceConfiguration.MgmtStats import MgmtStats
from ngts.nvos_tools.ib.InterfaceConfiguration.Phy import Phy


class LinkMgmt(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/link')
        self.state = BaseComponent(self, path='/state')
        self.diagnostics = BaseComponent(self, path='/diagnostics')
        self.stats = MgmtStats(self)
        self.phy = Phy(self)
        self.plan_ports = BaseComponent(self, path='/plan-ports')
        self.connection_mode = BaseComponent(self, path='/connection-mode')
        self.phy_recovery = BaseComponent(self, path='/phy-recovery')
        self.kr = BaseComponent(self, path='/link-training')
        self.plr = BaseComponent(self, path='/plr')

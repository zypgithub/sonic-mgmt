from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.Restrictions import Restrictions


class Authentication(BaseComponent):
    def __init__(self, parent_obj=None):
        resource_name = 'authentication-order' if TestToolkit.is_eth_dut() else 'authentication'
        BaseComponent.__init__(self, parent=parent_obj, path=f'/{resource_name}')
        self.restrictions = Restrictions(self)

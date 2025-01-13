import pytest

from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System


class NvCommand:
    def __init__(self):
        self.acl = Acl()
        self.ib = Ib()
        self.port = Port()
        self.platform = Platform()
        self.system = System()

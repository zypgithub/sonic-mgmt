import pytest

from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from typing import Dict


class NvCommand:
    def __init__(self):
        self.acl = Acl()
        self.fae = Fae()
        self.ib = Ib()
        self.platform = Platform()
        self.port: Dict[str, Port] = DefaultDict(lambda port: Port(name=port))
        self.system = System()

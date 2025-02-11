import pytest

from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from typing import Dict


class NvCommand:
    def __init__(self):
        self.acl = Acl()
        self.ib = Ib()
        self.platform = Platform()
        self.system = System()
        self.port: Dict[str, Port] = DefaultDict(
            lambda port: Port(name='eth0'))

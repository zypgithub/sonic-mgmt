import logging
from ngts.cli_wrappers.nvue.nvue_opensm_clis import NvueOpenSmCli
from ngts.cli_wrappers.openapi.openapi_opensm_cli import OpenApiOpenSmCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.ib.ibdiagnet import Ibdiagnet
from ngts.nvos_tools.ib.Sm import Sm
from ngts.nvos_tools.infra.BaseComponent import BaseComponent

logger = logging.getLogger()


class Ib(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj,
                               api={ApiType.NVUE: NvueOpenSmCli, ApiType.OPENAPI: OpenApiOpenSmCli}, path='/ib')
        self.ibdiagnet = Ibdiagnet(self)
        self.sm = Sm(self)
        self.device = BaseComponent(self, path='/device')
        self.router = IbRouter(self)


class IbRouter(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj,
                               api={ApiType.NVUE: NvueOpenSmCli, ApiType.OPENAPI: OpenApiOpenSmCli}, path='/router')
        self.routing_table = BaseComponent(self, path='/routing-table')
        self.ib_subnet = BaseComponent(self, path='/ib-subnet')

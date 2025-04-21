import logging

from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.nmx.App import App
from ngts.nvos_tools.nmx.Config import Config
from ngts.nvos_tools.nmx.State import State
from ngts.nvos_tools.nmx.Partition import Partition
from ngts.nvos_tools.nmx.FactoryDefault import FactoryDefault
from ngts.nvos_tools.nmx.Transceivers import Transceivers

logger = logging.getLogger()


class Sdn(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/sdn')
        self.config = Config(self)
        self.state = State(self)
        self.partition = Partition(self)
        self.factory_default = FactoryDefault(self)
        self.transceivers = Transceivers(self)

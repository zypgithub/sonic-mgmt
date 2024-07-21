from typing import Dict

import logging
import allure
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.nmx.Loglevel import Loglevel
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool

logger = logging.getLogger()


class Uuid(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/uuid')
        self.uuid_value: Dict[str, UuidVal] = DefaultDict(
            lambda uuid_value: AppsName(parent=self, uuid_value=uuid_value))


class UuidVal(BaseComponent):
    def __init__(self, parent, uuid_value):
        super().__init__(parent=parent, path=f'/{uuid_value}')

import allure
import logging

from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.system.Files import File, Files
from ngts.nvos_tools.nmx.App import App
from ngts.nvos_tools.nmx.Config import Config
from ngts.nvos_tools.nmx.State import State
from ngts.nvos_tools.nmx.Partition import Partition
from ngts.nvos_tools.nmx.FactoryDefault import FactoryDefault
from ngts.nvos_tools.nmx.Transceivers import Transceivers
from ngts.nvos_tools.nmx.Trays import Trays

logger = logging.getLogger()


class SdnCmdFiles(Files):
    """``nv show sdn cmd files`` / per-file show & delete; reuses ``Files`` helpers where they apply."""

    def __init__(self, parent_obj=None):
        BaseComponent.__init__(
            self,
            parent=parent_obj,
            api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
            path='/cmd/files',
        )
        self.file_name = DefaultDict(lambda fname: File(self, filename=fname))


class Sdn(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/sdn')
        self.cmd_files = SdnCmdFiles(self)
        self.config = Config(self)
        self.state = State(self)
        self.partition = Partition(self)
        self.factory_default = FactoryDefault(self)
        self.transceivers = Transceivers(self)
        self.trays = Trays(self)

    def action_run_cmd(self, sdn_cmd_str, dut_engine=None, exempted_err_msgs=()):
        engine = dut_engine or TestToolkit.get_engine()
        # OpenAPI: POST .../sdn/cmd. Do not change Sdn.get_resource_path() globally — children need /sdn/config, etc.
        resource_path = self.get_resource_path()
        if self._api_to_use == ApiType.OPENAPI:
            resource_path = resource_path.rstrip("/") + "/cmd"
        with allure.step("Execute run sdn cmd"):
            return SendCommandTool.execute_command(self._cli_wrapper.action_run_sdn_cmd, engine,
                                                   resource_path, sdn_cmd_str, exempted_err_msgs=exempted_err_msgs)

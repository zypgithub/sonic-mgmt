from ast import Dict
import logging

from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit


logger = logging.getLogger()


class Node(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/node',
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli})
        self.primary = Primary(self)
        self.secondary = Secondary(self)


class Primary(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/primary',
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli})

    def set_cluster_node(self, op_param_name="", op_param_value={}, expected_str='', apply=False, ask_for_confirmation=False,
                         dut_engine=None):
        _set_cluster_node(self, op_param_name=op_param_name, op_param_value=op_param_value, expected_str=expected_str, apply=apply, ask_for_confirmation=ask_for_confirmation,
                          dut_engine=dut_engine)


class Secondary(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/secondary',
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli})

    def set_cluster_node(self, op_param_name="", op_param_value={}, expected_str='', apply=False, ask_for_confirmation=False,
                         dut_engine=None):
        _set_cluster_node(self, op_param_name=op_param_name, op_param_value=op_param_value, expected_str=expected_str, apply=apply, ask_for_confirmation=ask_for_confirmation,
                          dut_engine=dut_engine)


def _set_cluster_node(self, op_param_name="", op_param_value={}, expected_str='', apply=False, ask_for_confirmation=False,
                      dut_engine=None):
    if not dut_engine:
        dut_engine = TestToolkit.get_engine()

    if TestToolkit.tested_api == ApiType.OPENAPI:
        openapi_value = {op_param_value: {}}
        self.set(op_param_name, openapi_value, expected_str=expected_str, apply=apply,
                 ask_for_confirmation=ask_for_confirmation, dut_engine=dut_engine)
    else:
        self.set(op_param_name, op_param_value, expected_str=expected_str, apply=apply,
                 ask_for_confirmation=ask_for_confirmation, dut_engine=dut_engine)

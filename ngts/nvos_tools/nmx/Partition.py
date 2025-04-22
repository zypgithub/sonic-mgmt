import logging
from typing import Dict

import allure

from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.nmx.Location import Location
from ngts.nvos_tools.nmx.Uuid import Uuid

logger = logging.getLogger()


class Partition(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj,
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli},
                         path='/partition')
        self.partition_id: Dict[str, PartitionId] = DefaultDict(
            lambda partition_id: PartitionId(parent=self, partition_id=partition_id))

    def action_delete_partition(self, engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Delete partition'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_delete,
                                                                "Action succeeded", engine,
                                                                self.get_resource_path())


class PartitionId(BaseComponent):
    def __init__(self, parent, partition_id):
        super().__init__(parent=parent, path=f'/{partition_id}')
        self.location = Location(self)
        self.uuid = Uuid(self)

    def action_create_partition_id(self, name, resiliency_mode, mcast_limit, uuid='', location='', engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Create partition'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_create_partition,
                                                                "successfully created", engine,
                                                                self.get_resource_path(), name, resiliency_mode, mcast_limit, uuid, location)

    def action_update_partition(self, engine=None, reroute=''):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Update partition'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_update_partition,
                                                                "successfully updated", engine,
                                                                self.get_resource_path(), reroute)

    def action_restore_partition(self, engine=None, no_reroute=''):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Restore partition'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_restore_partition,
                                                                "Action succeeded", engine,
                                                                self.get_resource_path(), no_reroute)

    def action_delete_partition(self, engine=None):
        engine = engine if engine else TestToolkit.engines.dut
        with allure.step('Delete partition'):
            return SendCommandTool.execute_command_expected_str(self._cli_wrapper.action_delete,
                                                                "Action succeeded", engine,
                                                                self.get_resource_path())

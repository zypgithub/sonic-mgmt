from ast import Dict
import logging

from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
import ngts.tools.test_utils.allure_utils as allure

from ngts.cli_wrappers.nvue.nvue_cluster_clis import NvueClusterCli
from ngts.cli_wrappers.openapi.openapi_cluster_clis import OpenApiClusterCli
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool

logger = logging.getLogger()


class RbacFiles(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/file',
                         api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli})

    def show_files(self, dut_engine=None):
        with allure.step("Get files"):
            files = OutputParsingTool.parse_json_str_to_dictionary(
                self.show(dut_engine=dut_engine)).get_returned_value()
            return files


class RbacFile(BaseComponent):
    def __init__(self, parent=None, rbac_id=''):
        super().__init__(parent=parent, path=f'/file/{rbac_id}', api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli})
        self.rbac_id = rbac_id

    def action_import(self, import_path: str, dut_engine=None, should_succeed: bool = True) -> bool:
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        resource_path = self.get_resource_path()
        with allure.step(f"Import file {resource_path} from '{import_path}'"):
            return SendCommandTool.execute_command(self._cli_wrapper.action_import_rbac_file, engine=engine, resource_path=resource_path, remote_url=import_path)

    def action_delete(self, dut_engine=None, should_succeed: bool = True) -> bool:
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        resource_path = self.get_resource_path()
        with allure.step(f"Delete file: {resource_path} with name: {self.rbac_id}"):
            return SendCommandTool.execute_command(self._cli_wrapper.action_delete_rbac_file, engine, resource_path)


class Rbac(BaseComponent):
    def __init__(self, parent_obj):
        super().__init__(parent=parent_obj, path='/rbac',
                         api={ApiType.NVUE: NvueClusterCli,
                              ApiType.OPENAPI: OpenApiClusterCli})
        self.files = RbacFiles(self)
        self.file: Dict[str, RbacFile] = DefaultDict(lambda rbac_id: RbacFile(self, rbac_id=rbac_id))


class RbacAppFile(BaseComponent):
    def __init__(self, parent=None):
        super().__init__(parent=parent, path='/file', api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli})

    def action_update(self, file_name: str, dut_engine=None, should_succeed: bool = True) -> bool:
        """nv action update cluster apps <app-name> rbac file <rbac-id>"""
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        resource_path = self.get_resource_path()
        with allure.step(f"Update cluster app RBAC file: {resource_path}"):
            return SendCommandTool.execute_command(self._cli_wrapper.action_update_cluster_manager_property, engine,
                                                   resource_path, 'rbac_id', file_name)

    def action_restore(self, dut_engine=None, should_succeed: bool = True) -> bool:
        """nv action restore cluster apps <app-name> rbac file"""
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        restore_path = self.get_resource_path()
        with allure.step(f"Restore cluster app RBAC file settings for app: {restore_path}"):
            return SendCommandTool.execute_command(self._cli_wrapper.action_restore_cluster_manager_property, engine,
                                                   restore_path)


class RbacAppMode(BaseComponent):
    def __init__(self, parent=None):
        super().__init__(parent=parent, path='/mode', api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli})

    def action_update(self, mode: str, dut_engine=None, should_succeed: bool = True) -> bool:
        """nv action update cluster apps <app-name> rbac mode <mode>"""
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        resource_path = self.get_resource_path()
        with allure.step(f"Update cluster app RBAC mode to '{mode}': {resource_path}"):
            return SendCommandTool.execute_command(self._cli_wrapper.action_update_cluster_manager_property, engine,
                                                   resource_path, 'mode', mode)

    def action_restore(self, dut_engine=None, should_succeed: bool = True) -> bool:
        """nv action restore cluster apps <app-name> rbac mode"""
        engine = dut_engine if dut_engine else TestToolkit.engines.dut
        resource_path = self.get_resource_path()
        with allure.step(f"Restore cluster app RBAC mode: {resource_path}"):
            return SendCommandTool.execute_command(self._cli_wrapper.action_restore_cluster_manager_property, engine,
                                                   resource_path)


class RbacApp(BaseComponent):
    def __init__(self, parent_obj):
        super().__init__(parent=parent_obj, path='/rbac', api={ApiType.NVUE: NvueClusterCli, ApiType.OPENAPI: OpenApiClusterCli})
        self.file = RbacAppFile(self)
        self.mode = RbacAppMode(self)

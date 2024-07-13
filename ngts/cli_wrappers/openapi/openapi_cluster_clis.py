import logging

from ngts.cli_wrappers.openapi.openapi_base_clis import OpenApiBaseCli
from ngts.nvos_constants.constants_nvos import ActionType
from .openapi_command_builder import OpenApiCommandHelper

logger = logging.getLogger()


class OpenApiClusterCli(OpenApiBaseCli):

    def __init__(self):
        self.cli_name = "Cluster"

    @staticmethod
    def action_start_cluster_app(engine, resource_path):
        return OpenApiClusterCli.action(engine, action_type=ActionType.START.value, resource_path=resource_path)

    @staticmethod
    def action_stop_cluster_app(engine, resource_path):
        return OpenApiClusterCli.action(engine, action_type=ActionType.STOP.value, resource_path=resource_path)

    @staticmethod
    def action_update_cluster_log_level(engine, resource_path, level):
        param_name = "level"
        param_value = level
        return OpenApiClusterCli.action(engine, action_type=ActionType.UPDATE.value, resource_path=resource_path, param_name=param_name, param_value=param_value)

    @staticmethod
    def action_restore_cluster(engine, resource_path):
        return OpenApiClusterCli.action(engine, action_type=ActionType.RESTORE.value, resource_path=resource_path)

    @staticmethod
    def action_generate(engine, resource_path):
        return OpenApiClusterCli.action(engine, action_type=ActionType.GENERATE.value, resource_path=resource_path)

    @staticmethod
    def action_fetch(engine, resource_path, remote_url):
        param_name = "url"
        param_value = remote_url
        return OpenApiClusterCli.action(engine, action_type=ActionType.FETCH.value, resource_path=resource_path, param_name=param_name, param_value=param_value)

    @staticmethod
    def action_update_cluster_manager_property(engine, resource_path, param_name='', param_val=''):
        logging.info(f'Run action import on: {resource_path} using OpenApi')
        parameters = {} if not param_name and not param_val else {param_name: param_val}
        params = \
            {
                "state": "start",
                "parameters": parameters
            }
        return OpenApiCommandHelper.execute_action(ActionType.UPDATE, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

    @staticmethod
    def action_restore_cluster_manager_property(engine, resource_path):
        logging.info(f'Run action delete on: {resource_path} using OpenApi')
        params = \
            {
                "state": "start",
                "parameters": {}
            }
        return OpenApiCommandHelper.execute_action(ActionType.RESTORE, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

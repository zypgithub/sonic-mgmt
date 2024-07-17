import logging

from ngts.cli_wrappers.openapi.openapi_base_clis import OpenApiBaseCli
from ngts.nvos_constants.constants_nvos import ActionType
from .openapi_command_builder import OpenApiCommandHelper

logger = logging.getLogger()


class OpenApiClusterCli(OpenApiBaseCli):

    def __init__(self):
        self.cli_name = "Cluster"

    @staticmethod
    def action_start_cluster_apps(engine, resource_path):
        return OpenApiClusterCli.action(engine, action_type=ActionType.START.replace('@', ''), resource_path=resource_path)

    @staticmethod
    def action_stop_cluster_apps(engine, resource_path):
        return OpenApiClusterCli.action(engine, action_type=ActionType.STOP.replace('@', ''), resource_path=resource_path)

    @staticmethod
    def action_update_cluster_log_level(engine, resource_path, level):
        param_name = "level"
        param_value = level
        return OpenApiClusterCli.action(engine, action_type=ActionType.UPDATE.replace('@', ''), resource_path=resource_path, param_name=param_name, param_value=param_value)

    @staticmethod
    def action_restore_cluster(engine, resource_path):
        return OpenApiClusterCli.action(engine, action_type=ActionType.RESTORE.replace('@', ''), resource_path=resource_path)

    @staticmethod
    def action_generate(engine, resource_path):
        return OpenApiClusterCli.action(engine, action_type=ActionType.GENERATE.replace('@', ''), resource_path=resource_path)

    @staticmethod
    def action_fetch(engine, resource_path, remote_url):
        param_name = "url"
        param_value = remote_url
        return OpenApiClusterCli.action(engine, action_type=ActionType.FETCH.replace('@', ''), resource_path=resource_path, param_name=param_name, param_value=param_value)

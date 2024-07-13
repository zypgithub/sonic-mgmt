from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli, check_output
from ngts.cli_wrappers.sonic.sonic_general_clis import *
from ngts.nvos_constants.constants_nvos import ActionType

logger = logging.getLogger()
server_ip = "10.237.116.60"


class NvueClusterCli(NvueBaseCli):

    """
    This class is for general cli commands for NVOS only
    """

    def __init__(self):
        self.cli_name = "Cluster"

    @staticmethod
    def action_start_cluster_app(engine, path):
        return NvueClusterCli.action(engine, action_type=ActionType.START.value, resource_path=path)

    @staticmethod
    def action_stop_cluster_app(engine, path):
        return NvueClusterCli.action(engine, action_type=ActionType.STOP.value, resource_path=path)

    @staticmethod
    def action_update_cluster_log_level(engine, path, level=''):
        return NvueClusterCli.action(engine, action_type=ActionType.UPDATE.value, resource_path=path, param_value=level)

    @staticmethod
    def action_restore_cluster(engine, path):
        return NvueClusterCli.action(engine, action_type=ActionType.RESTORE.value, resource_path=path)

    @staticmethod
    @check_output
    def action_generate(engine, resource_path):
        return NvueClusterCli.action(engine, action_type=ActionType.GENERATE.value, resource_path=resource_path)

    @staticmethod
    def action_fetch(engine, resource_path, remote_url):
        return NvueClusterCli.action(engine, action_type=ActionType.FETCH.value, resource_path=resource_path, param_value=remote_url)

    @staticmethod
    @check_output
    def action_update_cluster_manager_property(engine, resource_path, param_name='', param_val=''):
        path = resource_path.replace('/', ' ').strip()
        cmd = f'nv action {ActionType.UPDATE.value} {path} {param_val}'.strip()
        logging.info(f"Running action cmd: '{cmd}' on dut using NVUE")
        return engine.run_cmd(cmd)

    @staticmethod
    @check_output
    def action_restore_cluster_manager_property(engine, resource_path):
        path = resource_path.replace('/', ' ').strip()
        cmd = f'nv action {ActionType.RESTORE.value} {path}'
        logging.info(f"Running action cmd: '{cmd}' on dut using NVUE")
        return engine.run_cmd(cmd)

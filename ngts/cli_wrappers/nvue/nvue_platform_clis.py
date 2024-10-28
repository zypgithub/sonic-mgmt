import logging

from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli, check_output
from ngts.nvos_constants.constants_nvos import ActionType

logger = logging.getLogger()


class NvuePlatformCli(NvueBaseCli):

    def __init__(self):
        self.cli_name = "Platform"

    def action_generate(engine, resource_path, name=""):
        return NvuePlatformCli.action(engine, action_type=ActionType.GENERATE.replace('@', ''), resource_path=resource_path, param_value=name)

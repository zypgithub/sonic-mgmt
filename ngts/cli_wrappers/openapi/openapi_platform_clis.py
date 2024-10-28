import logging

from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.cli_wrappers.openapi.openapi_base_clis import OpenApiBaseCli
from ngts.nvos_constants.constants_nvos import ActionType
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from .openapi_command_builder import OpenApiCommandHelper

logger = logging.getLogger()


class OpenApiPlatformCli(OpenApiBaseCli):

    def __init__(self):
        self.cli_name = "Platform"

    def action_generate(engine, resource_path, file_name=''):
        logging.info("Running action: 'generate' on dut using OpenApi")
        params = \
            {
                "state": "start",
            }
        if file_name:
            params["parameters"] = {'new-name': file_name}
        return OpenApiCommandHelper.execute_action(ActionType.GENERATE, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

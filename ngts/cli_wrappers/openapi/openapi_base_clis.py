import logging

from ngts.nvos_constants.constants_nvos import OpenApiReqType, SystemConsts
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from .openapi_command_builder import OpenApiCommandHelper

logger = logging.getLogger()


class OpenApiBaseCli:
    cli_name = ""

    @staticmethod
    def show(engine, resource_path, op_param="", output_format=OutputFormat.json):
        logging.info("Running GET method on dut using openApi for {}".format(resource_path))
        return OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password,
                                                   OpenApiReqType.GET, engine.ip, resource_path, op_param)

    @staticmethod
    def set(engine, resource_path, op_param_name="", op_param_value=""):
        logging.info("Running PATCH method on dut using openApi for {}".format(resource_path))
        return OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password,
                                                   OpenApiReqType.PATCH, engine.ip, resource_path, op_param_name,
                                                   op_param_value)

    @staticmethod
    def unset(engine, resource_path, op_param=""):
        logging.info("Running DELETE method on dut using openApi for {}".format(resource_path))
        return OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password,
                                                   OpenApiReqType.DELETE, engine.ip, resource_path, op_param, None)

    @staticmethod
    def _resource_path_to_rest_path(resource_path: str, suffix=''):
        output = resource_path.replace(' ', '/')
        if suffix:
            output += '/' + suffix.replace('/', '%2F').replace(' ', '/')
        return output

    @staticmethod
    def _action_key(action: str):
        return '@' + action

    @staticmethod
    def action(engine, device=None, action_type='', resource_path='', suffix="", param_name="", param_value="",
               output_format=None, expect_reboot=False, recovery_engine=None):
        """See documentation of BaseComponent.action"""
        if not action_type:
            raise ValueError("action_type must be non-empty")
        if not resource_path:
            raise ValueError("resource_path must be non-empty")

        url = OpenApiBaseCli._resource_path_to_rest_path(resource_path, suffix)
        data = {'state': 'start'}
        if param_name:
            data['parameters'] = {param_name: (True if (param_value == '') else param_value)}
        result = OpenApiCommandHelper.execute_action(
            OpenApiBaseCli._action_key(action_type), engine.engine.username, engine.engine.password, engine.ip,
            url, data)

        if ((expect_reboot or any(msg in result for msg in SystemConsts.REBOOT_RESPONSE_MESSAGES)) and
                "abort" not in result):
            DutUtilsTool.wait_on_system_reboot(engine, recovery_engine)

        return result

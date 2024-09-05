import logging

from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.cli_wrappers.openapi.openapi_base_clis import OpenApiBaseCli
from ngts.nvos_constants.constants_nvos import ActionType, SystemConsts
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from .openapi_command_builder import OpenApiCommandHelper

logger = logging.getLogger()


class OpenApiSystemCli(OpenApiBaseCli):

    def __init__(self):
        self.cli_name = "System"

    @staticmethod
    def action_image(engine, action_str, action_component_str, op_param=""):
        logging.info("Running image action: '{action_type}' on dut using OpenApi".format(action_type=action_str))
        action_type = '@' + action_str
        params = \
            {
                ActionType.BOOT_NEXT:
                    {
                        "state": "start",
                        "parameters": {"partition": op_param}
                    },
                ActionType.UNINSTALL:
                    {
                        "state": "start",
                        "parameters": {"force": True if op_param == "force" else False}
                    },
                ActionType.FETCH:
                    {
                        "state": "start",
                        "parameters": {"remote-url": op_param}
                    }
            }
        return OpenApiCommandHelper.execute_action(action_type, engine.engine.username, engine.engine.password,
                                                   engine.ip, action_component_str, params[action_type])

    @staticmethod
    def action_general(engine, action_str, resource_path):
        logging.info("Running action: '{action_type}' on dut using OpenApi, resource: '{rsrc}'".
                     format(action_type=action_str, rsrc=resource_path))
        action_type = '@' + action_str
        params = \
            {
                ActionType.CLEAR:
                    {
                        "state": "start"
                    },
                ActionType.GENERATE:
                    {
                        "state": "start",
                    },
                ActionType.ENABLE:
                    {
                        "state": "start",
                    },
                ActionType.DISABLE:
                    {
                        "state": "start",
                    }
            }
        return OpenApiCommandHelper.execute_action(action_type, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params[action_type])

    @staticmethod
    def action_general_with_expected_disconnect(engine, action_str, resource_path):
        logging.info("Running action: '{action_type}' on dut using OpenApi, resource: '{rsrc}'".
                     format(action_type=action_str, rsrc=resource_path))
        action_type = '@' + action_str
        params = \
            {
                ActionType.CLEAR:
                    {
                        "state": "start"
                    },
                ActionType.GENERATE:
                    {
                        "state": "start",
                    },
                ActionType.ENABLE:
                    {
                        "state": "start",
                    },
                ActionType.DISABLE:
                    {
                        "state": "start",
                    }
            }
        output = OpenApiCommandHelper.execute_action(action_type, engine.engine.username, engine.engine.password,
                                                     engine.ip, resource_path, params[action_type])
        engine.disconnect()
        return output

    @staticmethod
    def action_generate_techsupport(engine, resource_path, field, value):
        logging.info("Running action: 'generate' on dut using OpenApi")

        params = \
            {
                "state": "start",
                "parameters": {
                    "since": value
                }
            }

        return OpenApiCommandHelper.execute_action(ActionType.GENERATE, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

    @staticmethod
    def action_delete(engine, resource_path, file_name):
        logging.info("Running action: 'delete' on dut using OpenApi")
        params = \
            {
                "state": "start",
                "parameters": {
                    'file-name': file_name,
                }
            }
        return OpenApiCommandHelper.execute_action(ActionType.DELETE, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

    @staticmethod
    def action_generate_tpm_quote(engine, resource_path, pcrs='', nonce='', algorithm=''):
        logging.info("Running action: 'generate' on dut using OpenApi")
        parameters = {'pcrs': pcrs, 'nonce': nonce}
        if algorithm:
            parameters['algorithm'] = algorithm
        params = \
            {
                "state": "start",
                "parameters": parameters
            }
        return OpenApiCommandHelper.execute_action(ActionType.GENERATE, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

    @staticmethod
    def action_upload_tpm_file(engine, resource_path, file_name, remote_url):
        logging.info("Running action: 'upload' on dut using OpenApi")
        params = \
            {
                "state": "start",
                "parameters": {
                    'file-name': file_name,
                    'remote-url': remote_url
                }
            }
        return OpenApiCommandHelper.execute_action(ActionType.UPLOAD, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

    @staticmethod
    def action_reset(engine, device, comp, param):
        logging.info("Running action: reset system {} on dut using OpenApi".format(comp))

        assert not param, "params are not supported yet"

        params = {}

        return OpenApiCommandHelper.execute_action(ActionType.RESET, engine.engine.username, engine.engine.password,
                                                   engine.ip, "/system/{}".format(comp), params)

    @staticmethod
    def action_rotate_logs(engine):
        logging.info("Running action: rotate system log on dut using OpenApi")
        params = \
            {
                "state": "start",
            }
        return OpenApiCommandHelper.execute_action(ActionType.ROTATE, engine.engine.username, engine.engine.password,
                                                   engine.ip, "/system/log", params)

    @staticmethod
    def action_reboot(engine, device, resource_path, op_param="", should_wait_till_system_ready=True, recovery_engine=None):
        logging.info("Running action: rotate system log on dut using OpenApi")
        parameters_dict = {}
        if "force" in op_param:
            parameters_dict.update({"force": True})
        if "immediate" in op_param:
            parameters_dict.update({"immediate": True})
        if "proceed" in op_param:
            parameters_dict.update({"proceed": True})
        params = \
            {
                "state": "start"
            }
        if parameters_dict:
            params.update({"parameters": parameters_dict})
        result = OpenApiCommandHelper.execute_action(ActionType.REBOOT, engine.engine.username, engine.engine.password,
                                                     engine.ip, resource_path, params)
        if any(msg in result for msg in SystemConsts.REBOOT_RESPONSE_MESSAGES):
            logger.info("Waiting for switch shutdown after reload command")
            check_port_status_till_alive(False, engine.ip, engine.ssh_port)
            engine.disconnect()
            logger.info("Waiting for switch to be ready")
            check_port_status_till_alive(True, engine.ip, engine.ssh_port)

        if should_wait_till_system_ready:
            device.wait_for_os_to_become_functional(recovery_engine or engine).verify_result()
        return result

    @staticmethod
    def action_change(engine, resource_path, params_dict=None):
        logging.info("Running action: 'change' on dut using OpenApi, resource: {rsrc}".format(rsrc=resource_path))

        params = \
            {
                "state": "start",
                "parameters": params_dict
            }

        return OpenApiCommandHelper.execute_action(ActionType.CHANGE, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

    @staticmethod
    def show_file(engine, file='', exit_cmd=''):
        # TODO not supported yet
        return ""

    @staticmethod
    def action_clear(engine, resource_path, params_dict=None):
        logging.info("Running action: 'clear' on dut using OpenApi, resource: {rsrc}".format(rsrc=resource_path))

        params = \
            {
                "state": "start",
                "parameters": params_dict
            }

        return OpenApiCommandHelper.execute_action(ActionType.CLEAR, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

    @staticmethod
    def action_profile_change(engine, device, resource_path, params_dict=None, should_wait_till_system_ready=True):
        logging.info("Running action: 'profile change' on dut using OpenApi, resource: {rsrc}"
                     .format(rsrc=resource_path))

        params = \
            {
                "state": "start",
                "parameters": params_dict
            }

        result = OpenApiCommandHelper.execute_action(ActionType.CHANGE, engine.engine.username, engine.engine.password,
                                                     engine.ip, resource_path, params)

        if "System will be rebooted" in result:
            logger.info("Waiting for switch shutdown after reload command")
            check_port_status_till_alive(False, engine.ip, engine.ssh_port)
            engine.disconnect()
            logger.info("Waiting for switch to be ready")
            check_port_status_till_alive(True, engine.ip, engine.ssh_port)

        if should_wait_till_system_ready:
            DutUtilsTool.wait_for_nvos_to_become_functional(engine).verify_result()

    @staticmethod
    def action_import_certificate(engine, resource_path, data='', passphrase='', uri_bundle='', uri_private_key='', uri_public_key=''):
        logging.info(f'Run action import on: {resource_path} using OpenApi')
        parameters = {'data': data, 'passphrase': passphrase, 'uri-bundle': uri_bundle, 'uri-private-key': uri_private_key,
                      'uri-public-key': uri_public_key}
        parameters = {param: val for param, val in parameters.items() if val}
        params = \
            {
                "state": "start",
                "parameters": parameters
            }
        return OpenApiCommandHelper.execute_action(ActionType.IMPORT, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

    @staticmethod
    def action_import_ca_certificate(engine, resource_path, data='', uri=''):
        logging.info(f'Run action import on: {resource_path} using OpenApi')
        parameters = {'data': data, 'uri': uri}
        parameters = {param: val for param, val in parameters.items() if val}
        params = \
            {
                "state": "start",
                "parameters": parameters
            }
        return OpenApiCommandHelper.execute_action(ActionType.IMPORT, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

    @staticmethod
    def action_delete_certificate(engine, resource_path):
        logging.info(f'Run action delete on: {resource_path} using OpenApi')
        params = \
            {
                "state": "start",
                "parameters": {}
            }
        return OpenApiCommandHelper.execute_action(ActionType.DELETE, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

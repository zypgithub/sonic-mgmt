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

    @staticmethod
    def action_install_fae_bios_firmware(engine, bios_image_path, resource_path='', device=None):
        """
        Method to install BIOS firmware using rest api
        :param engine: the engine to use
        :param bios_image_path: the path to the BIOS firmware image
        :param resource_path: path (example : /fae/platform/firmware/)
        :param device: Noga device info
        """
        resource_path = resource_path + '/bios/files/' + bios_image_path.replace('/', '%2F')

        action_type = ActionType.INSTALL
        params = \
            {
                "state": "start",
                "parameters": {"force": True}
            }
        logging.info("Running action: '{action_type}' on dut using OpenApi".format(action_type=action_type))
        result = OpenApiCommandHelper.execute_action(action_type, engine.engine.username, engine.engine.password,
                                                     engine.ip, resource_path, params, expected_regex="Installing firmware")

        logger.info("Waiting for switch shutdown after reload command")
        check_port_status_till_alive(False, engine.ip, engine.ssh_port)
        engine.disconnect()
        logger.info("Waiting for switch to be ready")
        check_port_status_till_alive(True, engine.ip, engine.ssh_port)

        DutUtilsTool.wait_for_nvos_to_become_functional(engine).verify_result()

        return result

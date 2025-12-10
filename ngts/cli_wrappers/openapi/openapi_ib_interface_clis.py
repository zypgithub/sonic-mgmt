import logging
from ngts.cli_wrappers.openapi.openapi_base_clis import OpenApiBaseCli
from .openapi_command_builder import OpenApiCommandHelper
from ngts.nvos_constants.constants_nvos import OutputFormat, OpenApiReqType
from ngts.nvos_constants.constants_nvos import ActionType


class OpenApiIbInterfaceCli(OpenApiBaseCli):

    def __init__(self):
        self.cli_name = "interface"

    @staticmethod
    def clear_stats(engine, port_name, fae_param=""):
        """
        Clears the interface counters
        :param engine: ssh engine object
        :param port_name: the name of the port/ports
        :param fae_param: optional - run the command with fae
        """
        resource_path = f'/interface/{port_name}/counters'
        logging.info("Running action: 'clear' on dut using OpenApi, resource: {rsrc}".format(rsrc=resource_path))
        params = {
            "state": "start",
        }

        return OpenApiCommandHelper.execute_action(ActionType.CLEAR, engine.engine.username, engine.engine.password,
                                                   engine.ip, engine.open_api_port, resource_path, params)

    @staticmethod
    def show_interface(engine, port_name, interface_hierarchy="", fae_param="", output_format=OutputFormat.json):
        """
        Displays the configuration and the status of the interface
        :param engine: ssh engine object
        :param port_name: the name of the port/ports
        :param interface_hierarchy: the show level
        :param fae_param: optional - to command with fae
        :param output_format: format of the output: auto(table), json or yaml. OutputFormat object is expected
        :return: output str
        """
        resource_path = interface_hierarchy.replace(' ', '/')

        return OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password, OpenApiReqType.GET,
                                                   engine.ip, engine.open_api_port,
                                                   '/{fae}interface{interface_id}{resource_path}'.format(
                                                       fae=fae_param + "/" if fae_param else '',
                                                       interface_id="/" + port_name if port_name else '',
                                                       resource_path="/" + resource_path if resource_path else ''))

    @staticmethod
    def action_clear_counters(engine, resource_path, fae_param='', params_dict=None):
        resource_path = '/' + resource_path
        logging.info("Running action: 'clear' on dut using OpenApi, resource: {rsrc}".format(rsrc=resource_path))
        params = {
            "state": "start",
            "parameters":
            {
                "counters": "counters"
            }
        }

        return OpenApiCommandHelper.execute_action(ActionType.CLEAR, engine.engine.username, engine.engine.password,
                                                   engine.ip, engine.open_api_port, resource_path, params)

    @staticmethod
    def filter(engine, filter_name, value):
        params = f'?filter={filter_name}%3d{value}' if filter_name else ''

        return OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password, OpenApiReqType.GET,
                                                   engine.ip, engine.open_api_port, '/interface', params)

    @staticmethod
    def action_renew_dhcp_client(engine, resource_path):
        """
        Renew DHCP client for the specified interface
        :param engine: ssh engine object
        :param resource_path: the path of the interface
        """
        logging.info(f"Running action: {ActionType.RENEW[1:]} on dut using OpenApi, resource: {resource_path}")
        params = {
            "state": "start",
        }

        return OpenApiCommandHelper.execute_action(ActionType.RENEW, engine.engine.username, engine.engine.password,
                                                   engine.ip, engine.open_api_port, resource_path, params)

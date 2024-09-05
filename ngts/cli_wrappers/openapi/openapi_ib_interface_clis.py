import logging
from ngts.cli_wrappers.openapi.openapi_base_clis import OpenApiBaseCli
from .openapi_command_builder import OpenApiCommandHelper
from ngts.nvos_constants.constants_nvos import OutputFormat, OpenApiReqType
from ngts.nvos_constants.constants_nvos import ActionType


class OpenApiIbInterfaceCli(OpenApiBaseCli):

    def __init__(self):
        self.cli_name = "interface"

    @staticmethod
    def clear_stats(engine, port_name):
        """
        Clears the interface counters
        :param engine: ssh engine object
        :param port_name: the name of the port/ports
        """
        assert "Not implemented"

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
                                                   engine.ip,
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
                "clear-target": "counters"
            }
        }

        return OpenApiCommandHelper.execute_action(ActionType.CLEAR, engine.engine.username, engine.engine.password,
                                                   engine.ip, resource_path, params)

    @staticmethod
    def action_recover(engine, port_name, comp):
        return OpenApiCommandHelper.execute_action("recover", engine.engine.username, engine.engine.password,
                                                   engine.ip, '/interface{interface_id}{resource_path}'.format(
                                                       interface_id="/" + port_name if port_name else '',
                                                       resource_path="/" + comp))

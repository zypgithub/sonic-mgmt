import logging
from ngts.cli_wrappers.openapi.openapi_base_clis import OpenApiBaseCli
from .openapi_command_builder import OpenApiCommandHelper
from ngts.nvos_constants.constants_nvos import OutputFormat, OpenApiReqType
from ngts.nvos_constants.constants_nvos import ActionType


class OpenApiPeerPortCli(OpenApiBaseCli):

    def __init__(self):
        self.cli_name = "peer-port"

    @staticmethod
    def show_peer_port(engine, peer_port_name, fae_param="", output_format=OutputFormat.json):
        """
        Displays the configuration and the status of the interface
        :param engine: ssh engine object
        :param port_name: the name of the port/ports
        :param fae_param: optional - to command with fae
        :param output_format: format of the output: auto(table), json or yaml. OutputFormat object is expected
        :return: output str
        """

        return OpenApiCommandHelper.execute_script(engine.engine.username, engine.engine.password, OpenApiReqType.GET,
                                                   engine.ip, engine.open_api_port,
                                                   '/{fae}peer-port{port_name}'.format(
                                                       fae=fae_param + "/" if fae_param else '',
                                                       port_name="/" + peer_port_name if peer_port_name else ''))

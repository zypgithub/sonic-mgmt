import logging
from typing import Dict

from retry import retry

from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import ActionConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.DefaultDict import DefaultDict

logger = logging.getLogger()


class Tunnel(BaseComponent):
    def __init__(self, parent, tunnel_name):
        super().__init__(parent=parent, path=f'/{tunnel_name}')
        self.tunnel_name = tunnel_name
        self.status = BaseComponent(self, path='/status')


class Server(BaseComponent):
    """Sub-component for 'nv show system grpc-tunnel server <tunnel_name>'"""

    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/server')
        self.tunnel_name: Dict[str, Tunnel] = DefaultDict(
            lambda tunnel_name: Tunnel(parent=self, tunnel_name=tunnel_name))

    def set_new_tunnel(self, tunnel_name="new_tunnel"):
        self.tunnel_name[tunnel_name].set().verify_result()
        return self.tunnel_name[tunnel_name]


class GrpcTunnel(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/grpc-tunnel')
        self.server = Server(self)

    def enable_grpc_tunnel_server(self, apply=True):
        return self.set(GnmiConsts.GNMI_STATE_FIELD, GnmiConsts.GNMI_STATE_ENABLED, apply=apply)

    def disable_grpc_tunnel_server(self, apply=True):
        return self.set(GnmiConsts.GNMI_STATE_FIELD, GnmiConsts.GNMI_STATE_DISABLED, apply=apply)

    def unset_grpc_tunnel_server(self, apply=True):
        return self.unset(apply=apply)

    def parsed_show_grpc_tunnel(self):
        return OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()

    @retry(Exception, tries=4, delay=3)
    def compare_show_grpc_tunnel_output(self, expected: Dict):
        show_output = self.parsed_show_grpc_tunnel()
        msg = ''
        for key in expected:
            if show_output[key] != expected[key]:
                msg += f"{key} field is different than expected: \n" \
                    f"Expected: {expected[key]}, but got: {show_output[key]}\n"
        assert not msg, f"The output of nv show system grpc-tunnel is different than expected:\n{msg}"

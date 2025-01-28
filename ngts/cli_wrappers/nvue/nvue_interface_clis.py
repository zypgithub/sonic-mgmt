from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.cli_wrappers.sonic.sonic_interface_clis import SonicInterfaceCli
import logging
import json


class NvueInterfaceCli(SonicInterfaceCli):
    """
    This class is for interface cli commands for NVOS/cumulus
    It extends SonicInterfaceCli for backwards compatability.
    """

    def __init__(self, engine, cli_obj, device=None):
        super().__init__(engine, cli_obj)
        self.engine = engine
        self.device = device
        self.cli_obj = cli_obj

    @staticmethod
    def _get_interface_mac_address(engine, interface):
        """
        Description :- Get interface mac address using the following command
        nv sh interface {interface} link -o json
        Args:
        interface :- interface name to find the mac address for.
        """
        cmd = f"nv sh interface {interface} link -o json"
        logging.info(f"Running {cmd}")
        output = engine.run_cmd(cmd)
        return output

    def get_interface_mac_address(self, interface, verify_execution=False):
        if verify_execution:
            output = SendCommandTool.execute_command(NvueInterfaceCli._get_interface_mac_address, self.engine, interface).verify_result()
        else:
            output = NvueInterfaceCli._get_interface_mac_address(self.engine, interface)
        output_json = json.loads(output)
        return output_json['mac-address']

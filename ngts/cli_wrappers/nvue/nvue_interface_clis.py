from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.cli_wrappers.sonic.sonic_interface_clis import SonicInterfaceCli
import logging
import json
import re
from ngts.constants.performance_constants import Cl_Consts


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
            try:
                output = SendCommandTool.execute_command(NvueInterfaceCli._get_interface_mac_address, self.engine, interface).verify_result()
            except Exception as e:
                logging.error(self.get_interface_status())
                logging.error(f"Error getting interface mac address for {interface}: {e}")
                raise
        else:
            output = NvueInterfaceCli._get_interface_mac_address(self.engine, interface)
        output_json = json.loads(output)
        return output_json['mac-address']

    def get_bonus_ports(self, engine) -> list:
        asic_model = self.cli_obj.general.get_asic_model(engine)
        bonus_ports = Cl_Consts.BONUS_PORTS[asic_model]
        logging.info(f"Bonus ports are {bonus_ports}")
        return bonus_ports

    def set_ports_admin_state(self, port_list: list, port_state):
        string_of_ports = ",".join(port_list)
        self.engine.run_cmd(f"nv set interface {string_of_ports} link state {port_state}")
        self.cli_obj.general.apply_config(self.engine, option="-y", verify_execution=True)

    def get_lldp_neighbors(self, output_type="json"):
        lldp_neighbors = self.engine.run_cmd(f"nv sh interface lldp -o {output_type}", print_output=False)
        try:
            lldp_neighbors = json.loads(lldp_neighbors)
        except json.JSONDecodeError as j:
            logging.error("Invalid lldp neighbor output received.")
            raise
        return lldp_neighbors

    def get_physical_ports(self):
        output = self.engine.run_cmd("nv sh platform -o json")
        output = json.loads(output)
        if output['product-name'] == 'SN5640':
            # for Spectrum 5 the number of ports is 66 but reported as 130
            return 66
        port_layout = output["port-layout"]
        port_number = re.findall(r'(\d+) x', port_layout)
        number_of_ports = sum(int(x) for x in port_number)
        return number_of_ports

    def initialize_physical_ports(self):
        number_of_ports = self.get_physical_ports()
        self.engine.run_cmd(f"nv unset interface swp1-{number_of_ports} link breakout")
        self.engine.run_cmd(f"nv set interface swp1-{number_of_ports} link breakout 1x")
        self.engine.run_cmd(f"nv set interface swp1-{number_of_ports} link state up")
        self.engine.run_cmd("nv config apply -y")

    def filter_lldp_neighbors(self, neighbor_list):
        lldp_neighbor = self.cli_obj.interface.get_lldp_neighbors(output_type="json")
        filtered_neighbors = {}
        for neighbor in neighbor_list:
            filtered_neighbors[neighbor] = []
        for port, properties in lldp_neighbor.items():
            neighbor = [*properties['lldp']['neighbor'].keys()][0]
            if neighbor in neighbor_list:
                filtered_neighbors[neighbor].append(port)
        return filtered_neighbors

    def get_down_ports(self):
        loopback_port = "lo"
        output = self.engine.run_cmd("nv sh interface down -o json")
        output = json.loads(output)
        down_ports = [*output.keys()]
        bonus_port = self.cli_obj.interface.get_bonus_ports(self.engine)
        for port in bonus_port:
            down_ports.pop(down_ports.index(port))
        try:
            down_ports.pop(down_ports.index(loopback_port))
        except ValueError:
            pass
        return down_ports

    def get_interface_status(self):
        output = self.engine.run_cmd("nv sh interface status -o json")
        output = json.loads(output)
        return output

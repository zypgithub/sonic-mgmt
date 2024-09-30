import logging
import time

from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.nvos_constants.constants_nvos import LinkDetectionConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.LinuxCmdBuilderTool import LinuxCmdBuilderTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RegisterTool import RegisterTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class IbInterfaceTool:

    @staticmethod
    def switch_port_connection_mode(port_name, connection_mode):
        with allure.step(f"Set connection-mode for {port_name} to {connection_mode}"):
            interface = Interface(parent_obj=None, port_name=port_name)
            interface.link.set(op_param_name=LinkDetectionConsts.CONNECTION_MODE,
                               op_param_value=connection_mode, apply=True,
                               ask_for_confirmation=True).verify_result()

    @staticmethod
    def switch_port_connection_mode_to_default(port_name):
        with allure.step(f"Set connection-mode for {port_name} default"):
            interface = Interface(parent_obj=None, port_name=port_name)
            interface.link.unset(op_param_name=LinkDetectionConsts.CONNECTION_MODE,
                                 apply=True, ask_for_confirmation=True).verify_result()

    @staticmethod
    def simulate_plugin_module_event(engine, device, module_index, mst_dev_name, sleep):
        with allure.step(f"Simulate plugin event for module {module_index}"):
            admin_status = "1"  # The code to simulate plug event
            RegisterTool.update_pmaos_register(engine, device, mst_dev_name=mst_dev_name,
                                               admin_status=admin_status, module_index=module_index)
            time.sleep(sleep)

    @staticmethod
    def simulate_unplug_module_event(engine, device, module_index, mst_dev_name, sleep):
        with allure.step(f"Simulate unplug event for module {module_index}"):
            admin_status = "0xe"  # The code to simulate unplug event
            RegisterTool.update_pmaos_register(engine, device, mst_dev_name=mst_dev_name,
                                               admin_status=admin_status, module_index=module_index)
            time.sleep(sleep)

    @staticmethod
    def simulate_toggle_port_event(engine, device, port_name, mst_dev_name, sleep):
        with allure.step(f"Simulate toggle port event for port {port_name}"):

            local_port_hex = IbInterfaceTool.get_local_port_hex(engine, port_name)
            RegisterTool.update_prei_register(engine, mst_dev_name=mst_dev_name, local_port=local_port_hex)
            time.sleep(sleep)

    @staticmethod
    def get_mst_dev_name(engines, asic_conf_dict, module_name=None, port_name=None):
        fae_port_name = f"{module_name}p1" if module_name else port_name
        fae = Fae(port_name=fae_port_name)

        with allure.step(f"Find correct mst_dev_name for {module_name or port_name}"):
            output_fae_port = OutputParsingTool.parse_show_interface_output_to_dictionary(
                fae.port.interface.show()).get_returned_value()
            asic_number = output_fae_port.get(IbInterfaceConsts.PRIMARY_ASIC, "0")
            assert asic_number is not None, "primary-asic is None"
            asic_dev_id_number = f"DEV_ID_ASIC_{asic_number}"
            asic_mapping_number = asic_conf_dict[asic_dev_id_number]
            cmd = LinuxCmdBuilderTool("sudo mst status -v").grep("pciconf").grep(f"{asic_mapping_number}").awk_print(
                "2").build()
            mst_dev_name = engines.dut.run_cmd(cmd)
            return mst_dev_name

    @staticmethod
    def get_local_port_hex(engine, input_str):
        """
        Retrieves the local port's hexadecimal value corresponding to a given input format.

        The function parses an input string in the format 'sw<label_port>p<port_index>'
        (e.g., 'sw18p1', 'swA1p1', 'swB3p2') and uses it to look up a table (provided as a string of port data)
        to find the corresponding local port's value. The local port's value is returned in hexadecimal.

        Args:
            input_str (str): Input in the format 'sw<label_port>p<port_index>',
                             where <label_port> is the port label number and <port_index> is the port index.
                             Example: 'sw18p1' refers to label port 18, first local port, and
                             'swA1p1' refers to label port A1, first local port.
            ports_data_str (str): A multi-line string containing port mappings in tabular format.
                                  Each row of the table includes local_port, label_port, and other info.

        Returns:
            str: Hexadecimal representation of the local port value corresponding to the input.
                 Returns error messages for invalid inputs or if no matching local_port is found.

        Example:
            Given the port data string:
            ports_data_str = '''
            =====================================================================================
            |  log_port|local_port|slot|label_port|      mode| width| lane_bmap| swid|
            =====================================================================================
            |   0x10001|         1|   0|        18|   ENABLED|     4|      0x0F|    0|
            |   0x10002|         2|   0|         0|  DISABLED|     0|      0x00|  255|
            |   0x10003|         3|   0|        18|   ENABLED|     4|      0xF0|    0|
            |   0x10004|         4|   0|         0|  DISABLED|     0|      0x00|  255|
            ...

            Example usage:
                get_local_port_hex('sw18p1', ports_data_str)  # Returns '0x1'
                get_local_port_hex('sw18p2', ports_data_str)  # Returns '0x3'
        """
        cmd = "docker exec syncd-ibv00 sx_api_ports_mapping_dump.py"
        ports_data_str = engine.run_cmd(cmd)
        # Parse the input string (e.g., 'sw18p1' -> label_port: 18, port_index: 1)
        if not input_str.startswith('sw') or 'p' not in input_str:
            return "Invalid input format"

        try:
            # Extract label_port and port_index from input string
            label_port = int(input_str[2:input_str.index('p')])  # Extract the number after 'sw'
            port_index = int(input_str[input_str.index('p') + 1:])  # Extract the number after 'p'
        except ValueError:
            return "Invalid input format"

        lines = ports_data_str.splitlines()
        matching_ports = []

        # Process each line and extract relevant data
        for line in lines:
            # Skip lines that are part of the header or separator lines
            if not line.startswith("|") or "log_port" in line:
                continue

            # Extract values from the columns (split by '|')
            columns = line.split('|')
            if len(columns) < 5:
                continue  # Skip malformed lines

            # Get the relevant values from the columns
            try:
                local_port = int(columns[2].strip())  # local_port is in column 2
                label_port_value = int(columns[4].strip())  # label_port is in column 4
            except ValueError:
                continue  # Skip lines that don't have valid integer values

            # Check if this line matches the requested label_port
            if label_port_value == label_port:
                matching_ports.append(local_port)

        # Check if we found any matching ports
        if not matching_ports or len(matching_ports) < port_index:
            return "No matching local_port found"

        # Get the correct local_port based on the port index (1-indexed)
        local_port = matching_ports[port_index - 1]

        # Return the local_port as a hexadecimal value
        return hex(local_port)

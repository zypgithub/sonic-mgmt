import logging
import time
import re

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
    def simulate_toggle_port_event(engine, device, fae, port_name, mst_dev_name, sleep):
        with allure.step(f"Simulate toggle port event for port {port_name}"):
            asic_number = get_primary_asic(fae)
            local_port_hex = IbInterfaceTool.get_local_port_hex(engine, port_name, asic_number)
            RegisterTool.update_prei_register(engine, mst_dev_name=mst_dev_name, local_port=local_port_hex)
            time.sleep(sleep)

    @staticmethod
    def get_mst_dev_name(engines, asic_conf_dict, module_name=None, port_name=None):
        fae_port_name = port_name if port_name else f"{module_name}p1"
        fae = Fae(port_name=fae_port_name)

        with allure.step(f"Find correct mst_dev_name for {module_name or port_name}"):
            asic_number = get_primary_asic(fae)
            assert asic_number is not None, "primary-asic is None"
            asic_dev_id_number = f"DEV_ID_ASIC_{asic_number}"
            asic_mapping_number = asic_conf_dict[asic_dev_id_number]
            cmd = LinuxCmdBuilderTool("sudo mst status -v").grep("pciconf").grep(f"{asic_mapping_number}").awk_print(
                "2").build()
            mst_dev_name = engines.dut.run_cmd(cmd)
            return mst_dev_name

    @staticmethod
    def get_mst_cable_name(engines, transceiver_name, pci_conf):
        match = re.search(r'(?<=sw)[^\d]*(\d+)', transceiver_name)
        mst_dev_name = pci_conf + '_cable_'
        if match:
            mst_dev_name += str(int(match.group(1)) - 1)

        return mst_dev_name

    @staticmethod
    def is_dev_module(engine, transceiver_name):
        engine.run_cmd("sudo mst cable add")
        output = (engine.run_cmd(f'sudo flint -d {transceiver_name} q | grep DEV')).strip()
        return bool(output)

    @staticmethod
    def get_local_port_hex(engine, port_name, asic_number):
        docker = f"syncd-ibv0{asic_number}"
        cmd = f"docker exec {docker} sx_api_ports_mapping_dump.py"
        table_output = engine.run_cmd(cmd)
        local_port, lane_bmap = get_local_port_and_lane_bmap(port_name)
        return get_log_port(table_output, local_port, lane_bmap)


def get_primary_asic(fae):
    output_fae_port = OutputParsingTool.parse_show_interface_output_to_dictionary(
        fae.interface.show()).get_returned_value()
    return output_fae_port.get(IbInterfaceConsts.PRIMARY_ASIC, "0")


def get_local_port_and_lane_bmap(port_name):
    """
    Extracts the switch number and port number from a port name.

    Args:
        port_name (str): The port name string (e.g., 'swA11p1', 'port swB15p1', 'sw11p1').

    Returns:
        tuple: A tuple containing the switch number and port number as integers (e.g., (11, 1)).
    """
    # Update regex to make 'A' or 'B' optional and match the switch and port number
    match = re.search(r'[sS][wW]([A-Za-z]?)\s*(\d+)p(\d+)', port_name)

    if match:
        switch_letter = match.group(1)  # This can be empty or 'A' or 'B'
        port_number = int(match.group(2))
        local_port = int(match.group(3))

        if switch_letter.lower() in ['a', 'b'] and local_port == 2:
            lane_bmap = '0x80'
        elif local_port == 2:
            lane_bmap = '0x10'
        elif local_port == 1:
            lane_bmap = '0x01'
        else:
            raise ValueError(f"Unsupported local_port value: {local_port}")

        return port_number, lane_bmap

    # Return None or raise an exception if the port name doesn't match the expected pattern
    raise ValueError(f"Invalid port name format: {port_name}")


def get_log_port(table: str, label_port: int, lane_bmap: str):
    """
    Fetches the log_port value based on label_port and lane_bmap values from a given table.
    Returns only the last two digits of log_port after removing the '0x100' prefix.

    Args:
        table (str): The table as a multiline string.
        label_port (int): The switch number (label_port).
        lane_bmap (str): The lane_bmap value (either '0x01' or '0x80').

    Returns:
        str: The corresponding log_port value without the '0x100' prefix, e.g., '09'.

    Raises:
        ValueError: If the specified label_port and lane_bmap combination are not found in the table.
    """

    # Split the table into rows
    rows = table.splitlines()
    header = rows[1]  # Header row with column names

    # Identify column indexes based on the header
    columns = header.split("|")
    col_indexes = {
        "log_port": columns.index("  log_port"),
        "label_port": columns.index("label_port"),
        "lane_bmap": columns.index(" lane_bmap")
    }

    # Parse rows and find the matching row based on label_port and lane_bmap
    for row in rows[3:]:  # Data rows start after the separator line
        cols = row.split("|")
        try:
            row_label_port = int(cols[col_indexes["label_port"]].strip())
            row_lane_bmap = cols[col_indexes["lane_bmap"]].strip()

            # Match the given label_port and lane_bmap
            if row_label_port == label_port and row_lane_bmap == lane_bmap:
                # Extract the last two digits of log_port, remove the "0x100" prefix
                log_port_value = cols[col_indexes["log_port"]].strip()
                return log_port_value[-2:]  # Return the last two characters
        except ValueError:
            continue  # Skip rows with non-numeric values in relevant columns

    raise ValueError(f"Entry not found for label_port={label_port}, lane_bmap={lane_bmap}")

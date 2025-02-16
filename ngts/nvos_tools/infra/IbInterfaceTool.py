import logging
import re
import time
from functools import lru_cache

from ngts.constants.constants import InfraConst
from ngts.nvos_constants.constants_nvos import LinkDetectionConsts
from ngts.nvos_tools.Devices.IbDevice import BlackMambaSwitch, CrocodileSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.LinuxCmdBuilderTool import LinuxCmdBuilderTool
from ngts.nvos_tools.infra.MultiPlanarTool import MultiPlanarTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
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
    def simulate_toggle_port_event(engine, port_name='', sleep=0):
        with allure.step(f"Simulate toggle port event for port {port_name}"):
            mst_dev_name = IbInterfaceTool.get_mst_dev_name(engine, port_name=port_name)
            local_port_hex = IbInterfaceTool.get_local_port_hex(engine, port_name)
            RegisterTool.update_prei_register(engine, mst_dev_name=mst_dev_name, local_port=local_port_hex)
            time.sleep(sleep)

    @staticmethod
    @lru_cache
    def get_mst_dev_name(engine, module_name=None, port_name=None):
        if not (module_name or port_name):
            raise ValueError(f'{module_name=}, {port_name=}')
        fae_port_name = port_name or f"{module_name}p1"
        asic_letter, _, _, plane_number = IbInterfaceTool.parse_port_name(port_name)

        with allure.step(f"Find mst_dev_name for {fae_port_name}"):
            if asic_letter or plane_number:  # Crocodile ports, e.g. swA...
                # asic_letter is for Crocodile where the port name mentions ASIC 'A' or 'B'.
                # plane_number is for other systems and only for plane-ports, e.g. sw1p1pl3 is plane 3 which belongs
                # to ASIC 2 (because plane-numbers are 1-based and ASIC-numbers are (sometimes) 0-based, god knows why)
                asic_number = MultiPlanarTool.asic_letter_to_number(asic_letter) if asic_letter else plane_number - 1
                logger.info(f'{fae_port_name=} --> {asic_number=}')
                asic_dev_id_number = f"DEV_ID_ASIC_{asic_number}"
                asic_mapping_number = MultiPlanarTool.get_asic_conf_dict(engine)[asic_dev_id_number]
                cmd = LinuxCmdBuilderTool("sudo mst status -v").grep("pciconf").grep(f"{asic_mapping_number}").awk_print(
                    "2").build()
                mst_dev_name = engine.run_cmd(cmd, validate=True)

            else:  # for aggregated port on non-Crocodile, get the primary-asic-device from nv show fae interface <port>
                fae = Fae(port_name=fae_port_name)  # todo nv_command.fae[fae_port_name] ...
                output_fae_port = OutputParsingTool.parse_show_interface_output_to_dictionary(
                    fae.interface.show()).get_returned_value()
                mst_dev_name = output_fae_port[IbInterfaceConsts.PRIMARY_ASIC_DEVICE]

        logger.info(f'mst device for {fae_port_name} is {mst_dev_name}')
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
    def get_local_port_hex(engine, port_name):
        asic_letter, port_number, local_port, plane_number = IbInterfaceTool.parse_port_name(port_name)
        asic_number = (MultiPlanarTool.asic_letter_to_number(asic_letter)
                       if asic_letter else MultiPlanarTool.get_primary_asic(Fae(port_name=port_name)))
        docker = InfraConst.SYNCD_IBV_DOCKER.format(asic_number)
        cmd = f"docker exec {docker} sx_api_ports_mapping_dump.py"
        table_output = engine.run_cmd(cmd, validate=True)
        lane_bmap = get_lane_bmap(port_name)
        return get_log_port(table_output, port_number, lane_bmap)

    @staticmethod
    def parse_port_name(name: str):
        """swA13p2pl1 --> ('A', 13, 2, 1).   sw13p2 --> (None, 13, 2, None)"""
        match = re.fullmatch(r'[sS][wW]([A-Za-z])?\s*(\d+)p(\d+)(?:pl(\d+))?', name)
        if not match:
            raise ValueError(f"Invalid port name format: {name}")

        asic_letter = match.group(1)  # This can be None or 'A' or 'B'
        port_number = int(match.group(2))
        local_port = int(match.group(3))
        plane_number = int(match.group(4)) if match.group(4) else None
        result = asic_letter, port_number, local_port, plane_number
        logger.info(f'parsed "{name}" ==> {result}')
        return result


def get_lane_bmap(port_name):
    """
    Calculates the lane-bmap as it would appear in the output of sx_api_ports_mapping_dump.py

    Args:
        port_name (str): The port name string, can be aggregated (e.g. 'swA11p1', 'sw11p2') or plane-port ('swB15p1pl3')
        Note: If the port given is an aggregated port, returned value is for plane-port #1.

    Returns:
        str: lane-bmap as a string representing a hex number, e.g. on Crocodile: 'swB11p2pl4' --> '0x18'
    """
    _, _, local_port, plane_number = IbInterfaceTool.parse_port_name(port_name)
    lane_bmap = 0x10 ** (local_port - 1) * 2 ** ((plane_number or 1) - 1)
    lane_bmap = f'0x{lane_bmap:0>2x}'
    # p1pl1 --> 0x01, p1pl2 --> 0x02, p1pl3 --> 0x04, p1pl4 --> 0x08
    # p2pl1 --> 0x10, p2pl2 --> 0x20, p2pl3 --> 0x40, p2pl4 --> 0x80
    logger.info(f'{lane_bmap=}')
    tested_switches = (BlackMambaSwitch, CrocodileSwitch)
    if not any(isinstance(TestToolkit.devices.dut, device) for device in tested_switches):
        raise NotImplementedError(
            f'get_lane_bmap function was only tested for {[device.__name__ for device in tested_switches]}. Test this '
            f'function manually for the current switch type and add it to the supported_switches list. Current output '
            f'for reference: get_lane_bmap({port_name}) --> {lane_bmap}')
    return lane_bmap


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
    for row in rows[3:-1]:  # these are all the data rows
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

import os
import json
import re
import pytest
import logging

from tests.common.platform.device_utils import __check_if_status as check_if_status
from tests.common.utilities import wait_until
from tests.common.platform.interface_utils import get_physical_port_indices
from tests.common.helpers.assertions import pytest_assert

logger = logging.getLogger()

IM_ENABLED = 1

SAI_PROFILE_FILE_NAME = "sai.profile"
PMON_DEAMON_CONTROL_FILE_NAME = "pmon_daemon_control.json"
PLATFORM_FOLDER_PATH = "/usr/share/sonic/device/"
IM_SAI_ATTRIBUTE_NAME = "SAI_INDEPENDENT_MODULE_MODE"
XCVRD_PMON_PROCESS_SKIP = "python3 /usr/local/bin/xcvrd --skip_cmis_mgr"

IM_EEPROM_SPECIFICATION_KEY = "Specification compliance"
IM_EEPROM_VENDOR_DATE_KEY = "Vendor Date Code\\(YYYY-MM-DD Lot\\)"
IM_EEPROM_VENDOR_NAME_KEY = "Vendor Name"
IM_EEPROM_VENDOR_OUI_KEY = "Vendor OUI"
IM_EEPROM_VENDOR_PM_KEY = "Vendor PN"
IM_EEPROM_VENDOR_REV_KEY = "Vendor Rev"
IM_EEPROM_VENDOR_SN_KEY = "Vendor SN"

IM_REDIS_SPECIFICATION_KEY = "specification_compliance"
IM_REDIS_VENDOR_DATE_KEY = "vendor_date"
IM_REDIS_VENDOR_NAME_KEY = "manufacturer"
IM_REDIS_VENDOR_OUI_KEY = "vendor_oui"
IM_REDIS_VENDOR_PM_KEY = "model"
IM_REDIS_VENDOR_REV_KEY = "vendor_rev"
IM_REDIS_VENDOR_SN_KEY = "serial"
IM_REDIS_SFP_IDENTIFIER_KEY = "type"

IM_TRANCEIVER_STATUS_MODULE_STATE = "Current module state"
IM_TRANCEIVER_STATUS_REASON_FAULT = "Reason of entering the module fault state"
IM_REDIS_TRANCEIVER_STATUS_MODULE_STATE = "module_state"
IM_REDIS_TRANCEIVER_STATUS_REASON_FAULT = "module_fault_cause"

EEPROM_CLI_KEYS = [
    IM_EEPROM_SPECIFICATION_KEY,
    IM_EEPROM_VENDOR_DATE_KEY,
    IM_EEPROM_VENDOR_NAME_KEY,
    IM_EEPROM_VENDOR_OUI_KEY,
    IM_EEPROM_VENDOR_PM_KEY,
    IM_EEPROM_VENDOR_REV_KEY,
    IM_EEPROM_VENDOR_SN_KEY,
]

TRANCEIVER_CLI_KEYS = [
    IM_TRANCEIVER_STATUS_MODULE_STATE,
    IM_TRANCEIVER_STATUS_REASON_FAULT
]

EEPROM_TO_REDIS_KEY_MAP = {
    IM_EEPROM_SPECIFICATION_KEY: IM_REDIS_SPECIFICATION_KEY,
    IM_EEPROM_VENDOR_DATE_KEY: IM_REDIS_VENDOR_DATE_KEY,
    IM_EEPROM_VENDOR_NAME_KEY: IM_REDIS_VENDOR_NAME_KEY,
    IM_EEPROM_VENDOR_OUI_KEY: IM_REDIS_VENDOR_OUI_KEY,
    IM_EEPROM_VENDOR_PM_KEY: IM_REDIS_VENDOR_PM_KEY,
    IM_EEPROM_VENDOR_REV_KEY: IM_REDIS_VENDOR_REV_KEY,
    IM_EEPROM_VENDOR_SN_KEY: IM_REDIS_VENDOR_SN_KEY
}

TRANSCEIVER_STATUS_TO_REDIS_KEY_MAP = {
    IM_TRANCEIVER_STATUS_MODULE_STATE: IM_REDIS_TRANCEIVER_STATUS_MODULE_STATE,
    IM_TRANCEIVER_STATUS_REASON_FAULT: IM_REDIS_TRANCEIVER_STATUS_REASON_FAULT
}

BER_EFFECTIVE_PHYSICAL_ERRORS = "Effective Physical Errors"
BER_EFFECTIVE_PHYSICAL_BER = "Effective Physical BER"
BER_ROW_PHYSICAL_ERRORS_PER_LANE = "Raw Physical Errors Per Lane"
BER_RAW_PHYSICAL_BER = "Raw Physical BER"

BER_KEY_MAP = {
    BER_EFFECTIVE_PHYSICAL_ERRORS,
    BER_EFFECTIVE_PHYSICAL_BER,
    BER_ROW_PHYSICAL_ERRORS_PER_LANE,
    BER_RAW_PHYSICAL_BER
}

PLATFORM_GENERATION = ['4280', '4700', '5600', '5610']

CMD_INTERFACE_TRANSCEIVER = "show interface transceiver eeprom"
CMD_SFPUTIL_EEPROM = "sudo sfputil show eeprom"
CMD_INTERFACE_TRANSCEIVER_STATUS= "show interfaces transceiver status"
CMD_REDIS_TRANSCEIVER_INFO = 'redis-cli -n 6 hgetall "TRANSCEIVER_INFO|{}"'
CMD_REDIS_TRANSCEIVER_STATUS = 'redis-cli -n 6 hgetall "TRANSCEIVER_STATUS|{}"'


def enable_cmis_mgr_in_pmon_file(duthost):
    """
    @summary: This method is for enable cmis_mgr for pmon
    @param: duthosts: duthosts fixture
    """
    dut_platfrom = duthost.facts['platform']
    pmon_daemon_path = os.path.join(PLATFORM_FOLDER_PATH, dut_platfrom)
    pmon_daemon_file_path = os.path.join(pmon_daemon_path, PMON_DEAMON_CONTROL_FILE_NAME)
    cmd = f'sudo sed -i \'s/"skip_xcvrd_cmis_mgr": true/"skip_xcvrd_cmis_mgr": false/\' {pmon_daemon_file_path}'
    duthost.shell(cmd)


def check_cmis_mgr_not_skipped(duthost):
    """
    @summary: This method is to check if cmis_mgr not skipped
    @param: duthosts: duthosts fixture
    """
    dut_platfrom = duthost.facts['platform']
    pmon_daemon_path = os.path.join(PLATFORM_FOLDER_PATH, dut_platfrom)
    pmon_daemon_file_path = os.path.join(pmon_daemon_path, PMON_DEAMON_CONTROL_FILE_NAME)
    cmd = duthost.shell('cat {}'.format(pmon_daemon_file_path))
    daemon_control_dict = json.loads(cmd['stdout'])
    if daemon_control_dict['skip_xcvrd_cmis_mgr'] is True:
        pytest.skip(f"Skip TC as skip_xcvrd_cmis_mgr skipped in {PMON_DEAMON_CONTROL_FILE_NAME} file")


def check_xcvrd_pmon_process_not_skipped(duthost):
    """
    @summary: This method is to check if xcvfd pmon process not skipped
    @param: duthosts: duthosts fixture
    """
    cmd = duthost.shell("docker exec pmon /bin/bash -c 'ps -ax'")
    if XCVRD_PMON_PROCESS_SKIP in cmd['stdout']:
        pytest.skip(f"Skip TC as IM started with skip flag in pmon processes")


def add_im_sai_attribute(duthost):
    """
    @summary: This method is for add Independent Module SAI attribute in sai.profile
    @param: duthosts: duthosts fixture
    """
    dut_hwsku = duthost.facts['hwsku']
    dut_platfrom = duthost.facts['platform']
    sai_profile_path = os.path.join(PLATFORM_FOLDER_PATH, dut_platfrom, dut_hwsku, SAI_PROFILE_FILE_NAME)
    duthost.shell(f'echo "{IM_SAI_ATTRIBUTE_NAME}=1" >> {sai_profile_path}')


def check_im_sai_attribute_value(duthost):
    """
    @summary: This method is for checking if Independent Module SAI attribute set to 1 in sai.profile
    @param: duthosts: duthosts fixture
    """
    dut_hwsku = duthost.facts['hwsku']
    dut_platfrom = duthost.facts['platform']
    sai_profile_path = os.path.join(PLATFORM_FOLDER_PATH, dut_platfrom, dut_hwsku, SAI_PROFILE_FILE_NAME)
    cmd = duthost.shell('cat {}'.format(sai_profile_path))
    if IM_SAI_ATTRIBUTE_NAME in cmd['stdout']:
        im_enabled_in_sai = re.search(f"{IM_SAI_ATTRIBUTE_NAME}=(\\d?)", cmd['stdout']).group(1)
        if im_enabled_in_sai == '1':
            return True
    return False


def disable_autoneg_at_ports(duthost, interfaces):
    """
    @summary: This method is for disabling autoneg at specific ports
    @param: duthosts: duthosts fixture
    """
    for im_interface_name in interfaces:
        logging.info(f"Disable auto negotiation at interface {im_interface_name}")
        duthost.command(f"sudo config interface autoneg {im_interface_name} disabled")


def parse_output_to_dict(output, keys_list):
    """
    @summary: Parse the output based at keys list provided
    @param output: command output
    @param keys_list: list of keys to be parsed
    @return: returns result in a dictionary
    """
    result_dict = {}
    for key in keys_list:
        result_dict.update({key.replace('\\', ''): re.search(f"{key}(\\s+)?:\\n? (.*)", output).group(2).strip()})
    return result_dict


def parse_im_eeprom(output_lines):
    """
    @summary: Parse the SFP eeprom information from command output
    @param output_lines: command output lines
    @return: returns result in a dictionary
    """
    return parse_output_to_dict(output_lines, EEPROM_CLI_KEYS)


def parse_sfp_info_from_redis(duthost, cmd, asic_index, interfaces):
    """
    @summary: Parse the SFP eeprom information from redis database
    @param duthost: duthost fixture
    @param cmd: command to be executed
    @param asic_index: asic index
    @param interfaces: interfaces list
    @return: Returns result in a dictionary
    """
    result_dict = {}
    asichost = duthost.asic_instance(asic_index)
    logging.info("Check detailed transceiver information of each connected port")
    for intf in interfaces:
        redis_all_data_dict = {}
        docker_cmd = asichost.get_docker_cmd(cmd.format(intf), "database")
        port_xcvr_info = duthost.command(docker_cmd)["stdout_lines"]
        # Convert to dictionary

        split_by_2 = [port_xcvr_info[i * 2:(i + 1) * 2] for i in range((len(port_xcvr_info) + 2 - 1) // 2)]
        for item in split_by_2:
            redis_all_data_dict.update({item[0]: item[1].rstrip()})

        # Clean up the placeholder (\x00 or \u0000) in vendor_date field
        cleanup_placeholder(redis_all_data_dict, "vendor_date")

        result_dict.update({intf: redis_all_data_dict})
    return result_dict


def compare_data_from_cli_and_redis(cli_data, redis_data, port, key_mapping):
    for cli_eeprom_key, redis_key in key_mapping.items():
        # For SFF cables some fields having multi line output, taking first and check if present in redis db output
        cli_value = cli_data[cli_eeprom_key.replace("\\", "")]
        redis_value = redis_data[port][redis_key]
        assert cli_value == redis_value if ":" not in cli_value else cli_value.split(":")[-1].strip() in redis_value, \
            f"Data from cli param {cli_eeprom_key} does not match data from redis"


def get_sff_cables(duthost, cmd, asic_index, port_list):
    sff_ports = []
    for port in port_list:
        redis_output = parse_sfp_info_from_redis(duthost, cmd,
                                                 asic_index, [port])
        if 'QSFP28' in redis_output[port][IM_REDIS_SFP_IDENTIFIER_KEY]:
            sff_ports.append(port)
    return sff_ports

def parse_im_tranceiver_status(output_lines):
    """
    @summary: Parse the  output
    @param output_lines: Command output lines
    @return: Returns result in a dictionary
    """
    return parse_output_to_dict(output_lines, TRANCEIVER_CLI_KEYS)


def get_mlxlink_ber(duthost, interface):
    """
    @summary: Parse the  output
    @param duthost: duthost fixture
    @param interface: DUT interface
    @return: BER values dictionary
    """
    # Get name of pci_cr0
    mst_path_pciconf = duthost.shell('sudo ls /dev/mst/ | grep cr0')['stdout']
    mst_path = f"/dev/mst/{mst_path_pciconf}"
    # Get interface port number
    physical_port_index_map = get_physical_port_indices(duthost, interface)
    physical_port_index = physical_port_index_map[interface]
    cmd = duthost.command(f"mlxlink -d {mst_path} -p {physical_port_index} -c")['stdout']
    return parse_output_to_dict(cmd, BER_KEY_MAP)


def emulate_interface_plug_in_out(duthost, interface, plug_in=True):
    """
    @summary: This method is for emulate plug in/out SFP module
    @param: duthost: duthosts fixture
    @param: enum_rand_one_per_hwsku_frontend_hostname: enum_rand_one_per_hwsku_frontend_hostname fixture
    @param: interface: interface_name
    @param: plug_in: if true - emulate plug in event, if false - emulate plug out event
    """
    # Get name of pciconf0
    mst_path_pciconf = duthost.shell('sudo ls /dev/mst/ | grep conf')['stdout']
    # Get interface port number
    physical_port_index_map = get_physical_port_indices(duthost, interface)
    physical_port_index = physical_port_index_map[interface] - 1
    # Set last bit value to 1 if plug_in flag set to true otherwise set to 0
    last_bit = 1 if plug_in else 0
    cmd = f"mlxreg -d {mst_path_pciconf} --set 'admin_status=0x0000000{last_bit},ase=1' --reg_name PMAOS --indexes " \
          f"'module={physical_port_index},slot_index=0' -y"
    if plug_in:
        duthost.shell(cmd)
        pytest_assert(wait_until(90, 5, 0, check_if_status, duthost, interface, "up"),
                      "Port did not come up after plug in event")
    else:
        duthost.shell(cmd)
        pytest_assert(wait_until(15, 5, 0, check_if_status, duthost, interface, "down"),
                      "Port did not come down after plug out event")


def get_split_ports(duthost, port_index):
    """
    @summary: This method is for check
    @param: duthost: duthosts fixture
    @param: port_index: logical port index
    @return: list of split port names
    """
    config_facts = duthost.config_facts(host=duthost.hostname, source="running")['ansible_facts']
    split_port_alias_pattern = r"etp{}[a-z]".format(port_index)
    split_up_ports = [p for p, v in list(config_facts['PORT'].items()) if v.get('admin_status', None) == 'up' and
                      re.match(split_port_alias_pattern, v['alias'])]
    return split_up_ports


def get_ports_supporting_im(duthost, conn_graph_facts):
    """
    @summary: This method is for get DUT ports supporting IM
    @param: duthost: duthost fixture
    @param: conn_graph_facts: conn_graph_facts fixture
    @param: enum_frontend_asic_index: enum_frontend_asic_index fixture
    @return: list of IM ports supported
    """
    ports_with_im_support = []
    logging.info("Get all ports from DUT")
    dut_interfaces = list(conn_graph_facts["device_conn"][duthost.hostname].keys())

    logging.info("Create interface to physical port dict")
    physical_index_to_interface_dict = {}
    for interface in dut_interfaces:
        int_to_index = get_physical_port_indices(duthost, interface)
        index_to_interface = {v: k for k, v in int_to_index.items()}
        physical_index_to_interface_dict.update(index_to_interface)

    for port_number, port_name in physical_index_to_interface_dict.items():
        cmd = duthost.shell(f"sudo cat /sys/module/sx_core/asic0/module{int(port_number) - 1}/control")
        if int(cmd['stdout']) == IM_ENABLED:
            # Check if port is split
            split_ports = get_split_ports(duthost, int(port_number))
            if split_ports:
                ports_with_im_support += split_ports
            else:
                ports_with_im_support.append(port_name)

    return ports_with_im_support


def is_spc1(duthost):
    """
    @summary: This method checking if platform is SPC1
    @param: duthost: duthost fixture
    @return: list of IM ports supported
    """
    return True if "sn2" in duthost.facts["platform"] else False


def is_spc2(duthost):
    """
    @summary: This method checking if platform is SPC2
    @param: duthost: duthost fixture
    @return: list of IM ports supported
    """
    return True if "sn3" in duthost.facts["platform"] else False


def im_supported(duthost):
    """
    @summary: This method checking if platform supports Independent Module feature
    @param: duthost: duthost fixture
    @return: list of IM ports supported
    """
    return True if not is_spc1(duthost) and not is_spc2(duthost) else False


def im_ms_sku(duthost):
    """
    @summary: This method checking if HWSKU is Microsoft
    @param: duthost: duthost fixture
    @return: list of IM ports supported
    """
    return any(item in duthost.facts['hwsku'] for item in PLATFORM_GENERATION)


def cleanup_placeholder(parsed_eeprom, key):
    """
    Clean up the placeholder (\x00 or \u0000) in Vendor Date Code field

    Args:
        parsed_eeprom: Dictionary containing parsed EEPROM data
        key: Key name for vendor date in the EEPROM dictionary
    """
    if key in parsed_eeprom:
        logger.info(f"The current vendor date is [{parsed_eeprom[key]}]")
        parsed_eeprom[key] = parsed_eeprom[key].split()[0]
        logger.info(f"The vendor date after update is [{parsed_eeprom[key]}]")

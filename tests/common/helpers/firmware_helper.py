import re
import os
import json
import tarfile


PLATFORM_COMP_PATH_TEMPLATE = '/usr/share/sonic/device/{}/platform_components.json'
FW_TYPE_INSTALL = 'install'
FW_TYPE_UPDATE = 'update'


def extract_fw_data(fw_pkg_path):
    """
    Extract firmware data from tar.gz or json file.

    Args:
        fw_pkg_path: Path to firmware package (tar.gz or json file)

    Returns:
        dict: Firmware data dictionary
    """
    if tarfile.is_tarfile(fw_pkg_path):
        path = "/tmp/firmware"
        if not os.path.exists(path):
            os.mkdir(path)
        with tarfile.open(fw_pkg_path, "r:gz") as f:
            f.extractall(path)
            json_file = os.path.join(path, "firmware.json")
            with open(json_file, 'r') as fw:
                fw_data = json.load(fw)
    else:
        with open(fw_pkg_path, 'r') as fw:
            fw_data = json.load(fw)

    return fw_data


def get_bmc_info_from_firmware_data(fw_data, chassis_name):
    """
    Get BMC version and firmware path from firmware data.

    Args:
        fw_data: Firmware data from extract_fw_data()
        chassis_name: Chassis name to look up

    Returns:
        tuple: (expected_version, firmware_path) or (None, None) if not found
    """
    bmc_info = fw_data.get('chassis', {}).get(chassis_name, {}).get('component', {}).get('BMC')
    if not bmc_info or not isinstance(bmc_info, list) or len(bmc_info) == 0:
        return None, None

    return bmc_info[0].get('version'), bmc_info[0].get('firmware')


def parse_firmware_status(status_output):
    """
    Parse 'fwutil show status' output string into structured data.

    Args:
        status_output: Raw output string from 'fwutil show status' command

    Returns:
        dict: {"chassis": {"CHASSIS_NAME": {"component": {"BMC": "version", ...}}}}
    """
    output_data = {"chassis": {}}

    if not status_output:
        return output_data

    lines = status_output.splitlines()
    if len(lines) < 3:
        return output_data

    num_spaces = 2
    curr_chassis = ""
    separators = re.split(r'\s{2,}', lines[1])

    for line in lines[2:]:
        if not line.strip():
            continue

        data = []
        start = 0

        for sep in separators:
            curr_len = len(sep)
            data.append(line[start:start+curr_len].strip())
            start += curr_len + num_spaces

        if len(data) < 4:
            continue

        if data[0].strip():
            curr_chassis = data[0].strip()
            output_data["chassis"][curr_chassis] = {"component": {}}

        if curr_chassis and curr_chassis in output_data["chassis"]:
            output_data["chassis"][curr_chassis]["component"][data[2]] = data[3]

    return output_data


def show_firmware(duthost):
    """
    Get firmware status from DUT using Ansible interface.

    Args:
        duthost: Ansible DUT host object

    Returns:
        dict: Parsed firmware status data
    """
    out = duthost.command("sudo fwutil show status")
    return parse_firmware_status(out['stdout'])


def get_bmc_version_from_firmware_data(fw_data):
    """
    Extract BMC version and chassis name from parsed firmware data.

    Args:
        fw_data: Parsed firmware data from show_firmware() or parse_firmware_status()

    Returns:
        tuple: (bmc_version, chassis_name) or (None, None) if not found
    """
    chassis_dict = fw_data.get("chassis", {})
    if not chassis_dict:
        return None, None

    # Get first chassis name (typically only one)
    chassis_name = list(chassis_dict.keys())[0]
    components = chassis_dict[chassis_name].get("component", {})

    bmc_version = components.get("BMC")
    return bmc_version, chassis_name

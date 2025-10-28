import argparse
import json
import os.path
import traceback
from typing import List
import time

import nogaq
from Component import Component, BmcComponent
from ComponentManager import ComponentManager
from Redfish_rest_api import RedFishRestApi
from Constants import Defaults, NogaConstants, RedfishCollection


def get_switch_info(setup_name: str) -> List[str]:
    setup_dict = nogaq.get_noga_resource_data(resource_name=setup_name)
    switch_names = [item[NogaConstants.NAME] for item in
                    setup_dict[NogaConstants.RELATIONS][NogaConstants.HAS_A]
                    if item[NogaConstants.TYPE_TITLE] == NogaConstants.SWITCH]
    switches = [nogaq.get_noga_resource_data(resource_name=switch) for switch in switch_names]
    assert switches, f"No switches found in noga for setup {setup_name}"
    return switches[0]


def get_provisioning(switch_info: dict) -> str:
    is_opn = switch_info[NogaConstants.ATTRIBUTES][NogaConstants.SPECIFIC][NogaConstants.OPN].lower()
    return Defaults.PRODUCTION if is_opn == NogaConstants.YES else Defaults.DEVELOPMENT


def start_components_update(_args):
    switch_info = get_switch_info(_args.setup_name)
    bmc_ip = switch_info[NogaConstants.ATTRIBUTES][NogaConstants.SPECIFIC][NogaConstants.BMC_IP]
    provisioning = get_provisioning(switch_info)
    switch_name = switch_info[NogaConstants.ATTRIBUTES][NogaConstants.COMMON]['Name'].strip()
    assert bmc_ip, "No bmc ip found in noga"
    update_via_parameter = bool(_args.bmc_path or _args.bios_path or _args.erot_path or _args.fpga_path)
    rf_api = RedFishRestApi(bmc_ip, _args.bmc_user, _args.bmc_pass)
    json_dict = create_json_dict(_args.fw_versions_json_file)
    devices_with_rel_prod_erot = {
        "juliet-160": {Defaults.EROT_NAME, Defaults.BIOS_NAME, Defaults.BMC_NAME},
        "juliet-195": {Defaults.EROT_NAME, Defaults.BIOS_NAME, Defaults.BMC_NAME},
    }

    components_mapping = {
        Defaults.BMC_NAME: "bmc_path",
        Defaults.FPGA_NAME: "fpga_path",
        Defaults.FPGA_ENCRYPTED_NAME: "fpga_path",
        Defaults.EROT_NAME: "erot_path",
        Defaults.BIOS_NAME: "bios_path",
        Defaults.PLDM_NAME: "pldm_path",
        Defaults.SMA_NAME: "sma_path"
    }
    components_to_update = _get_components_for_update(_args, update_via_parameter)
    if _has_non_encrypted_fpga(bmc_ip) and any(Defaults.FPGA_NAME in comp for comp in components_to_update):
        components_to_update.remove(Defaults.FPGA_ENCRYPTED_NAME)
        components_to_update.append(Defaults.FPGA_NAME)

    respond = rf_api.get_query(f'{RedfishCollection.FIRMWARE_INVENTORY}')

    # If no FPGA hardware found, remove all FPGA-related components
    if Defaults.FPGA_NAME not in str(respond).lower():
        components_to_update = [comp for comp in components_to_update if Defaults.FPGA_NAME not in comp.lower()]

    if (not update_via_parameter) and (Defaults.SMA_NAME in json_dict.get(provisioning, {})):
        components_to_update.append(Defaults.SMA_NAME)

    components: List[Component] = []
    for component_name in components_to_update:
        required_version = None

        if update_via_parameter:
            install_path = _args.__dict__[components_mapping[component_name]]
        else:
            if switch_name in devices_with_rel_prod_erot and component_name in devices_with_rel_prod_erot[switch_name]:
                required_version = json_dict['prod'][component_name]['latest']['version_name']
                install_path = json_dict['prod'][component_name]['latest']['path']
            else:
                required_version = json_dict[provisioning][component_name]['latest']['version_name']
                install_path = json_dict[provisioning][component_name]['latest']['path']

        install_path = install_path.strip()  # Make sure there are no extra spaces in the path

        if not verify_install_path(install_path):
            print(f"{component_name} path does not exist {install_path}")
            raise FileNotFoundError(install_path)

        component = _create_bmc_component(component_name, version=required_version, install_path=install_path,
                                          rf_api=rf_api)
        components.append(component)

    component_manager = ComponentManager(components)

    component_manager.print_installed_versions()
    was_update_performed = component_manager.perform_update()
    update_errors = component_manager.get_errors()

    if was_update_performed:
        component_manager.perform_pc(switch_info)
        try:
            _wait_cpu_boot_start(rf_api)
        except Exception as e:
            print("Timed out waiting for BMC to see CPU boot to complete.")
            raise e

    component_manager.print_installed_versions()

    if update_errors:
        error_summary = "The following component updates encountered errors:\\n" + "\\n".join(update_errors)
        raise Exception(error_summary)


def verify_install_path(install_path):
    return os.path.exists(install_path)


def _create_bmc_component(component_name, version, install_path, rf_api):
    component = BmcComponent(name=component_name, required_version=version,
                             install_path=install_path, rf_api=rf_api)
    return component


def create_json_dict(json_file_path):
    print(f'Read platform components info from json {json_file_path}')
    if not verify_install_path(json_file_path):
        print(f"Json file path does not exist {json_file_path}")
        raise FileNotFoundError(json_file_path)
    with open(json_file_path, 'r') as file:
        return json.load(file)


def _get_components_for_update(_args, update_via_parameter):
    if not update_via_parameter:
        return [Defaults.BMC_NAME, Defaults.BIOS_NAME, Defaults.EROT_NAME, Defaults.FPGA_ENCRYPTED_NAME]
    components_to_update = []
    if _args.bmc_path:
        components_to_update.append(Defaults.BMC_NAME)
    if _args.bios_path:
        components_to_update.append(Defaults.BIOS_NAME)
    if _args.erot_path:
        components_to_update.append(Defaults.EROT_NAME)
    if _args.fpga_path:
        components_to_update.append(Defaults.FPGA_ENCRYPTED_NAME)
    if _args.sma_path:
        components_to_update.append(Defaults.SMA_NAME)
    return components_to_update


def _has_non_encrypted_fpga(bmc_ip):
    non_encrypted_fpga_ips = {'10.7.113.142', '10.7.113.148'}
    return bmc_ip in non_encrypted_fpga_ips


# Try for 2 minutes (24 * 5 seconds) to wait for BMC to see CPU component boot.
def _wait_cpu_boot_start(rf_api):
    tries = 24
    delay = 5
    cpu_inv_name = RedfishCollection.CPU_REDFISH_NAME

    for attempt in range(1, tries + 1):
        respond = rf_api.get_query(f"{RedfishCollection.FIRMWARE_INVENTORY}")
        if cpu_inv_name.lower() in str(respond).lower():
            print(f"{cpu_inv_name} found in firmware inventory.")
            return True

        if attempt < tries:
            print(f"{cpu_inv_name} not found yet; attempt {attempt}/{tries}. Retrying in {delay}s...")
            time.sleep(delay)

    raise RuntimeError(f"{cpu_inv_name} not found after {tries} tries")


def parse_args():
    """Handle parsing the command line arguments using argparse. Documented in the code."""
    usage_str = """Script to be used as a regression step in order
     to align juliet components firmware versions to specific recipe"""
    epilog_str = f'How to run the script:\n{usage_str}'
    parser = argparse.ArgumentParser(usage=usage_str, epilog=epilog_str,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    def parse_mars_default(value):
        if value == 'False':
            return None
        return value

    parser.add_argument('--setup_name',
                        help='Setup name in NOGA', required=True)
    parser.add_argument('--sonic_mgmt_repo_branch',
                        help='Release branch target', required=False, type=parse_mars_default, default=Defaults.DEFAULT_BRANCH_NAME)
    parser.add_argument('--bmc_user',
                        help='Bmc username', required=False, type=parse_mars_default, default=Defaults.DEFAULT_BMC_USER)
    parser.add_argument('--bmc_pass',
                        help='Bmc password', required=False, type=parse_mars_default, default=Defaults.DEFAULT_BMC_PASSWORD)

    parser.add_argument('--fw_versions_json_file',
                        help='Path to file containing required version',
                        default='/auto/sw_system_project/NVOS_INFRA/verification_files/platform_components/juliet_versions.json',
                        type=parse_mars_default)

    parser.add_argument('--bmc_path',
                        help='Path to bmc fwpkg', required=False, type=parse_mars_default, default=None)
    parser.add_argument('--bios_path',
                        help='Path to bios fwpkg', required=False, type=parse_mars_default, default=None)
    parser.add_argument('--fpga_path',
                        help='Path to fpga fwpkg', required=False, type=parse_mars_default, default=None)
    parser.add_argument('--erot_path',
                        help='Path to erot fwpkg', required=False, type=parse_mars_default, default=None)
    parser.add_argument('--cpld_path',
                        help='Path to cpld fwpkg', required=False, type=parse_mars_default, default=None)
    parser.add_argument('--sma_path',
                        help='Path to sma fwpkg', required=False, type=parse_mars_default, default=None)
    parser.add_argument('--pldm_path',
                        help='Path to pldm fwpkg', required=False, type=parse_mars_default, default=None)

    parser.add_argument('--ssh_user',
                        help='SSH username', required=False, type=parse_mars_default, default=Defaults.DEFAULT_SWITCH_USERNAME)
    parser.add_argument('--ssh_pass',
                        help='SSH password', required=False, type=parse_mars_default, default=Defaults.DEFAULT_SWITCH_PASSWORD)

    args = parser.parse_args()
    for arg, value in vars(args).items():
        if not value:
            setattr(args, arg, parser.get_default(arg))
    return args


if __name__ == '__main__':
    try:
        print(f"Start component alignment script ({__file__})")
        _args = parse_args()
        start_components_update(_args)
        print(f"Finished component alignment script ({__file__})")
    except Exception as err:
        print(f"\nException {type(err)} occurred with message: {err}\nTraceback:\n{traceback.format_exc()}")
        traceback.print_exc()
        raise  # raise an exception, keeping the stack trace

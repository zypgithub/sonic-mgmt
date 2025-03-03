import os
import traceback

from Component import CpldComponent
from ComponentManager import ComponentManager
from Constants import NogaConstants, Defaults
from align_fw_components import get_switch_info, parse_args, create_json_dict, verify_install_path


def perform_cpld_update(_args):
    switch_info = get_switch_info(_args.setup_name)
    hostname = switch_info[NogaConstants.ATTRIBUTES][NogaConstants.COMMON]['Name']
    if _args.cpld_path:
        install_path = _args.cpld_path
    else:
        json_dict = create_json_dict(_args.file_path)
        provisioning = switch_info[NogaConstants.ATTRIBUTES][NogaConstants.HARDWARE_COMPONENTS][
            NogaConstants.BIOS_VERSION]
        provisioning = 'prod' if provisioning == 'OPN' else 'dev'
        install_path = json_dict[provisioning][Defaults.CPLD_NAME]['latest']['path']

    if not verify_install_path(install_path):
        print(f"Provided cpld path does not exist {install_path}")
        raise FileNotFoundError(install_path)

    file_name = os.path.basename(install_path)
    required_version = file_name[file_name.index("CPLD"):file_name.rindex("_")]

    component = CpldComponent(Defaults.CPLD_NAME, install_path=install_path, switch_ip=hostname,
                              required_version=required_version, ssh_user=_args.ssh_user, ssh_pass=_args.ssh_pass)
    component_manager = ComponentManager(components=[component])

    component_manager.print_installed_versions()
    was_update_performed = component_manager.perform_update()

    if was_update_performed:
        component_manager.perform_pc()

    component_manager.print_installed_versions()


if __name__ == '__main__':
    try:
        print(f"Start component alignment script ({__file__})")
        _args = parse_args()
        perform_cpld_update(_args)
        print(f"Finished component alignment script ({__file__})")
    except Exception as err:
        print(f"\nException {type(err)} occurred with message: {err}\nTraceback:\n{traceback.format_exc()}")
        traceback.print_exc()
        raise  # raise an exception, keeping the stack trace

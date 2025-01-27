import os
import traceback

from Component import CpldComponent
from ComponentManager import ComponentManager
from align_fw_components import get_switch_info, parse_args
from Constants import NogaConstants, Defaults


def perform_cpld_update(_args):
    switch_info = get_switch_info(_args.setup_name)
    hostname = switch_info[NogaConstants.ATTRIBUTES][NogaConstants.COMMON]['Name']
    file_name = os.path.basename(_args.cpld_path)
    required_version = file_name[file_name.index("CPLD"):file_name.rindex("_")]

    component = CpldComponent(Defaults.CPLD_NAME, install_path=_args.cpld_path, switch_ip=hostname,
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

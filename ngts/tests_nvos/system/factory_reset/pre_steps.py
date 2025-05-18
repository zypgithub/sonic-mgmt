from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch


@disabled_access_ports
def factory_reset_no_params_pre_steps(engines, platform_params, system, devices, has_loopbox, setup_name, standalone_system):
    port_type = devices.dut.switch_type.lower()
    init_cluster_status = None
    port_type = devices.dut.switch_type.lower()

    with allure.step('Create System object'):
        machine_type = platform_params['filtered_platform']

    with allure.step('Get health status'):
        health_status = get_health_status(system)

    with allure.step(f'Set description to {port_type} ports'):
        description = "test_reset_factory_without_params"
        ports = Tools.RandomizationTool.select_random_ports(requested_ports_state=None, requested_ports_type=port_type,
                                                            num_of_ports_to_select=3).get_returned_value()
        apply_and_save_port = ports[0]
        just_apply_port = ports[1]
        not_apply_port = ports[2]

    with allure.step(f'Set and apply description to {port_type} port, save config after it'):
        apply_and_save_port.interface.set(NvosConst.DESCRIPTION, description, apply=True).verify_result()
        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
        NvueGeneralCli.save_config(engines.dut)

    with allure.step(f'Set and apply description to {port_type} port'):
        just_apply_port.interface.set(NvosConst.DESCRIPTION, description, apply=True).verify_result()

    with allure.step(f'Set description to {port_type} port'):
        not_apply_port.interface.set(NvosConst.DESCRIPTION, description, apply=False).verify_result()

        if devices.dut.has_nmx:
            with allure.step('Juliet Device Check'):
                with allure.step("Config A reverse cluster state than configured"):
                    cluster = Cluster()
                    # Enable cluster and validate its enabled.
                    init_cluster_status = ClusterTools.check_cluster_state(cluster, output_format=OutputFormat.json)
                    ClusterTools.reverse_cluster_state(cluster, setup_name, output_format=OutputFormat.json)
        else:
            init_cluster_status = None

    with allure.step('Validate ports description'):
        validate_port_description(engines.dut, apply_and_save_port, description)
        validate_port_description(engines.dut, just_apply_port, description)
        validate_port_description(engines.dut, not_apply_port, "")

    with allure.step("Add data before reset factory"):
        username = add_verification_data(engines.dut, system)

    with allure.step("Get current time"):
        update_timezone(system)
        current_time = get_current_time(engines)

    return apply_and_save_port, current_time, just_apply_port, health_status, machine_type, not_apply_port, username, init_cluster_status


def factory_reset_keep_basic_pre_steps(engines, system):
    with allure.step('Get health status'):
        health_status = get_health_status(system)

    with allure.step('Set description to eth0 port'):
        mgmt_port = Port('eth0')
        mgmt_port.interface.set(NvosConst.DESCRIPTION, 'nvosdescription', apply=True).verify_result()
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_output_to_dictionary(
            mgmt_port.interface.show()).get_returned_value()

        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=NvosConst.DESCRIPTION,
                                                          expected_value='nvosdescription')

    with allure.step("Add data before reset factory"):
        username = add_verification_data(engines.dut, system)

    with allure.step("Get current time"):
        update_timezone(system)
        current_time = get_current_time(engines)

    return current_time, username, health_status, mgmt_port, output_dictionary


def factory_reset_general_pre_steps(engines, devices, system):
    port_type = devices.dut.switch_type.lower()

    with allure.step('Get health status'):
        health_status = get_health_status(system)

    with allure.step(f'Set description to {port_type} ports'):
        description = "with_keep_all_config_param"
        ports = Tools.RandomizationTool.select_random_ports(requested_ports_state=None, requested_ports_type=port_type,
                                                            num_of_ports_to_select=3).get_returned_value()
        apply_and_save_port = ports[0]
        just_apply_port = ports[1]
        not_apply_port = ports[2]

    with allure.step(f'Set and apply description to {port_type} port, save config after it'):
        apply_and_save_port.interface.set(NvosConst.DESCRIPTION, description, apply=True).verify_result()
        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
        NvueGeneralCli.save_config(engines.dut)
    with allure.step(f'Set and apply description to {port_type} port'):
        just_apply_port.interface.set(NvosConst.DESCRIPTION, description, apply=True).verify_result()
    with allure.step(f'Set description to {port_type} port'):
        not_apply_port.interface.set(NvosConst.DESCRIPTION, description, apply=False).verify_result()
    with allure.step('Validate ports description'):
        validate_port_description(engines.dut, apply_and_save_port, description)
        validate_port_description(engines.dut, just_apply_port, description)
        validate_port_description(engines.dut, not_apply_port, "")

    with allure.step("Add data before reset factory"):
        username = add_verification_data(engines.dut, system)

    with allure.step("Get current time"):
        update_timezone(system)
        current_time = get_current_time(engines)

    return health_status, current_time, apply_and_save_port, description, just_apply_port, not_apply_port, username


def get_health_status(system):
    system_output = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).get_returned_value()
    return system_output[SystemConsts.STATUS]

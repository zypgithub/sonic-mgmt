from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.general.security.tpm_attestation.helpers import factory_reset_tpm_checker
from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tests_nvos.system.gnmi.helpers import factory_reset_gnmi_checker
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_tools.nmx.Cluster import Cluster


def factory_reset_no_params_pre_steps(engines, platform_params, system, devices):
    init_cluster_status = None
    port_type = devices.dut.switch_type.lower()

    with allure.step('Create System object'):
        machine_type = platform_params['filtered_platform']

    if machine_type != 'MQM9520':
        with allure.step('Validate health status is OK'):
            system.validate_health_status(HealthConsts.OK)
            last_status_line = system.health.history.retry_get_health_history_file_summary_line()

    with allure.step(f'Set description to {port_type} ports'):
        logger.info(f'Set description to {port_type} ports')
        description = "test_reset_factory_without_params"
        ports = Tools.RandomizationTool.select_random_ports(requested_ports_state=None, requested_ports_type=port_type,
                                                            num_of_ports_to_select=3).get_returned_value()
        apply_and_save_port = ports[0]
        just_apply_port = ports[1]
        not_apply_port = ports[2]

    with allure.step(f'Set and apply description to {port_type} port, save config after it'):
        logger.info(f'Set and apply description to {port_type} port, save config after it')
        apply_and_save_port.interface.set(NvosConst.DESCRIPTION, description, apply=True).verify_result()
        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
        NvueGeneralCli.save_config(engines.dut)

    with allure.step(f'Set and apply description to {port_type} port'):
        logger.info(f"Set and apply description to {port_type} port")
        just_apply_port.interface.set(NvosConst.DESCRIPTION, description, apply=True).verify_result()

    with allure.step(f'Set description to {port_type} port'):
        logger.info(f"Set description to {port_type} port")
        not_apply_port.interface.set(NvosConst.DESCRIPTION, description, apply=False).verify_result()

    with allure.step('Check is Juliet Device'):
        if not isinstance(devices.dut, JulietSwitch):
            pytest.skip("It's not a Juliet Switch. Skipping NMX configuration")
        else:
            with allure.step("Config A reverse cluster state than configured"):
                cluster = Cluster()
                # Enable cluster and validate its enabled.
                init_cluster_status = ClusterTools.check_cluster_state(cluster, output_format=OutputFormat.json)
                ClusterTools.reverse_cluster_state(cluster, output_format=OutputFormat.json)

    with allure.step('Validate ports description'):
        logger.info("Validate ports description")
        validate_port_description(engines.dut, apply_and_save_port, description)
        validate_port_description(engines.dut, just_apply_port, description)
        validate_port_description(engines.dut, not_apply_port, "")

    with allure.step("Add data before reset factory"):
        username = add_verification_data(engines.dut, system)

    with allure.step("Get current time"):
        update_timezone(system)
        current_time = get_current_time(engines)

    with allure.step('pre factory reset TPM related check'):
        next(factory_reset_tpm_checker)

    with allure.step('pre factory reset GNMI cert related check'):
        next(factory_reset_gnmi_checker)

    return apply_and_save_port, current_time, just_apply_port, last_status_line, machine_type, not_apply_port, \
        username, init_cluster_status

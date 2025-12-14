from ngts.nvos_constants.constants_nvos import OutputFormat, LinkDetectionConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.ValidationTool import ValidationTool


# @disabled_access_ports
def factory_reset_no_params_post_steps(apply_and_save_port, engines, just_apply_port, pre_health_status, machine_type,
                                       not_apply_port, system, init_cluster_status, has_loopbox, devices, setup_name, standalone_system):
    with allure.step('update timezone'):
        update_timezone(system)
    if machine_type != 'MQM9520':
        with allure.step("Validate health status and report"):
            validate_health_status_report(system, pre_health_status)

    with allure.step("Verify description has been deleted"):
        validate_port_description(engines.dut, apply_and_save_port, "")
        validate_port_description(engines.dut, just_apply_port, "")
        validate_port_description(engines.dut, not_apply_port, "")

    with allure.step("Validate system contact information has been deleted"):
        system_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        assert system_output[SystemConsts.CONTACT] is None, "System {} in system show is {} instead of Null".\
            format(SystemConsts.CONTACT, system_output[SystemConsts.CONTACT])

    with allure.step("Validate system location information has been deleted"):
        system_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        assert system_output[SystemConsts.LOCATION] is None, "System {} in system show is {} instead of Null".\
            format(SystemConsts.LOCATION, system_output[SystemConsts.LOCATION])

    with allure.step("Validate health component unhealthy counters and timestamps are cleared"):
        health = Tools.OutputParsingTool.parse_json_str_to_dictionary(system.health.component.show()).get_returned_value()
        fan_unhealthy_count = int(health[HealthConsts.Component.FAN][HealthConsts.Component.UNHEALTHY_COUNT])
        fan_last_unhealthy = health[HealthConsts.Component.FAN][HealthConsts.Component.LAST_HEALTHY]
        assert fan_unhealthy_count == 0, "Fan unhealthy counter is not cleared"
        assert fan_last_unhealthy == "", "Fan last-unhealthy time is not cleared"

    if TestToolkit.devices.dut.has_nmx:
        with allure.step('Juliet Device Check'):
            with allure.step("Make sure cluster initial state restored"):
                cluster = Cluster()
                # Enable cluster and validate its enabled.
                state = ClusterTools.check_cluster_state(cluster, output_format=OutputFormat.json)
                assert state == init_cluster_status, f"State is {state} instead of {init_cluster_status}"

    if devices.dut.check_fec_capability():
        tested_api = TestToolkit.tested_api
        TestToolkit.tested_api = ApiType.NVUE
        with allure.step("Verify fec mode is set to {}".format(LinkDetectionConsts.FEC_MODE_DEFAULT)):
            link_output = apply_and_save_port.interface.link.show(output_format="auto")
            ValidationTool.verify_fec_config_in_auto_output(link_output, LinkDetectionConsts.FEC_MODE_DEFAULT)
        TestToolkit.tested_api = tested_api

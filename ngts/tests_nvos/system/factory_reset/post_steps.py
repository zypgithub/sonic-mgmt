from ngts.nvos_constants.constants_nvos import LinkDetectionConsts
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.Devices.IbDevice import CrocodileSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools, disabled_access_ports
from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tools.test_utils import allure_utils as allure


@disabled_access_ports
def factory_reset_no_params_post_steps(apply_and_save_port, engines, just_apply_port, pre_health_status, machine_type,
                                       not_apply_port, system, init_cluster_status):
    with allure.step('update timezone'):
        update_timezone(system)
    if machine_type != 'MQM9520':
        with allure.step("Validate health status and report"):
            validate_health_status_report(system, pre_health_status)
    with allure.step("Verify description has been deleted"):
        validate_port_description(engines.dut, apply_and_save_port, "")
        validate_port_description(engines.dut, just_apply_port, "")
        validate_port_description(engines.dut, not_apply_port, "")
    with allure.step('Check is Juliet Device'):
        if not isinstance(TestToolkit.devices.dut, JulietSwitch):
            # pytest.skip("It's not a Juliet Switch. Skipping NMX configuration")
            pass    # TODO: use Devices OM to do this!
        else:
            with allure.step("Make sure cluster initial state restored"):
                cluster = Cluster()
                # Enable cluster and validate its enabled.
                state = ClusterTools.check_cluster_state(cluster, output_format=OutputFormat.json)
                assert state == init_cluster_status, f"State is {state} instead of {init_cluster_status}"

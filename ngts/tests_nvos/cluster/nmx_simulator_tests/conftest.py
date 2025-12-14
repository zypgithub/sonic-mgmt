import pytest
import logging
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_tools import ClusterSimulation, ClusterTools
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.nvos_tools.infra.SecureBootTool import SecureBootTool
from ngts.nvos_tools.Devices.IbDevice import JulietScaleoutSwitch, JulietNonScaleoutSwitch, JulietSwitch


logger = logging.getLogger()


@pytest.fixture(scope="session")
def check_device_and_system_type_for_sdn(engines, devices, standalone_system):
    """
    Skip all SDN tests if device is not JulietScaleoutSwitch, if it's not a standalone system, or if it's a production system.

    This fixture ensures that SDN tests only run on dev JulietScaleoutSwitch systems in standalone mode
    """
    # Check if device is not JulietScaleoutSwitch or if it's a non-scaleout switch or if it's not a standalone system
    if (not isinstance(devices.dut, JulietScaleoutSwitch) or
        isinstance(devices.dut, JulietNonScaleoutSwitch) or
            not standalone_system):
        pytest.skip("SDN tests are supported only on JulietScaleoutSwitch in standalone mode. "
                    f"Current device type: {type(devices.dut).__name__}, Standalone: {standalone_system}")

    # Check if system is production
    if SecureBootTool.is_prod_system(engines.dut):
        pytest.skip("SDN tests are supported only on development systems. The current system is a production system.")


@pytest.fixture(scope="session")
def check_device_type_for_partition(devices, standalone_system):
    """
    Skip all partition tests if device is not JulietSwitch or if it's not a standalone system.

    This fixture ensures that partition tests only run on JulietSwitch systems in standalone mode
    """
    # Check if device is not JulietSwitch
    if not isinstance(devices.dut, JulietSwitch):
        pytest.skip("Partition tests are supported only on JulietSwitch. "
                    f"Current device type: {type(devices.dut).__name__}")

    # Check if it's not a standalone system
    if not standalone_system:
        pytest.skip("Partition tests are supported only in standalone mode. "
                    f"Current system mode: standalone={standalone_system}")


@pytest.fixture(scope="session", autouse=True)
def start_sdn_maintenance_state_simulation(engines, setup_name):
    try:
        ClusterSimulation.start_sdn_cluster_simulation(engines, setup_name)
        yield
    finally:
        ClusterSimulation.end_of_sdn_cluster_simulation(engines, setup_name)


@pytest.fixture(scope="function", autouse=True)
def enable_cluster_and_wait_nmx_controller_status(setup_name):
    cluster = Cluster()
    ClusterTools.start_cluster(cluster, setup_name)
    ClusterTools.wait_until_app_expected_status(cluster, ClusterConsts.NMX_CONTROLLER, 'ok')

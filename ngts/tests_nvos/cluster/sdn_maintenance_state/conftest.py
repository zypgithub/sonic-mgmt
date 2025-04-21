import pytest
import logging
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_tools import ClusterSimulation, ClusterTools
from ngts.nvos_tools.infra.SecureBootTool import SecureBootTool
from ngts.nvos_tools.Devices.IbDevice import JulietScaleoutSwitch


logger = logging.getLogger()


@pytest.fixture(scope="session", autouse=True)
def check_device_and_system_type(engines, devices):
    """
    Skip all tests if device is not JulietScaleoutSwitch or if it's a production system
    """
    # Check if device is JulietScaleoutSwitch
    if not isinstance(devices.dut, JulietScaleoutSwitch):
        pytest.skip("Tests are supported only on JulietScaleoutSwitch. The current device is not a JulietScaleoutSwitch")
    # Check if system is production
    if SecureBootTool.is_prod_system(engines.dut):
        pytest.skip("Tests are supported only on development systems. The current system is a production system.")


@pytest.fixture(scope="session", autouse=True)
def start_sdn_maintenance_state_simulation(engines, setup_name):
    ClusterSimulation.start_sdn_cluster_simulation(engines, setup_name)
    yield
    ClusterSimulation.end_of_sdn_cluster_simulation(engines, setup_name)


@pytest.fixture(scope="function", autouse=True)
def enable_cluster_and_wait_nmx_controller_status(setup_name):
    cluster = Cluster()
    ClusterTools.start_cluster(cluster, setup_name)
    ClusterTools.wait_until_app_expected_status(cluster, 'nmx-controller', 'ok')

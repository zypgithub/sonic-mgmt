import pytest
import logging
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_tools import ClusterSimulation, ClusterTools
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.nvos_tools.infra.SecureBootTool import SecureBootTool
from ngts.nvos_tools.Devices.IbDevice import JulietScaleoutSwitch, JulietNonScaleoutSwitch, JulietSwitch


logger = logging.getLogger()


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

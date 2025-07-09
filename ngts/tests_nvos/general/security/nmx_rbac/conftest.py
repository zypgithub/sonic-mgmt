import pytest

from ngts.nvos_tools.infra.NmxRbacTool import NmxRbacTool
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Apps import ClusterApp
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.general.security.certificate.helpers import delete_certificates
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import ClusterConsts, RbacConsts

apps = [pytest.param(ClusterConsts.NMX_CONTROLLER, id='nmx_c'),
        pytest.param(ClusterConsts.NMX_TELEMETRY, id='nmx_t')]


@pytest.fixture(scope='function')
def enable_cluster(setup_name):
    with allure.step(f'Enable cluster'):
        cluster = Cluster()
        cluster_tools = ClusterTools()
        cluster_tools.start_cluster(cluster, setup_name)
    yield cluster
    with allure.step(f'Disable cluster'):
        cluster_tools.stop_cluster(cluster)


@pytest.fixture(scope='function', params=apps)
def cluster_rbac_tools(enable_cluster, request, engines):
    cluster: Cluster = enable_cluster
    cluster_app: ClusterApp = cluster.apps.app_name[request.param]
    cluster_tools = NmxRbacTool(cluster, engines.dut, cluster_app)
    yield cluster_tools
    with allure.step(f'Cleanup for RBAC test'):
        cluster_tools.restore_rbac_mode()
        cluster_tools.restore_rbac_file()
        app_manager = cluster_app.manager
        app_manager.encryption.action_restore().verify_result()
        app_manager.certificate.action_restore().verify_result()
        app_manager.ca_certificate.action_restore().verify_result()
        app_manager.action_restore().verify_result()
        cluster_tools.delete_all_rbac_files()
        delete_certificates()
        delete_certificates(ca=True)

"""
Conftest for NV Bridge encryption tests.
"""

import logging
import os
import time

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.NvCommand import NvCommand
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.helpers import (
    delete_certificates,
)
from ngts.tests_nvos.general.security.helpers import generate_certs, get_test_certs_dir_location
from ngts.tests_nvos.general.security.nmx_cert.constants import ENABLED
from ngts.tests_nvos.general.security.nmx_cert.helpers import set_cluster_state
from ngts.tests_nvos.general.security.nv_bridge.helpers import (
    generate_internal_certs,
    import_internal_certs,
    is_cluster_enabled,
)
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger(__name__)

apps = [pytest.param(ClusterConsts.NMX_CONTROLLER, id="nmx_c")]


@pytest.fixture(scope="module")
def generate_internal_bridge_certs(engines, dut_hostname):
    """Generate required certificates for testing."""
    with allure.step("import test certificates"):
        server_cert, client_ca_cert = generate_internal_certs(engines, "internal_nv_bridge", dut_hostname)
    yield server_cert, client_ca_cert


@pytest.fixture(scope="function")
def import_certs(engines, generate_internal_bridge_certs):
    """Import required certificates for testing."""
    server_cert, client_ca_cert = generate_internal_bridge_certs
    with allure.step("import test certificates"):
        import_internal_certs(engines, [server_cert, client_ca_cert], [client_ca_cert, server_cert])
    yield server_cert, client_ca_cert
    with allure.step("cleanup certificates"):
        delete_certificates()
        delete_certificates(ca=True)


@pytest.fixture(scope="function")
def generate_certs_with_alt(engines, dut_hostname):
    certs_location = get_test_certs_dir_location("certs_with_alt", dut_hostname)
    cn = "nv-bridge-client"
    dn = dut_hostname
    ip = engines.dut.ip
    with allure.step("Generate 2 certificates (cert and alt-cert) signed by the same CA"):
        cert = CertInfo("cert", "certificate for test", "", "", "", "", dn, ip, "", f"{cn}")
        cert_alt = CertInfo("alt-cert", "alternate certificate for test", "", "", "", "", dn, ip, "", f"{cn}")
        bridge_certs = [cert, cert_alt]
        bridge_certs_dir = os.path.join(certs_location, "bridge_certs")
        generate_certs(bridge_certs_dir, bridge_certs)
    with allure.step("Generate other certificate signed by a different CA"):
        other_cert = CertInfo("other-cert", "other certificate for test", "", "", "", "", dn, ip, "", f"{cn}")
        other_cert_dir = os.path.join(certs_location, "other_certs")
        generate_certs(other_cert_dir, [other_cert])
    yield cert, cert_alt, other_cert


@pytest.fixture(scope="function")
def import_certs_with_alt(engines, generate_certs_with_alt):
    """Import required certificates for testing."""
    cert, cert_alt, other_cert = generate_certs_with_alt
    with allure.step("import test certificates"):
        import_internal_certs(engines, [cert, cert_alt, other_cert], [cert, other_cert])
    yield cert, cert_alt, other_cert
    with allure.step("cleanup certificates"):
        delete_certificates()
        delete_certificates(ca=True)


@pytest.fixture(scope="function")
def enable_cluster(setup_name, engines):
    with allure.step("Enable cluster"):
        cluster = Cluster()
        cluster_tools = ClusterTools()
        cluster.node.primary.set_cluster_node(
            op_param_name=SystemConsts.NV_BRIDGE_NODE_SERVER,
            op_param_value=engines.dut.ip,
        )
        cluster_tools.start_cluster(cluster, setup_name)
        set_cluster_state(ENABLED, True)
    yield cluster
    with allure.step("Disable cluster"):
        cluster.unset().verify_result()
        cluster_tools.stop_cluster(cluster)


@pytest.fixture(scope="function")
def disable_cluster(setup_name):
    """Ensure cluster is disabled after the test."""
    cluster = Cluster()
    cluster_tools = ClusterTools()
    with allure.step("ensure cluster is disabled before the test"):
        if is_cluster_enabled():
            cluster_tools.stop_cluster(cluster)
    yield
    with allure.step("ensure cluster is disabled after the test"):
        if is_cluster_enabled():
            cluster_tools.stop_cluster(cluster)


@pytest.fixture
def restore_system_internal_config(nv_command: NvCommand):
    """Restore system internal config after test."""
    yield
    with allure.step("restore system internal config"):
        try:
            nv_command.system.internal.encryption.action_restore().verify_result()
            nv_command.system.internal.certificate.action_restore().verify_result()
            nv_command.system.internal.ca_certificate.action_restore().verify_result()
            nv_command.system.internal.alternate_certificate.action_restore().verify_result()
        except Exception as e:
            logger.warning(f"Failed to restore system internal config: {e}")
            if is_bug_active(4824684):
                time.sleep(100)
                nv_command.system.internal.action_restore().verify_result()
            raise


@pytest.fixture(scope="function", params=apps)
def restore_cluster_app_internal_config(request):
    """Restore cluster app internal config after test."""
    yield request.param
    with allure.step("restore cluster app internal config"):
        try:
            cluster = Cluster()
            app_name = request.param
            app = cluster.apps.app_name[app_name]
            app.internal.encryption.action_restore().verify_result()
            app.internal.certificate.action_restore().verify_result()
            app.internal.alternate_certificate.action_restore().verify_result()
            app.internal.ca_certificate.action_restore().verify_result()
        except Exception as e:
            logger.warning(f"Failed to restore cluster app internal config: {e}")
            if is_bug_active(4824684):
                time.sleep(100)
                app.internal.action_restore().verify_result()
            raise

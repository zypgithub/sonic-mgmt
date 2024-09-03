import pytest

from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.certificate.helpers import import_test_certs
from ngts.tests_nvos.general.security.nmx_cert.constants import STATE, ENABLED, DISABLED
from ngts.tests_nvos.system.gnmi.conftest import scp_player


@pytest.fixture(scope='session', autouse=True)
def setup_import_certs(scp_player, engines):
    import_test_certs(scp_player, engines.dut, [TestCert.cert_valid_1, TestCert.cert_valid_2])
    yield
    # delete_certificates()     # TODO: uncomment after finish testing
    # delete_certificates(True)


@pytest.fixture()
def import_certs_back_after_test(scp_player, engines):
    yield
    import_test_certs(scp_player, engines.dut, [TestCert.cert_valid_1, TestCert.cert_valid_2])


def clear_manager_config():
    cluster = Cluster()
    cluster.set(STATE, ENABLED, apply=True).verify_result()
    cluster.manager.encryption.action_restore().verify_result()
    cluster.manager.certificate.action_restore().verify_result()
    cluster.manager.ca_certificate.action_restore().verify_result()
    cluster.manager.action_restore().verify_result()


@pytest.fixture(autouse=True)
def setup_cleared_manager(scp_player, engines):
    clear_manager_config()


@pytest.fixture()
def enable_cluster(setup_cleared_manager):
    Cluster().set(STATE, ENABLED, apply=True).verify_result()


@pytest.fixture()
def disable_cluster(setup_cleared_manager):
    Cluster().set(STATE, DISABLED, apply=True).verify_result()

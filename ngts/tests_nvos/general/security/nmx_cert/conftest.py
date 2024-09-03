from typing import List

import pytest

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.helpers import remove_etc_host_mapping_to_dn, add_etc_host_mapping_to_dn
from ngts.tests_nvos.general.security.nmx_cert.constants import STATE, ENABLED, DISABLED
from ngts.tests_nvos.general.security.nmx_cert.helpers import import_certificates
from ngts.tests_nvos.system.gnmi.conftest import scp_player
from ngts.tests_nvos.system.gnmi.constants import ETC_HOSTS


@pytest.fixture(scope='session', autouse=True)
def test_certs():
    return [TestCert.cert_valid_1, TestCert.cert_valid_2]


def import_test_certs(scp_player: LinuxSshEngine, dut_engine: LinuxSshEngine, certs: List[CertInfo]):
    import_certificates(scp_player, dut_engine, certs)
    import_certificates(scp_player, dut_engine, certs, True)


@pytest.fixture(scope='session', autouse=True)
def setup_import_certs(scp_player, engines, test_certs):
    import_test_certs(scp_player, engines.dut, test_certs)
    yield
    # delete_certificates()     # TODO: uncomment after finish testing
    # delete_certificates(True)


@pytest.fixture()
def import_certs_back_after_test(scp_player, engines, test_certs):
    yield
    import_test_certs(scp_player, engines.dut, test_certs)


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


@pytest.fixture(scope='module', autouse=True)
def add_etc_host_mapping_for_test_cert(engines, test_certs):
    cert = test_certs[0]
    with allure.step(f'add mapping of new dut hostname to {ETC_HOSTS}'):
        cmd_runner = CmdRunner()
        remove_etc_host_mapping_to_dn(cert.dn, cmd_runner)
        add_etc_host_mapping_to_dn(cert.dn, engines.dut.ip, cmd_runner)
    yield
    with allure.step(f'remove hostname mapping from {ETC_HOSTS}'):
        remove_etc_host_mapping_to_dn(cert.dn, cmd_runner)

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import CacertType
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.certificate.helpers import import_test_certs, delete_certificates
from ngts.tests_nvos.general.security.helpers import remove_etc_host_mapping_to_dn, add_etc_host_mapping_to_dn
from ngts.tests_nvos.general.security.nmx_cert.constants import STATE, ENABLED, DISABLED
from ngts.tests_nvos.helpers.pytest_helpers import get_cur_test_param_value
from ngts.tests_nvos.system.gnmi.conftest import scp_player
from ngts.tests_nvos.system.gnmi.constants import ETC_HOSTS


@pytest.fixture(autouse=True)
def use_external_ca_type(request) -> bool:
    return get_cur_test_param_value(request, 'ca_type') == CacertType.EXTERNAL
    # use_external = random.choice([False, True])
    # with allure.step(f'use {"External" if use_external else "Global (default)"} CAs type for the test'):
    #     return use_external


@pytest.fixture(scope='session', autouse=True)
def test_certs():
    return [TestCert.cert_valid_1, TestCert.cert_valid_2]


def clear_manager_config():
    cluster = Cluster()
    cluster.set(STATE, ENABLED, apply=True).verify_result()
    cluster.manager.encryption.action_restore().verify_result()
    cluster.manager.certificate.action_restore().verify_result()
    cluster.manager.ca_certificate.action_restore().verify_result()
    cluster.manager.action_restore().verify_result()


def clear_everything():
    with allure.step('clear everything'):
        clear_manager_config()
        delete_certificates()
        delete_certificates(True)


@pytest.fixture(scope='session', autouse=True)
def cleanup_session(scp_player, engines, test_certs):
    clear_everything()
    yield
    clear_everything()


@pytest.fixture(autouse=True)
def setup_case(scp_player, engines, test_certs, use_external_ca_type):
    clear_everything()
    import_test_certs(scp_player, engines.dut, test_certs, use_external_ca_type)
    yield
    clear_everything()


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

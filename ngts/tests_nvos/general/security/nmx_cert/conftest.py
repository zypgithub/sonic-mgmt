import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import CacertType
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.certificate.helpers import import_test_certs, delete_certificates
from ngts.tests_nvos.general.security.helpers import remove_etc_host_mapping_to_dn, add_etc_host_mapping_to_dn
from ngts.tests_nvos.general.security.nmx_cert.constants import STATE, DISABLED
from ngts.tests_nvos.general.security.nmx_cert.helpers import enable_cluster, restore_cluster_app_manager_state
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
    return [TestCert.cert_valid_1, TestCert.cert_valid_2, TestCert.cert_valid_3]


def clear_manager_config(app_name: str, force_wait: bool = False):
    enable_cluster(force_wait=force_wait)
    app = Cluster().apps.app_name[app_name]
    restore_cluster_app_manager_state(app.manager)
    app.manager.encryption.action_restore().verify_result()
    app.manager.certificate.action_restore().verify_result()
    app.manager.ca_certificate.action_restore().verify_result()


def clear_everything(app_name: str):
    with allure.step('clear everything'):
        clear_manager_config(app_name, True)
        delete_certificates()
        delete_certificates(True)


@pytest.fixture(autouse=True)
def setup_case(scp_player, engines, test_certs, use_external_ca_type, request):
    app_name: str = get_cur_test_param_value(request, 'app_name')
    if app_name:
        clear_everything(app_name)

    import_test_certs(scp_player, engines.dut, test_certs, use_external_ca_type)


@pytest.fixture()
def disable_cluster(setup_case):
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

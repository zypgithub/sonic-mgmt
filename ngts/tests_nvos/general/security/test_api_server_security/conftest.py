import pytest

from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.tests_nvos.general.security.certificate.helpers import import_test_certs, delete_certificates
from ngts.tests_nvos.general.security.helpers import setup_certs_for_tests
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.general.security.test_api_server_security.constants import TEST_CERTS
from ngts.tests_nvos.general.security.test_api_server_security.helpers import cleanup_mtls_test
from ngts.tests_nvos.helpers.pytest_helpers import get_cur_test_param_value
from ngts.tests_nvos.system.gnmi.conftest import scp_player


@pytest.fixture(scope='module', autouse=True)
def import_required_certs(scp_player, engines):
    import_test_certs(scp_player, engines.dut, TEST_CERTS)
    yield
    delete_certificates()
    delete_certificates(True)


@pytest.fixture(scope='session', autouse=True)
def verify_curl_installed():
    CurlTool('', '', '', verify_tools_installed=True)


@pytest.fixture()
def import_missing_cas_after_test(scp_player, engines):
    yield
    import_test_certs(scp_player, engines.dut, TEST_CERTS)


@pytest.fixture(scope='module')
def certs_ipv4_no_import(engines, dut_hostname, scp_player):
    tmp_certs_dir, certs = setup_certs_for_tests('api-sec', ['api-cert1', 'api-cert2', 'api-cert3'], engines,
                                                 dut_hostname, False, scp_player, engines.dut.ip)
    yield certs
    cleanup_mtls_test(tmp_certs_dir, certs, certs)


@pytest.fixture(scope='module')
def certs_ipv6_no_import(engines, dut_hostname, scp_player, dut_ipv6_addr):
    tmp_certs_dir, certs = setup_certs_for_tests('api-sec', ['api-cert1', 'api-cert2', 'api-cert3'], engines,
                                                 dut_hostname, False, scp_player, dut_ipv6_addr)
    yield certs
    cleanup_mtls_test(tmp_certs_dir, certs, certs)


@pytest.fixture
def certs_no_import(request, certs_ipv4_no_import, certs_ipv6_no_import):
    if get_cur_test_param_value(request, 'addressing_type') == AddressingType.IPV6:
        return certs_ipv6_no_import
    else:
        return certs_ipv4_no_import

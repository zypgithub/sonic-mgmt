import pytest

from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.tests_nvos.general.security.certificate.helpers import import_test_certs, delete_certificates
from ngts.tests_nvos.general.security.test_api_server_security.constants import TEST_CERTS
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

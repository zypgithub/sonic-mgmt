import pytest

from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.helpers import delete_certificates
from ngts.tests_nvos.general.security.helpers import delete_all_imported_cas, \
    delete_all_imported_certs
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope="function")
def system_cleanup():
    system = System()
    yield system
    system.gnmi_server.unset(apply=True).verify_result()
    delete_certificates()
    delete_certificates(ca=True)


def cleanup_spiffe_gnmi():
    with allure.step('cleanup gnmi spiffe test'):
        System().gnmi_server.unset(apply=True).verify_result()
        delete_all_imported_cas()
        delete_all_imported_certs()

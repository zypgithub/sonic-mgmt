import pytest

from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.helpers import delete_certificates


@pytest.fixture(scope="function")
def system_cleanup():
    system = System()
    yield system
    system.gnmi_server.unset(apply=True).verify_result()
    delete_certificates()
    delete_certificates(ca=True)

from typing import List

import pytest

from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.certificate.helpers import import_test_certs, delete_certificates
from ngts.tests_nvos.system.gnmi.conftest import scp_player


@pytest.fixture(scope='session', autouse=True)
def test_certs() -> List[CertInfo]:
    return [TestCert.cert_valid_1, TestCert.cert_valid_2, TestCert.cert_valid_3]


@pytest.fixture(scope='module')
def import_required_certs(test_certs, scp_player, engines):
    import_test_certs(scp_player, engines.dut, test_certs)
    yield
    delete_certificates()
    delete_certificates(True)

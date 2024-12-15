import pytest

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.helpers import add_etc_host_mapping_to_dn, remove_etc_host_mapping_to_dn
from ngts.tests_nvos.system.gnmi.constants import ETC_HOSTS
from ngts.tools.test_utils import allure_utils as allure


def clear_existing_certs():
    system = System()
    with allure.step('delete imported certificates'):
        certs = OutputParsingTool.parse_json_str_to_dictionary(system.security.certificate.show()).get_returned_value()
        for cert in certs:
            system.security.certificate.cert_id[cert].action_delete().verify_result()
    with allure.step('delete imported ca-certificates'):
        certs = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.ca_certificate.show()).get_returned_value()
        for cert in certs:
            system.security.ca_certificate.cert_id[cert].action_delete().verify_result()


@pytest.fixture(scope='function')
def clear_certs():
    clear_existing_certs()
    yield
    System().api.unset(apply=True).verify_result()
    clear_existing_certs()


@pytest.fixture(scope='module', autouse=True)
def clear_certs_session():
    clear_existing_certs()
    yield
    System().api.unset(apply=True).verify_result()
    clear_existing_certs()


@pytest.fixture(scope='module', autouse=True)
def etc_hosts_mapping(engines):
    cert: CertInfo = TestCert.cert_valid_1
    with allure.step(f'add ipv4 mapping of new dut hostname to {ETC_HOSTS}'):
        remove_etc_host_mapping_to_dn(cert.dn)
        add_etc_host_mapping_to_dn(cert.dn, engines.dut.ip)
    yield
    with allure.step(f'remove ipv4 mapping of new dut hostname to {ETC_HOSTS}'):
        remove_etc_host_mapping_to_dn(cert.dn)

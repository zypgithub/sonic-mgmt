import pytest

from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.system.gnmi.constants import ETC_HOSTS, GNMI_TEST_CERT
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='module', autouse=True)
def clear_certs():
    yield
    system = System()
    with allure.step('delete imported certificates'):
        certs = OutputParsingTool.parse_json_str_to_dictionary(system.security.certificate.show()).get_returned_value()
        for cert in certs:
            system.security.certificate.cert_id[cert].action_delete().verify_result()
    with allure.step('delete imported ca-certificates'):
        certs = OutputParsingTool.parse_json_str_to_dictionary(system.security.ca_certificate.show()).get_returned_value()
        for cert in certs:
            system.security.ca_certificate.cert_id[cert].action_delete().verify_result()


@pytest.fixture(scope='module', autouse=True)
def curl_cert_hostname(engines):
    cert = GNMI_TEST_CERT
    with allure.step(f'add mapping of new dut hostname to {ETC_HOSTS}'):
        cmd_runner = CmdRunner()
        cmd_runner.run_cmd_in_process(f'echo "{engines.dut.ip} {cert.dn}" | sudo tee -a {ETC_HOSTS}')
    yield
    with allure.step(f'remove hostname mapping fro {ETC_HOSTS}'):
        cmd_runner.run_cmd_in_process(f"sudo sed -i '/{cert.dn}/d' {ETC_HOSTS}")

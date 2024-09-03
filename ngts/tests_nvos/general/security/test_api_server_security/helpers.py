from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.test_api_server_security.constants import API_INSTALLED, INSTALLED


def verify_installed_cacert(all_ca_names, expect_installed_ca):
    system = System()
    if expect_installed_ca is None:
        cacerts_conf = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.ca_certificate.show()).get_returned_value()
        assert all(API_INSTALLED not in cacerts_conf[ca][INSTALLED] for ca in
                   all_ca_names), f'some ca is unexpectedly installed for api\ncas info:\n{cacerts_conf}'
    else:
        cacert_conf = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.ca_certificate.cert_id[expect_installed_ca].show()).get_returned_value()
        assert API_INSTALLED in cacert_conf[
            INSTALLED], f'ca "{expect_installed_ca}" is not installed for api as expected\nca info:\n{cacert_conf}'

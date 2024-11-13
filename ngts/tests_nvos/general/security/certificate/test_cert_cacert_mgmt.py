import random

import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, RebootTestFlowType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.certificate.helpers import verify_cert_in_expected_locations, \
    verify_ca_in_expected_locations
from ngts.tests_nvos.system.gnmi.conftest import scp_player
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player


@pytest.mark.track_serial_console
@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
@pytest.mark.parametrize('reboot_flow', random.sample(RebootTestFlowType.ALL_TYPES, 1))
def test_cert_mgmt_use_cert_for_rest_api_tls(test_api, reboot_flow, engines, scp_player, clear_certs):
    """
    Verify that:
    when not saving config with installed ca/certs – config should be cleared, ca/certs should remain (and exist in show without install info)

    1.  import cert
    2.  bind to rest server
    3.  import ca1 (global/external)
    4.  import ca2 (external)
    5.  reboot
    6.  verify cert exist in show and not installed
    7.  verify cas exist and not installed
    8.  verify cert in certs locations
    9.  verify cas in expected locations
    """
    TestToolkit.tested_api = test_api
    is_save_flow = reboot_flow == RebootTestFlowType.WITH_SAVE

    system = System()
    security = system.security

    cert1 = TestCert.cert_valid_1.copy('cert1')
    ca1 = TestCert.cert_valid_2.copy('ca1')
    cert_bundle_uri = generate_scp_uri_using_player(scp_player, cert1.p12_bundle)
    ca_uri = generate_scp_uri_using_player(scp_player, ca1.cacert)

    with allure.step('import certs'):
        security.certificate.cert_id[cert1.name].action_import(uri_bundle=cert_bundle_uri,
                                                               passphrase=cert1.p12_password).verify_result()
    with allure.step('import cas'):
        security.ca_certificate.cert_id[ca1.name].action_import(uri=ca_uri).verify_result()
    if is_save_flow:
        with allure.step('save config'):
            NvueGeneralCli.save_config(engines.dut)
    with allure.step('reboot the system'):
        System().action('reboot', param_name='force', expect_reboot=True, output_format=None).verify_result()
        engines.dut.disconnect()
    with allure.step('verify after reboot'):
        with allure.independent_step('verify cert exist in show'):
            out = OutputParsingTool.parse_json_str_to_dictionary(security.certificate.show()).get_returned_value()
            assert cert1.name in out, f'cert {cert1.name} expected to be in output but is not\n{out}'
        with allure.independent_step('verify cas exist'):
            out = OutputParsingTool.parse_json_str_to_dictionary(security.ca_certificate.show()).get_returned_value()
            assert ca1.name in out, f'ca {ca1.name} expected to be in output but is not\n{out}'
        with allure.independent_step('verify cert in certs locations'):
            verify_cert_in_expected_locations(cert1.name, engines.dut)
        with allure.independent_step('verify cas in expected locations'):
            verify_ca_in_expected_locations(ca1.name, ca1, engines.dut)

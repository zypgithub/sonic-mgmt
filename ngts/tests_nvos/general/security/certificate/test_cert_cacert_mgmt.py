import random
from typing import List

import pytest

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, RebootTestFlowType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.Security import Security
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.conftest import get_dut_hostname
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.certificate.helpers import verify_cert_in_expected_locations, \
    verify_ca_in_expected_locations, import_certificates
from ngts.tests_nvos.general.security.helpers import setup_certs_for_tests, cleanup_certs_for_tests
from ngts.tests_nvos.system.gnmi.conftest import scp_player
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player


@pytest.mark.track_serial_console
@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
@pytest.mark.parametrize('reboot_flow', random.sample(RebootTestFlowType.ALL_TYPES, 1))
def test_certs_mgmt_reboot_case(test_api, reboot_flow, engines, scp_player, clear_certs):
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
    ca2 = TestCert.cert_valid_3.copy('ca2')
    cert_bundle_uri = generate_scp_uri_using_player(scp_player, cert1.p12_bundle)
    ca1_uri = generate_scp_uri_using_player(scp_player, ca1.cacert)
    ca2_uri = generate_scp_uri_using_player(scp_player, ca2.cacert)

    with allure.step('import certs'):
        security.certificate.cert_id[cert1.name].action_import(uri_bundle=cert_bundle_uri,
                                                               passphrase=cert1.p12_password).verify_result()
    with allure.step('import cas'):
        security.ca_certificate.cert_id[ca1.name].action_import(uri=ca1_uri).verify_result()
        security.ca_certificate.cert_id[ca2.name].action_import(uri=ca2_uri, external=True).verify_result()
    if is_save_flow:
        with allure.step('save config'):
            NvueGeneralCli.save_config(engines.dut)
    with allure.step('reboot the system'):
        System().action_reboot('force').verify_result()
        engines.dut.disconnect()
    with allure.step('verify after reboot'):
        with allure.independent_step('verify cert exist in show'):
            out = OutputParsingTool.parse_json_str_to_dictionary(security.certificate.show()).get_returned_value()
            assert cert1.name in out, f'cert {cert1.name} expected to be in output but is not\n{out}'
        with allure.independent_step('verify cas exist'):
            out = OutputParsingTool.parse_json_str_to_dictionary(security.ca_certificate.show()).get_returned_value()
            for ca in [ca1, ca2]:
                with allure.independent_step(f'verify ca: {ca.name}'):
                    assert ca.name in out, f'ca {ca.name} expected to be in output but is not\n{out}'
        with allure.independent_step('verify cert in certs locations'):
            verify_cert_in_expected_locations(cert1.name, engines.dut)
        with allure.independent_step('verify cas in expected locations'):
            verify_ca_in_expected_locations(ca1.name, ca1, engines.dut)
            verify_ca_in_expected_locations(ca2.name, ca2, engines.dut, True)


# generator functions


class CaInfo:
    def __init__(self, ca_info: CertInfo, external: bool, scp_player: LinuxSshEngine):
        self.ca_info: CertInfo = ca_info
        self.external: bool = external
        self.uri = generate_scp_uri_using_player(scp_player, ca_info.cacert)


def checker_setup_steps(security: Security, cert: CertInfo, cas: List[CaInfo], engines, scp_player: LinuxSshEngine):
    with allure.step('import certs'):
        import_certificates(scp_player, engines.dut, [cert])
    with allure.step('import cas'):
        for ca in cas:
            with allure.independent_step(f'import {ca.ca_info.name}'):
                security.ca_certificate.cert_id[ca.ca_info.name].action_import(uri=ca.uri, external=ca.external).verify_result()
    with allure.step('save config'):
        NvueGeneralCli.save_config(engines.dut)


def setup_cert_mgmt_checker(engines):
    scp_player = get_scp_player(engines)
    dut_hostname = get_dut_hostname(engines)
    security = System().security

    with allure.step('prepare certs'):
        tmp_certs_dir, certs = setup_certs_for_tests('cert-mgmt',
                                                     ['cert-mgmt-cert1', 'cert-mgmt-ca1', 'cert-mgmt-ca2'],
                                                     engines, dut_hostname, False, scp_player)
        cert = certs[0]
        cas: List[CaInfo] = [
            CaInfo(certs[1], False, scp_player),
            CaInfo(certs[2], True, scp_player),
        ]
    with allure.step('import certs'):
        import_certificates(scp_player, engines.dut, [cert])
    with allure.step('import cas'):
        for ca in cas:
            with allure.independent_step(f'import {ca.ca_info.name}'):
                security.ca_certificate.cert_id[ca.ca_info.name].action_import(uri=ca.uri,
                                                                               external=ca.external).verify_result()

    return tmp_certs_dir, cert, cas


def certs_mgmt_factory_reset_no_params_check():
    """
    Verify that:
    when saving config with installed ca/certs – config and ca/certs should be cleared

    * same for: no params, keep basic, keep all config

    import cert

    1. import cert
    2. import ca (global/external)
    3. import ca2 (external)
    4. save
    5. do reset factory
    6. verify no cert in show
    7. verify no cas in show
    8. verify no cert in expected locations
    9. verify no cas in expected locations
    """
    engines = TestToolkit.engines
    security = System().security

    with allure.step('setup'):
        tmp_certs_dir, cert, cas = setup_cert_mgmt_checker(engines)

    yield  # factory reset

    try:
        with allure.step('verify after factory reset'):
            with allure.independent_step('verify no cert in show'):
                out = OutputParsingTool.parse_json_str_to_dictionary(security.certificate.show()).get_returned_value()
                assert out == {}, f'certs show not as expected\nexpected: {"{}"}\nactual:\n{out}'
            with allure.independent_step('verify no cas in show'):
                out = OutputParsingTool.parse_json_str_to_dictionary(
                    security.ca_certificate.show()).get_returned_value()
                assert out == {}, f'cas show not as expected\nexpected: {"{}"}\nactual:\n{out}'
            with allure.independent_step('verify cert not in certs locations'):
                verify_cert_in_expected_locations(cert.name, engines.dut, False)
            with allure.independent_step('verify cas not in expected locations'):
                for ca in cas:
                    with allure.independent_step(ca.ca_info.name):
                        verify_ca_in_expected_locations(ca.ca_info.name, ca.ca_info, engines.dut, ca.external, False)
    finally:
        with allure.step('cleanup'):
            cleanup_certs_for_tests(tmp_certs_dir, [cert], [ca.ca_info for ca in cas])

    yield  # to prevent StopIteration on the 2nd next() call


def certs_mgmt_factory_reset_keep_only_files_check():
    """
    Verify that:
    when saving config with installed ca/certs – config and ca/certs should be cleared

    import cert

    1. import cert
    2. import ca (global/external)
    3. import ca2 (external)
    4. save
    5. do reset factory
    6. verify cert exist in show
    7. verify cas exist in show
    8. verify cert in expected locations
    9. verify cas in expected locations
    """
    engines = TestToolkit.engines
    security = System().security

    with allure.step('setup'):
        tmp_certs_dir, cert, cas = setup_cert_mgmt_checker(engines)

    yield  # factory reset

    try:
        with allure.step('verify after factory reset'):
            with allure.independent_step('verify cert exist in show'):
                out = OutputParsingTool.parse_json_str_to_dictionary(security.certificate.show()).get_returned_value()
                assert cert.name in out, f'cert {cert.name} expected to be in output but is not\n{out}'
            with allure.independent_step('verify cas exist'):
                out = OutputParsingTool.parse_json_str_to_dictionary(
                    security.ca_certificate.show()).get_returned_value()
                missing_cas = [ca.ca_info.name for ca in cas if ca.ca_info.name not in out]
                assert not missing_cas, f'{missing_cas} are missing from ca show output\n{out}'
            with allure.independent_step('verify cert in certs locations'):
                verify_cert_in_expected_locations(cert.name, engines.dut)
            with allure.independent_step('verify cas in expected locations'):
                for ca in cas:
                    with allure.independent_step(ca.ca_info.name):
                        verify_ca_in_expected_locations(ca.ca_info.name, ca.ca_info, engines.dut, ca.external)
    finally:
        with allure.step('cleanup'):
            cleanup_certs_for_tests(tmp_certs_dir, [cert], [ca.ca_info for ca in cas])

    yield  # to prevent StopIteration on the 2nd next() call


def certs_mgmt_upgrade_check():
    """
    Verify that:
    when saving config with installed ca/certs – config and ca/certs should be kept

    1. import cert
    2. import ca (global/external)
    3. import ca2 (external)
    4. save
    5. upgrade
    6. verify cert exist in show
    7. verify cas exist and installed
    8. verify cert in certs locations
    9. verify cas in expected locations
    """
    engines = TestToolkit.engines
    scp_player = get_scp_player(engines)
    system = System()
    security = system.security
    cert1 = TestCert.cert_valid_1.copy('cert-mgmt-cert1')

    cas: List[CaInfo] = [
        CaInfo(TestCert.cert_valid_2.copy('cert-mgmt-ca1'), False, scp_player),
        CaInfo(TestCert.cert_valid_3.copy('cert-mgmt-ca2'), True, scp_player),
    ]

    checker_setup_steps(security, cert1, cas, engines, scp_player)

    yield  # upgrade

    with allure.step('verify after upgrade'):
        with allure.independent_step('verify cert exist in show'):
            out = OutputParsingTool.parse_json_str_to_dictionary(security.certificate.show()).get_returned_value()
            assert cert1.name in out, f'cert {cert1.name} expected to be in output but is not\n{out}'
        with allure.independent_step('verify cas exist'):
            out = OutputParsingTool.parse_json_str_to_dictionary(
                security.ca_certificate.show()).get_returned_value()
            missing_cas = [ca.ca_info.name for ca in cas if ca.ca_info.name not in out]
            assert not missing_cas, f'{missing_cas} are missing from ca show output\n{out}'
        with allure.independent_step('verify cert in certs locations'):
            verify_cert_in_expected_locations(cert1.name, engines.dut)
        with allure.independent_step('verify cas in expected locations'):
            for ca in cas:
                with allure.independent_step(ca.ca_info.name):
                    verify_ca_in_expected_locations(ca.ca_info.name, ca.ca_info, engines.dut, ca.external)

    yield  # to prevent StopIteration on the 2nd next() call

import random
from typing import List

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, TestFlowType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.bmc.bmc_erot_attestation.helpers import randomize_hex_str
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import TestCert, CaShowFields
from ngts.tests_nvos.general.security.certificate.helpers import import_certificates, \
    verify_ca_in_expected_locations, send_curl_with_and_verify
from ngts.tests_nvos.general.security.nmx_cert.constants import EncryptionMode
from ngts.tests_nvos.general.security.test_api_server_security.constants import CERTIFICATE, CA_CERTIFICATE
from ngts.tests_nvos.system.gnmi.conftest import scp_player
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player


@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cacert_mgmt_cacert_cli(test_api, engines, scp_player, clear_certs):
    """
    Verify that all CLI work and check values change properly in show

    1.  Show cas – expect no data – {}
    2.  Import ca1 using data
    3.  Import ca2 using URI
    4.  One of the imports should be external
    5.  Show cas – expect cert1,2 in output
    6.  Verify files in expected locations
    7.  Verify global ca content is in CAs pool file, and external is not
    8.  Show a global ca and an external ca – expect fields [count, installed, serial-number, valid-from, valid-to, type]
    9.  Verify count = 1
    10. Verify installed empty {}
    11. Verify all the rest non empty strings
    12. Verify type – ‘external’ if imported with ‘skip_global’; ‘global’ otherwise
    13. Show dump of any cert – expect ‘CN = Root CA’ & ‘CA:TRUE’ in output (sanity)
    14. Show installed of any cert – expect empty {}
    15. Delete a ca
    16. Show Cas – expect deleted ca not exist
    17. Verify no files at the expected locations
    """
    TestToolkit.tested_api = test_api

    security = System().security

    ca1 = TestCert.cert_valid_1.copy('ca1')
    ca2 = TestCert.cert_valid_2.copy('ca2')

    cas: List[CertInfo] = [ca1, ca2]

    with allure.step('Show cas – expect no data – {}'):
        out = OutputParsingTool.parse_json_str_to_dictionary(security.ca_certificate.show()).get_returned_value()
        assert not out, f'show ca expected to be empty but it is not\n{out}'
    with allure.step('import cas'):
        with allure.independent_step('Import ca1 using data'):
            with allure.step('get cert data as string'):
                data = ca1.get_ca_content_str()
            with allure.step('import with data'):
                security.ca_certificate.cert_id[ca1.name].action_import(data=data).verify_result()
        with allure.independent_step('Import ca2 using URI'):
            uri = generate_scp_uri_using_player(scp_player, ca2.cacert)
            security.ca_certificate.cert_id[ca2.name].action_import(uri=uri).verify_result()
    with allure.step('Show cas – expect all imported cas in output'):
        out = OutputParsingTool.parse_json_str_to_dictionary(security.ca_certificate.show()).get_returned_value()
        assert all(ca.name in out for ca in cas), f'not all expected cas names in show output\nexpected: {[ca.name for ca in cas]}\nout:\n{out}'
    with allure.step('Verify files in expected locations'):
        for ca in cas:
            with allure.independent_step(f'verify "{ca.name}" in expected cert locations'):
                verify_ca_in_expected_locations(ca.name, ca, engines.dut)
    rand_ca: CertInfo = random.choice(cas)
    with allure.step(f'Show a single cert "{rand_ca.name}" – expect fields {CaShowFields.ALL_FIELDS}'):
        out_single = OutputParsingTool.parse_json_str_to_dictionary(security.ca_certificate.cert_id[rand_ca.name].show()).get_returned_value()
        assert all(field in out_single for field in CaShowFields.ALL_FIELDS), f'not all expected fields in single ca show output\nexpected: {CaShowFields.ALL_FIELDS}\nout:\n{out}'
    with allure.step('verify show values'):
        for field in CaShowFields.ALL_FIELDS:
            if field == CaShowFields.COUNT:
                with allure.independent_step('Verify count is 1'):
                    assert str(out_single[field]) == '1', f'field {field} not as expected\nexpected: 1\nactual: {out_single[field]}'
            elif field == CaShowFields.INSTALLED:
                with allure.independent_step('Verify installed empty {}'):
                    assert out_single[field] == {}, f'field {field} not as expected\nexpected: {"{}"}\nactual: {out_single[field]}'
            else:
                with allure.independent_step(f'verify {field} not empty'):
                    assert out_single[field] != '', f'field {field} not as expected\nexpected: not empty\nactual: ""'
    with allure.step('verify inner show commands on ca'):
        expected_patterns_in_content = ['CN = Root CA', 'CA:TRUE']
        with allure.independent_step(f'Show dump of any cert – expect "{expected_patterns_in_content}" in output (sanity)'):
            dump_out_str = security.ca_certificate.cert_id[rand_ca.name].dump.show()
            assert all(pattern in dump_out_str for pattern in expected_patterns_in_content), f'not all of {expected_patterns_in_content} found in show dump output of {rand_ca.name}\nout:\n{dump_out_str}'
    with allure.step(f'Delete a ca: {rand_ca.name}'):
        security.ca_certificate.cert_id[rand_ca.name].action_delete().verify_result()
    with allure.step('Show all cas – expect deleted ca not exist'):
        out = OutputParsingTool.parse_json_str_to_dictionary(security.ca_certificate.show()).get_returned_value()
        assert rand_ca.name not in out, f'deleted ca {rand_ca.name} unexpectedly exists in show output'
    with allure.step(f'Verify deleted ca {rand_ca.name} not exists in expected locations'):
        verify_ca_in_expected_locations(rand_ca.name, rand_ca, engines.dut, False)


@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cacert_mgmt_import_ca_data_bad_param(test_api, engines, scp_player, clear_certs):
    """
    Verify that import cert with bad params rejected

    1. Empty
    2. random short string
    3. real cert that injected letter in the middle
    """
    TestToolkit.tested_api = test_api

    security = System().security

    ca = TestCert.cert_valid_1.copy()
    real_data = ca.get_ca_content_str()

    ca_name, ca_obj, data = 'ca_name', 'ca_obj', 'data'
    cases = [
        {ca_name: 'ca-empty-string', ca_obj: ca, data: ''},
        {ca_name: 'ca-rand-string', ca_obj: ca, data: randomize_hex_str(10)},
        {ca_name: 'ca-messed-data', ca_obj: ca, data: real_data[:50 - 5] + 'ALON' + real_data[50 - 1:]},
    ]

    with allure.step('import cas using bad data params - expect fail and not in output'):
        with allure.independent_step('try import ca with using data param with bad values'):
            for case in cases:
                # for ca_name, data in cas_datas.items():
                with allure.independent_step(case[ca_name]):
                    security.ca_certificate.cert_id[case[ca_name]].action_import(data=case[data]).verify_result(False)
        with allure.independent_step('verify no ca in show'):
            out = OutputParsingTool.parse_json_str_to_dictionary(security.ca_certificate.show()).get_returned_value()
            assert out == {}, f'output not as expected\nexpected: {"{}"}\nactual: {out}'
        with allure.independent_step('Verify cas not exist in expected locations'):
            for case in cases:
                with allure.independent_step(case[ca_name]):
                    verify_ca_in_expected_locations(case[ca_name], case[ca_obj], engines.dut, False)


@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cacert_mgmt_import_ca_uri_bad_param(test_api, engines, scp_player, clear_certs):
    """
    Verify that import ca with bad params rejected

    1. empty values
    2. random string as url
    """
    TestToolkit.tested_api = test_api

    security = System().security

    name, description, uri, cacert_info = 'name', 'description', 'uri', 'cacert_info'
    cases = [
        {name: 'ca1', description: 'empty uri', uri: ""},
        {name: 'ca2', description: 'random str uri', uri: 'xyz'}
    ]

    with allure.step('import certs using bad data params - expect fail and not in output'):
        with allure.independent_step('try import cert with using data param with bad values'):
            for case in cases:
                with allure.independent_step(f'{case[name]} - {case[description]}'):
                    security.ca_certificate.cert_id[case[name]].action_import(uri=case[uri]).verify_result(False)
        with allure.independent_step('verify no ca in show'):
            out = OutputParsingTool.parse_json_str_to_dictionary(security.ca_certificate.show()).get_returned_value()
            assert out == {}, f'output not as expected\nexpected: {"{}"}\nactual: {out}'
        with allure.independent_step('Verify cas not exist in expected locations'):
            for case in cases:
                with allure.independent_step(case[name]):
                    verify_ca_in_expected_locations(case[name], None, engines.dut, False)


@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cacert_mgmt_delete_ca_bad_param(test_api, engines, scp_player, clear_certs):
    """
    Verify that delete ca with bad params rejected and doesn't affect other imported cas
    """
    TestToolkit.tested_api = test_api

    security = System().security

    cas: List[CertInfo] = [TestCert.cert_valid_1.copy(f'cert{i + 1}') for i in range(5)]

    with allure.step('import some cas'):
        import_certificates(scp_player, engines.dut, cas, True)
    with allure.step('delete cert that does not exist'):
        security.ca_certificate.cert_id['xyz'].action_delete().verify_result(False)
    with allure.step('verify all imported certs still exist'):
        out = OutputParsingTool.parse_json_str_to_dictionary(security.ca_certificate.show()).get_returned_value()
        for ca in cas:
            with allure.independent_step(ca.name):
                with allure.independent_step('verify exists in show'):
                    assert ca.cacert_name in out, f'{ca.cacert_name} does not exist in show ca-certificate output, but expected to exist\n{out}'
                with allure.independent_step('verify exists in expected locations'):
                    verify_ca_in_expected_locations(ca.cacert_name, ca, engines.dut)


@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cacert_mgmt_import_ca_unique_id(test_api, engines, scp_player, clear_certs):
    """
    Verify that must use unique ca id

    1. import ca1
    2. import another ca with same id – expect rejected
    """
    TestToolkit.tested_api = test_api

    security = System().security
    cacert = TestCert.cert_valid_1
    uri = generate_scp_uri_using_player(scp_player, cacert.cacert)

    title, ca_name, expect = 'title', 'ca_name', 'expect'
    cases: List[dict] = [
        {title: 'import ca1', ca_name: 'ca1', expect: True},
        {title: 'import ca2', ca_name: 'ca2', expect: True},
        {title: 'repeat ca1', ca_name: 'ca1', expect: False},
        {title: 'import ca3', ca_name: 'ca3', expect: True},
        {title: 'repeat ca2', ca_name: 'ca2', expect: False},
        {title: 'import ca4', ca_name: 'ca4', expect: True},
    ]

    with allure.step('test importing in several cases'):
        for case in cases:
            with allure.independent_step(f'{case[title]} - expect: {case[expect]}'):
                security.ca_certificate.cert_id[case[ca_name]].action_import(uri=uri).verify_result(case[expect])
    with allure.step('show cas'):
        out = OutputParsingTool.parse_json_str_to_dictionary(security.ca_certificate.show()).get_returned_value()
    with allure.step('verify existence of all cas'):
        cas = ['ca1', 'ca2', 'ca3', 'ca4']
        for ca in cas:
            with allure.independent_step(f'{case[ca_name]} - expect: {case[expect]}'):
                with allure.independent_step('verify in show'):
                    assert ca in out, f'ca {ca} does not appear in ca-certificate show output but expected to exist\n{out}'
                with allure.independent_step('verify files'):
                    verify_ca_in_expected_locations(ca, cacert, engines.dut)


""" functional tests """


@pytest.mark.system
@pytest.mark.certificate
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
@pytest.mark.parametrize('test_flow', TestFlowType.ALL_TYPES)
def test_cert_mgmt_use_ca_for_rest_api_mtls(test_api, test_flow, engines, scp_player, clear_certs):
    """
    Verify that valid imported cert can be used for REST server TLS

    1. import cert
    2. bind cert to rest server (system api certificate)
    3. send unsecured client request – success
    4. send client request using non/proper CA - fail/success
    """
    TestToolkit.tested_api = test_api
    is_good_flow = test_flow == TestFlowType.GOOD_FLOW

    system = System()
    security = system.security

    server_cert = TestCert.cert_valid_1.copy('cert1')
    server_ca = TestCert.cert_valid_2.copy('cert2')
    cert_bundle_uri = generate_scp_uri_using_player(scp_player, server_cert.p12_bundle)
    ca_uri = generate_scp_uri_using_player(scp_player, server_ca.cacert)

    with allure.step('import cert and ca'):
        security.certificate.cert_id[server_cert.name].action_import(uri_bundle=cert_bundle_uri, passphrase=server_cert.p12_password).verify_result()
        security.ca_certificate.cert_id[server_ca.cacert_name].action_import(uri=ca_uri).verify_result()
    with allure.step('bind cert and ca to rest server (system api certificate & mtls)'):
        system.api.set(CERTIFICATE, server_cert.name).verify_result()
        system.api.mtls.set(CA_CERTIFICATE, server_ca.cacert_name, apply=True, client_certs_after_apply=CertInfo('', '', server_ca.private, server_ca.public, '', '', server_ca.dn, None, '')).verify_result()
    if not is_good_flow:
        with allure.step('send unsecured client request – expect fail'):
            send_curl_with_and_verify(server_cert.dn, engines.dut.username, engines.dut.password, EncryptionMode.DISABLED, should_succeed=False)
    with allure.step(f'send client request using {"" if is_good_flow else "non-"}proper client cert – expect {"success" if is_good_flow else "fail"}'):
        client_ca = server_cert  # client cert matches server CA
        client_cert = server_ca if is_good_flow else TestCert.cert_valid_3
        send_curl_with_and_verify(server_cert.dn, engines.dut.username, engines.dut.password, EncryptionMode.MTLS, client_ca, client_cert, is_good_flow)

import random

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.nmx_cert.constants import CA_CERTIFICATE
from ngts.tests_nvos.general.security.test_api_server_security.constants import ApiConsts
from ngts.tests_nvos.general.security.test_api_server_security.helpers import verify_installed_cacert


@pytest.mark.mtls
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_api_mtls_cli(test_api, test_certs):
    """
    Verify that all CLI work and check values change properly in show

    1. Run show commands
    2. Verify outputs contain the required fields
    3. Set ca-certificate
    4. Verify in show commands
    5. Unset
    6. Verify in show commands
    """
    TestToolkit.tested_api = test_api
    system = System()
    imported_cas = [cert.cacert_name for cert in test_certs]
    ca = random.choice(imported_cas)

    with allure.step('run show commands and verify required fields'):
        with allure.independent_step('api show'):
            api_conf = OutputParsingTool.parse_json_str_to_dictionary(system.api.show()).get_returned_value()
            assert all(field in api_conf for field in
                       ApiConsts.fields), f'some of expected fields are missing from show api output\nexpected: {ApiConsts.fields}\nout keys: {api_conf.keys()}'
        with allure.independent_step('mtls show'):
            mtls_conf = OutputParsingTool.parse_json_str_to_dictionary(system.api.mtls.show()).get_returned_value()
            with allure.independent_step('verify all expected fields exist'):
                assert all(field in mtls_conf for field in
                           ApiConsts.Mtls.fields), f'some of expected fields are missing from show mtls output\nexpected: {ApiConsts.Mtls.fields}\nout keys: {mtls_conf.keys()}'
            with allure.independent_step('verify no config initially'):
                assert not mtls_conf[
                    CA_CERTIFICATE], f'value of "{CA_CERTIFICATE}" in mtls show not as expected\nexpected: ""\nactual: {mtls_conf[CA_CERTIFICATE]}'
        with allure.independent_step('ca-certificates show'):
            cacerts_conf = OutputParsingTool.parse_json_str_to_dictionary(
                system.security.ca_certificate.show()).get_returned_value()
            with allure.independent_step('verify all expected cas exist'):
                assert all(caname in cacerts_conf for caname in
                           imported_cas), f'some of expected ca names are missing from show ca-certificate output\nexpected: {imported_cas}\nout keys: {cacerts_conf.keys()}'
            with allure.independent_step('verify no ca installed for api initially'):
                verify_installed_cacert(imported_cas, None)

    with allure.step(f'Set ca-certificate to {ca}'):
        system.api.mtls.set(CA_CERTIFICATE, ca, apply=True).verify_result()
    with allure.step('Verify in show commands'):
        with allure.independent_step('mtls show'):
            mtls_conf = OutputParsingTool.parse_json_str_to_dictionary(system.api.mtls.show()).get_returned_value()
            assert mtls_conf[
                CA_CERTIFICATE] == ca, f'value of "{CA_CERTIFICATE}" in mtls show not as expected\nexpected: {ca}\nactual: {mtls_conf[CA_CERTIFICATE]}'
        with allure.independent_step(f'ca-certificate show - verify ca "{ca}" installed for api'):
            verify_installed_cacert(imported_cas, ca)

    with allure.step('check unset commands clear mtls config'):
        with allure.independent_step('check unset api'):
            with allure.step('run unset api'):
                system.api.unset(apply=True).verify_result()
            with allure.independent_step('verify mtls config cleared'):
                mtls_conf = OutputParsingTool.parse_json_str_to_dictionary(system.api.mtls.show()).get_returned_value()
                assert not mtls_conf[
                    CA_CERTIFICATE], f'value of "{CA_CERTIFICATE}" in mtls show not as expected\nexpected: ""\nactual: {mtls_conf[CA_CERTIFICATE]}'
            with allure.independent_step('verify no ca installed for api initially'):
                verify_installed_cacert(imported_cas, None)
        with allure.independent_step('check unset mtls'):
            with allure.step(f'Set ca-certificate to {ca}'):
                system.api.mtls.set(CA_CERTIFICATE, ca, apply=True).verify_result()
            with allure.step('run unset mtls'):
                system.api.mtls.unset(apply=True).verify_result()
            with allure.step('check mtls config cleared'):
                mtls_conf = OutputParsingTool.parse_json_str_to_dictionary(system.api.mtls.show()).get_returned_value()
                assert not mtls_conf[
                    CA_CERTIFICATE], f'value of "{CA_CERTIFICATE}" in mtls show not as expected\nexpected: ""\nactual: {mtls_conf[CA_CERTIFICATE]}'
            with allure.independent_step('verify no ca installed for api initially'):
                verify_installed_cacert(imported_cas, None)
        with allure.independent_step('check unset cacert field'):
            with allure.step(f'Set ca-certificate to {ca}'):
                system.api.mtls.set(CA_CERTIFICATE, ca, apply=True).verify_result()
            with allure.step('run unset mtls cacert'):
                system.api.mtls.unset(CA_CERTIFICATE, apply=True).verify_result()
            with allure.step('check mtls cacert config cleared'):
                mtls_conf = OutputParsingTool.parse_json_str_to_dictionary(system.api.mtls.show()).get_returned_value()
                assert not mtls_conf[
                    CA_CERTIFICATE], f'value of "{CA_CERTIFICATE}" in mtls show not as expected\nexpected: ""\nactual: {mtls_conf[CA_CERTIFICATE]}'
            with allure.independent_step('verify no ca installed for api initially'):
                verify_installed_cacert(imported_cas, None)

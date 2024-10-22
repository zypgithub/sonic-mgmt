import logging
from typing import Union, Dict

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.helpers import get_path_of_imported_cert_private_file, \
    get_path_of_imported_cert_public_file, get_path_of_imported_cacert_public_file
from ngts.tests_nvos.general.security.nmx_cert.constants import FieldsInShowOf, CERTIFICATE, CA_CERTIFICATE, ENCRYPTION, \
    DEFAULT_NMX_C_MGMT_PORT, USR_CFG_JSON, USR_CFG_JSON_PATH, NMX_CERTS_DIR, FILE_NOT_EXIST_ERR, NMX_CACERTS_DIR, \
    FILE_SHOULD_NOT_EXIST, STATE
from ngts.tests_nvos.general.security.nmx_cert.grpc.client.client import run_grpc_client
from ngts.tests_nvos.general.security.nmx_cert.grpc.config import GrpcConfig, GrpcServerConfig, GrpcClientConfig


def verify_component_show(component: BaseComponent, required_fields,
                          value_expectations: Dict[str, Union[str, None, int]]):
    with allure.step(f'verify show: {component._resource_path}'):
        with allure.step('run show command'):
            out = OutputParsingTool.parse_json_str_to_dictionary(component.show()).get_returned_value()
        with allure.independent_step('verify required fields exist'):
            missing_fields = [field for field in required_fields if field not in out]
            assert not missing_fields, f'some required fields are missing in show cluster manager output:\n{missing_fields}'
        for field, expected in value_expectations.items():
            with allure.independent_step(f'verify expected {field} - {expected}'):
                assert expected is None or out[
                    field] == expected, f'mismatch with field "{field}": expected {field}: {expected}, actual: {out[field]}'


def verify_manager_show(expect_state=None, expect_cert=None, expect_cacert=None, expect_encryption=None):
    verify_component_show(Cluster().manager, FieldsInShowOf.MANAGER,
                          {STATE: expect_state, CERTIFICATE: expect_cert, CA_CERTIFICATE: expect_cacert,
                              ENCRYPTION: expect_encryption})


def verify_cert_show(expect_cert_id=None):
    verify_component_show(Cluster().manager.certificate, FieldsInShowOf.CERTIFICATE, {CERTIFICATE: expect_cert_id})


def verify_cacert_show(expect_cert_id=None):
    verify_component_show(Cluster().manager.ca_certificate, FieldsInShowOf.CA_CERTIFICATE,
                          {CA_CERTIFICATE: expect_cert_id})


def verify_encryption_show(expect_mode=None):
    verify_component_show(Cluster().manager.encryption, FieldsInShowOf.ENCRYPTION, {ENCRYPTION: expect_mode})


def run_manager_client_hello_request(client_tls_mode: str, server_cert: CertInfo, server_ca: CertInfo,
                                     client_cert: CertInfo, client_ca: CertInfo,
                                     num_requests: int = 1, delay_between_requests: int = 1) -> ResultObj:
    result = ResultObj(result=True, info='client successfully communicated with nmx-c', returned_value=True)

    with allure.step('create config for grpc client'):
        config = GrpcConfig(
            server=GrpcServerConfig(address=server_cert.dn or server_cert.ip, port=DEFAULT_NMX_C_MGMT_PORT,
                                    tls_mode=client_tls_mode, cert=server_cert, cacert=server_ca),
            client=GrpcClientConfig(address=client_cert.dn or client_cert.ip, tls_mode=client_tls_mode, cert=client_cert,
                                    cacert=client_ca, num_requests=num_requests,
                                    delay_between_requests=delay_between_requests))
    try:
        with allure.step('run client hello request'):
            responses = run_grpc_client(config, TestToolkit.engines.dut.ip, logging, False)
        result.returned_value = responses
    except Exception as e:
        result = ResultObj(result=False, info=f'client failed:\n{e}', returned_value=None)

    return result


def get_user_config_json_file_content(dut_engine: LinuxSshEngine):
    output: str = dut_engine.run_cmd(f'sudo cat {USR_CFG_JSON_PATH}')
    if not output.endswith('}'):
        output += '\n}'
    return output


def verify_static_checks(expect_fields: Dict[str, Union[str, None]] = None, cert_id=None, cacert_id=None):
    """
    static checks:
    1. user_config.json file: check for existence of fields and their values
    2. cert file
    3. cacert file

    * if json field exists with None - field should not exist in json
    * if cert/cacert = None - don't check the file
    * if cert/cacert = -1 (FILE_SHOULD_NOT_EXIST) - file should not exist
    """
    dut: LinuxSshEngine = TestToolkit.engines.dut
    with allure.step('verify static checks'):
        if expect_fields:
            with allure.independent_step(f'verify fields in {USR_CFG_JSON}'):
                with allure.step('get content of the file'):
                    content = OutputParsingTool.parse_json_str_to_dictionary(
                        get_user_config_json_file_content(dut)).get_returned_value()
                for field, expect in expect_fields.items():
                    with allure.independent_step(
                            f'verify field "{field}" ' + 'does not exist' if expect is None else f'verify field "{field}" = "{expect}"'):
                        if expect is None:
                            assert field not in content, f'field "{field}" exists in {USR_CFG_JSON}, while it should not.\ncontent:\n{content}'
                        else:
                            assert content[
                                field] == expect, f'bad value of field "{field}" in {USR_CFG_JSON}\nexpected: "{expect}"\nactual: "{content[field]}"\ncontent:\n{content}'

        if cert_id:
            cert_should_not_exist = cert_id == FILE_SHOULD_NOT_EXIST
            with allure.independent_step(
                    f'verify certificate files {"do not " if cert_should_not_exist else ""}exist for cert-id: {cert_id}'):
                with allure.independent_step('verify private'):
                    nmx_private_path = get_path_of_nmx_cert_private_file(cert_id, dut)
                    if cert_should_not_exist:
                        assert not nmx_private_path, f'nmx private key file exists while expected not to.\nat: {nmx_private_path}'
                    else:
                        assert nmx_private_path, f'nmx private key file does not exists while expected to exist.\ncert-id: {cert_id}'
                        nmx_private_content = get_cert_key_content(nmx_private_path, dut)
                        imported_private_content = get_cert_key_content(
                            get_path_of_imported_cert_private_file(cert_id, dut), dut)
                        assert nmx_private_content == imported_private_content, f'nmx cert private key file do not match imported. cert-id: {cert_id}'
                with allure.independent_step('verify public'):
                    nmx_public_path = get_path_of_nmx_cert_public_file(cert_id, dut)
                    if cert_should_not_exist:
                        assert not nmx_public_path, f'nmx public crt file exists while expected not to.\nat: {nmx_public_path}'
                    else:
                        assert nmx_public_path, f'nmx public crt file does not exists while expected to exist.\ncert-id: {cert_id}'
                        nmx_public_content = get_cert_key_content(nmx_public_path, dut)
                        imported_public_content = get_cert_key_content(
                            get_path_of_imported_cert_public_file(cert_id, dut), dut)
                        assert nmx_public_content == imported_public_content, f'nmx cert public crt file do not match imported. cert-id: {cert_id}'

        if cacert_id:
            cacert_should_not_exist = cacert_id == FILE_SHOULD_NOT_EXIST
            with allure.independent_step(
                    f'verify ca-cert files {"do not " if cacert_should_not_exist else ""}exist for cacert-id: {cacert_id}'):
                nmx_cacert_path = get_path_of_nmx_cacert_public_file(cacert_id, dut)
                if cacert_should_not_exist:
                    assert not nmx_cacert_path, f'nmx cacert file exists while expected not to.\nat: {nmx_cacert_path}'
                else:
                    assert nmx_cacert_path, f'nmx cacert file does not exists while expected to exist.\ncert-id: {cacert_id}'
                    nmx_cacert_content = get_cert_key_content(nmx_cacert_path, dut)
                    imported_cacert_content = get_cert_key_content(
                        get_path_of_imported_cacert_public_file(cacert_id, dut), dut)
                    assert nmx_cacert_content == imported_cacert_content, f'nmx cert cacert file do not match imported. cert-id: {cacert_id}'


def get_cert_key_content(cert_file, dut_engine: LinuxSshEngine):
    prefix = '-----BEGIN'
    content = dut_engine.run_cmd(f'sudo cat {cert_file}')
    return (prefix + content.split(prefix, 1)[-1]).strip()


def get_path_of_nmx_cert_private_file(cert_id, dut_engine: LinuxSshEngine):
    path = f'{NMX_CERTS_DIR}/{cert_id}.key'
    # path = f'{NMX_CERTS_DIR}/nmx.key'
    out = dut_engine.run_cmd(f'sudo ls {path}')
    # assert FILE_NOT_EXIST_ERR not in out, f'there is no private key file for the given cert-id "{cert_id}"'
    return path if FILE_NOT_EXIST_ERR not in out else None


def get_path_of_nmx_cert_public_file(cert_id, dut_engine: LinuxSshEngine):
    path = f'{NMX_CERTS_DIR}/{cert_id}.crt'
    # path = f'{NMX_CERTS_DIR}/nmx.pem'
    out = dut_engine.run_cmd(f'sudo ls {path}')
    # assert FILE_NOT_EXIST_ERR not in out, f'there is no public crt file for the given cert-id "{cert_id}"'
    return path if FILE_NOT_EXIST_ERR not in out else None


def get_path_of_nmx_cacert_public_file(cacert_id, dut_engine: LinuxSshEngine):
    path = f'{NMX_CACERTS_DIR}/{cacert_id}.crt'
    # path = f'{NMX_CACERTS_DIR}/ca_nmx.crt'
    out = dut_engine.run_cmd(f'sudo ls {path}')
    # assert FILE_NOT_EXIST_ERR not in out, f'there is no public pem file for the given cacert-id "{cacert_id}"'
    return path if FILE_NOT_EXIST_ERR not in out else None

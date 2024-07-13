import logging
from typing import Union, Dict

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.nmx_cert.constants import FieldsInShowOf, STATE, CERTIFICATE, CA_CERTIFICATE, \
    ENCRYPTION, CERT_ID, MODE, NMX_C_MGMT_PORT
from ngts.tests_nvos.general.security.nmx_cert.grpc.client.client import run_grpc_client_app
from ngts.tests_nvos.general.security.nmx_cert.grpc.config import GrpcConfig, GrpcServerConfig, GrpcClientConfig


def verify_component_show(component: BaseComponent, required_fields, value_expectations):
    with allure.step(f'verify show: {component._resource_path}'):
        with allure.step('run show command'):
            out = OutputParsingTool.parse_json_str_to_dictionary(component.show()).get_returned_value()
        with allure.step('verify required fields exist'):
            missing_fields = [field for field in required_fields if field not in out]
            assert not missing_fields, f'some required fields are missing in show cluster manager output:\n{missing_fields}'
        problems = []
        for field, expected in value_expectations.items():
            with allure.step(f'verify expected {field} - {expected}'):
                if expected is not None and out[field] != expected:
                    problems.append(f'expected {field}: {expected} ; actual: {out[field]}')
        assert not problems, '\n'.join(problems)


def verify_manager_show(expect_state=None, expect_cert=None, expect_cacert=None, expect_encryption=None):
    verify_component_show(Cluster().manager, FieldsInShowOf.MANAGER, {
        STATE: expect_state, CERTIFICATE: expect_cert, CA_CERTIFICATE: expect_cacert, ENCRYPTION: expect_encryption
    })


def verify_cert_show(expect_cert_id=None):
    verify_component_show(Cluster().manager.certificate, FieldsInShowOf.CERTIFICATE, {CERT_ID: expect_cert_id})


def verify_cacert_show(expect_cert_id=None):
    verify_component_show(Cluster().manager.ca_certificate, FieldsInShowOf.CA_CERTIFICATE, {CERT_ID: expect_cert_id})


def verify_encryption_show(expect_mode=None):
    verify_component_show(Cluster().manager.encryption, FieldsInShowOf.ENCRYPTION, {MODE: expect_mode})


def send_grpc_request_to_nmx_c(tls_mode: str, server_cert: CertInfo, client_cert: CertInfo, server_cacert: CertInfo,
                               client_cacert: CertInfo, num_requests: int = 1,
                               delay_between_requests: int = 1) -> ResultObj:
    result = ResultObj(
        result=True,
        info='client successfully communicated with nmx-c',
        returned_value=True
    )

    with allure.step('create config for grpc client'):
        client_config = GrpcConfig(
            server=GrpcServerConfig(
                address=server_cert.dn or server_cert.ip,
                port=NMX_C_MGMT_PORT,
                tls_mode=tls_mode,
                cert=server_cert,
                cacert=server_cacert
            ),
            client=GrpcClientConfig(
                address=client_cert.dn or client_cert.ip,
                tls_mode=tls_mode,
                cert=client_cert,
                cacert=client_cacert,
                num_requests=num_requests,
                delay_between_requests=delay_between_requests
            )
        )

    with allure.step('run grpc client'):
        try:
            responses = run_grpc_client_app(client_config, logging)
            result.returned_value = responses
        except Exception as e:
            result = ResultObj(
                result=False,
                info=f'client failed:\n{e}',
                returned_value=None
            )

    return result


def verify_client_connection(test_is_good_flow: bool, expectations: Union[bool, Dict[str, bool]], nmx_c_cert: CertInfo,
                             client_cert: CertInfo, nmx_c_cacert: CertInfo, client_cacert: CertInfo):
    def _run_client_and_verify():
        with allure.step('Run client request to nmx-c'):  # TODO: check encryption works?
            res: ResultObj = send_grpc_request_to_nmx_c(encryption_mode, nmx_c_cert, client_cert, nmx_c_cacert,
                                                        client_cacert)
        with allure.step(f'Expect {"success" if test_is_good_flow else "fail"}'):
            res.verify_result(test_is_good_flow)

    if isinstance(expectations, bool):
        if expectations == test_is_good_flow:
            _run_client_and_verify()
        return

    for encryption_mode, expect_success in expectations.items():
        with allure.step(f'test with encryption mode: {encryption_mode} - expect success: {test_is_good_flow}'):
            if expect_success == test_is_good_flow:
                with allure.step(f'Update manager encryption mode: {encryption_mode}'):
                    Cluster().manager.encryption.action_update(encryption_mode).verify_result()
                _run_client_and_verify()

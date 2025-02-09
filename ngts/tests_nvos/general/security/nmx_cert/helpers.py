import logging
import time
from typing import Union, Dict

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import ClusterApps, OutputFormat
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Manager import Manager
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.nmx_cert.constants import FieldsInShowOf, CERTIFICATE, CA_CERTIFICATE, ENCRYPTION, \
    FILE_NOT_EXIST_ERR, STATE, APP_CONSTS, ClusterAppConsts, NMX_C_CONSTS, NMX_T_CONSTS, ITEM_NOT_EXIST_ERR, ENABLED, \
    CLUSTER_STATE_TOGGLE_WAIT_TIME, DISABLED, CLUSTER_APP_MNGR_STATE_UPDATE_WAIT_TIME, USR_CFG_JSON_PATH
from ngts.tests_nvos.general.security.nmx_cert.grpc.config import GrpcConfig, GrpcServerConfig, GrpcClientConfig
from ngts.tests_nvos.general.security.nmx_cert.grpc.nmx_c.client.NmxControllerClientApp import run_nmx_c_grpc_client
from ngts.tests_nvos.general.security.nmx_cert.grpc.nmx_t.client.NmxTelemetryClientApp import run_nmx_t_grpc_client


def set_cluster_state(state, force_wait: bool = False):
    with allure.step(f'set cluster state: {state}'):
        res: ResultObj = Cluster().set(STATE, state, apply=True)
        if force_wait or res.apply_occurred():
            with allure.step(f'wait {CLUSTER_STATE_TOGGLE_WAIT_TIME} seconds after cluster state toggled'):
                time.sleep(CLUSTER_STATE_TOGGLE_WAIT_TIME)
        res.verify_result()


def enable_cluster(force_wait: bool = False):
    set_cluster_state(ENABLED, force_wait)


def disable_cluster(force_wait: bool = False):
    set_cluster_state(DISABLED, force_wait)


def wait_after_cluster_app_manager_state_changed():
    with allure.step(
            f'wait {CLUSTER_APP_MNGR_STATE_UPDATE_WAIT_TIME} seconds after cluster app manager state updated'):
        time.sleep(CLUSTER_APP_MNGR_STATE_UPDATE_WAIT_TIME)


def update_cluster_app_manager_state(manager: Manager, state):
    with allure.step(f'update cluster app manager state: {state}'):
        res: ResultObj = manager.action_update(state)
        wait_after_cluster_app_manager_state_changed()
        res.verify_result()


def enable_cluster_app_manager_state(manager: Manager):
    update_cluster_app_manager_state(manager, ENABLED)


def disable_cluster_app_manager_state(manager: Manager):
    update_cluster_app_manager_state(manager, DISABLED)


def restore_cluster_app_manager_state(manager: Manager):
    with allure.step('restore cluster app manager state'):
        res: ResultObj = manager.action_restore()
        wait_after_cluster_app_manager_state_changed()
        res.verify_result()


def verify_component_show(component: BaseComponent, required_fields,
                          value_expectations: Dict[str, Union[str, None, int]], expect_item_not_exist: bool = False):
    if expect_item_not_exist:
        with allure.step(f'verify show: {component._resource_path} - expect item not exists'):
            out = component.show(should_succeed=False)
            assert ITEM_NOT_EXIST_ERR in out, f'wrong output. expected: "{ITEM_NOT_EXIST_ERR}". actual:\n{out}'
    else:
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


def verify_manager_show(app_name: str, expect_state=None, expect_cert=None, expect_cacert=None, expect_encryption=None,
                        expect_item_not_exist: bool = False):
    verify_component_show(Cluster().apps.app_name[app_name].manager, FieldsInShowOf.MANAGER,
                          {STATE: expect_state, CERTIFICATE: expect_cert, CA_CERTIFICATE: expect_cacert,
                           ENCRYPTION: expect_encryption}, expect_item_not_exist)


def verify_cert_show(app_name: str, expect_cert_id=None, expect_item_not_exist: bool = False):
    verify_component_show(Cluster().apps.app_name[app_name].manager.certificate, FieldsInShowOf.CERTIFICATE,
                          {CERTIFICATE: expect_cert_id}, expect_item_not_exist)


def verify_cacert_show(app_name: str, expect_cert_id=None, expect_item_not_exist: bool = False):
    verify_component_show(Cluster().apps.app_name[app_name].manager.ca_certificate, FieldsInShowOf.CA_CERTIFICATE,
                          {CA_CERTIFICATE: expect_cert_id}, expect_item_not_exist)


def verify_encryption_show(app_name: str, expect_mode=None, expect_item_not_exist: bool = False):
    verify_component_show(Cluster().apps.app_name[app_name].manager.encryption, FieldsInShowOf.ENCRYPTION,
                          {ENCRYPTION: expect_mode}, expect_item_not_exist)


def run_nmx_c_client_hello_request(client_tls_mode: str, server_cert: CertInfo, server_ca: CertInfo,
                                   client_cert: CertInfo, client_ca: CertInfo,
                                   num_requests: int = 1, delay_between_requests: int = 1) -> ResultObj:
    result = ResultObj(result=True, info='client successfully communicated with nmx-c', returned_value=True)

    with allure.step('create config for grpc client'):
        config = GrpcConfig(
            server=GrpcServerConfig(address=server_cert.dn or server_cert.ip, port=NMX_C_CONSTS.external_manager_port,
                                    tls_mode=client_tls_mode, cert=server_cert, cacert=server_ca),
            client=GrpcClientConfig(address=client_cert.dn or client_cert.ip, tls_mode=client_tls_mode,
                                    cert=client_cert,
                                    cacert=client_ca, num_requests=num_requests,
                                    delay_between_requests=delay_between_requests))
    try:
        with allure.step('run client hello request'):
            responses = run_nmx_c_grpc_client(config, TestToolkit.engines.dut.ip, logging, False)
        result.returned_value = responses
    except Exception as e:
        result = ResultObj(result=False, info=f'client failed:\n{e}', returned_value=None)

    return result


def run_nmx_t_client_hello_request(client_tls_mode: str, server_cert: CertInfo, server_ca: CertInfo,
                                   client_cert: CertInfo, client_ca: CertInfo,
                                   num_requests: int = 1, delay_between_requests: int = 1) -> ResultObj:
    result = ResultObj(result=True, info='client successfully communicated with nmx-t', returned_value=True)

    with allure.step('create config for grpc client'):
        config = GrpcConfig(
            server=GrpcServerConfig(address=server_cert.dn or server_cert.ip, port=NMX_T_CONSTS.external_manager_port,
                                    tls_mode=client_tls_mode, cert=server_cert, cacert=server_ca),
            client=GrpcClientConfig(address=client_cert.dn or client_cert.ip, tls_mode=client_tls_mode,
                                    cert=client_cert,
                                    cacert=client_ca, num_requests=num_requests,
                                    delay_between_requests=delay_between_requests))
    try:
        with allure.step('run client hello request'):
            responses = run_nmx_c_grpc_client(config, TestToolkit.engines.dut.ip, logging, False)
        result.returned_value = responses
    except Exception as e:
        result = ResultObj(result=False, info=f'client failed:\n{e}', returned_value=None)

    return result


def run_manager_hello_request(app_name: str, client_tls_mode: str, server_cert: CertInfo, server_ca: CertInfo,
                              client_cert: CertInfo, client_ca: CertInfo,
                              num_requests: int = 1, delay_between_requests: int = 1, skip_etc_mapping: bool = False) -> ResultObj:
    app_consts: ClusterAppConsts = APP_CONSTS[app_name]

    result = ResultObj(result=True, info=f'client successfully communicated with {app_name}', returned_value=True)

    with allure.step('create config for grpc client'):
        config = GrpcConfig(
            server=GrpcServerConfig(address=server_cert.dn or server_cert.ip, port=app_consts.external_manager_port,
                                    tls_mode=client_tls_mode, cert=server_cert, cacert=server_ca),
            client=GrpcClientConfig(address=client_cert.dn or client_cert.ip, tls_mode=client_tls_mode,
                                    cert=client_cert,
                                    cacert=client_ca, num_requests=num_requests,
                                    delay_between_requests=delay_between_requests))
    try:
        with allure.step('run client hello request'):
            if app_name == ClusterApps.NMX_CONTROLLER:
                responses = run_nmx_c_grpc_client(config, TestToolkit.engines.dut.ip, logging, skip_etc_mapping)
            else:
                responses = run_nmx_t_grpc_client(config, TestToolkit.engines.dut.ip, logging, skip_etc_mapping)
        result.returned_value = responses
    except Exception as e:
        result = ResultObj(result=False, info=f'client failed:\n{e}', returned_value=None)

    return result


def get_user_config_json_file_content(app_name, dut_engine: LinuxSshEngine):
    consts: ClusterAppConsts = APP_CONSTS[app_name]
    output: str = dut_engine.run_cmd(f'sudo cat {consts.user_config_json_path}')
    if not output.endswith('}'):
        output += '\n}'
    return output


def verify_user_config_json(app_name: str, dut_engine: LinuxSshEngine, expected_values: dict = {}):
    consts: ClusterAppConsts = APP_CONSTS[app_name]
    with allure.step('verify user_config.json'):
        with allure.step('get user_config.json content'):
            user_config_json_content = OutputParsingTool.parse_json_str_to_dictionary(
                get_user_config_json_file_content(app_name, dut_engine)).get_returned_value()
        with allure.step('verify actual values against expected'):
            for field in consts.user_config_json_fields.all_fields:
                with allure.independent_step(f'check user_config.json key: {field}'):
                    if field not in expected_values:
                        if field in consts.fields_that_must_exist_in_user_config_json:
                            assert field in user_config_json_content, f'{app_name} key "{field}" does not exist in user_config.json but expected to exist'
                            assert user_config_json_content[field] == consts.fields_that_must_exist_in_user_config_json[
                                field], f'{app_name} key "{field}" has unexpected value\nexpected: {consts.fields_that_must_exist_in_user_config_json[field]}\nactual: {user_config_json_content[field]}'
                        else:
                            assert field not in user_config_json_content, f'{app_name} key "{field}" exists in user_config.json but should not'
                    else:
                        assert user_config_json_content[field] == expected_values[
                            field], f'{app_name} key "{field}" has unexpected value\nexpected: {expected_values[field]}\nactual: {user_config_json_content[field]}'


def verify_cert_files(app_name: str, dut_engine: LinuxSshEngine, expected_cert_id: str = ''):
    consts: ClusterAppConsts = APP_CONSTS[app_name]
    with allure.step('verify cert files'):
        if expected_cert_id:
            for path in [consts.cert_private_key_path.format(expected_cert_id),
                         consts.cert_public_key_path.format(expected_cert_id)]:
                with allure.independent_step(f'check cert exists at: {path}'):
                    out = dut_engine.run_cmd(f'sudo ls {path}')
                    assert FILE_NOT_EXIST_ERR not in out, f'{app_name} cert was not found in expected path: {path}\nout: {out}'
        else:
            for path in [consts.cert_private_key_path.rsplit('/', 1)[0], consts.cert_public_key_path.rsplit('/', 1)[0]]:
                with allure.independent_step(f'check no cert in path: {path}'):
                    out = dut_engine.run_cmd(f'sudo ls {path}')
                    assert not out or FILE_NOT_EXIST_ERR in out, f'{app_name} cert files unexpected in path: {path}\nout: {out}'


def verify_cacert_file(app_name: str, dut_engine: LinuxSshEngine, expected_cacert_id: str = ''):
    consts: ClusterAppConsts = APP_CONSTS[app_name]
    if expected_cacert_id:
        path = consts.cacert_path.format(expected_cacert_id)
        with allure.step(f'check cacert exists at: {path}'):
            out = dut_engine.run_cmd(f'sudo ls {path}')
            assert FILE_NOT_EXIST_ERR not in out, f'{app_name} cacert was not found in expected path: {path}\nout: {out}'
    else:
        path = consts.cacert_path.rsplit('/', 1)[0]
        with allure.step(f'check no cacert at: {path}'):
            out = dut_engine.run_cmd(f'sudo ls {path}')
            assert not out or FILE_NOT_EXIST_ERR in out, f'{app_name} cacert file unexpected in path: {path}\nout: {out}'


def verify_files(app_name: str, dut_engine: LinuxSshEngine, expected_user_config_json_values: dict = {},
                 expected_cert_id: str = '', expected_cacert_id: str = ''):
    """
    static checks:
    1. user_config.json file: check for existence of fields and their values
    2. cert file
    3. cacert file
    """
    with allure.step('verify files'):
        if expected_user_config_json_values is not None:
            with allure.independent_step('verify user_config.json'):
                verify_user_config_json(app_name, dut_engine, expected_user_config_json_values)
        if expected_cert_id is not None:
            with allure.independent_step('verify cert file'):
                verify_cert_files(app_name, dut_engine, expected_cert_id)
        if expected_cacert_id is not None:
            with allure.independent_step('verify cacert file'):
                verify_cacert_file(app_name, dut_engine, expected_cacert_id)


def attach_debug_info(cluster: Cluster, engines):
    with allure.step('DEBUG - attach info to allure'):
        allure.attach('netstat -tulnp', engines.dut.run_cmd('netstat -tulnp'))
        allure.attach('netstat -lt', engines.dut.run_cmd('netstat -lt'))
        allure.attach('user_config.json', engines.dut.run_cmd(f'sudo cat {USR_CFG_JSON_PATH}'))
        allure.attach('cluster config', cluster.show(output_format=OutputFormat.auto))

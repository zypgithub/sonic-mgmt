import random
import string
from typing import List

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import ApiType, OpenApiReqType
from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import DUT_IMPORTED_CERTS_PRIVATE_DIR, \
    DUT_IMPORTED_CERTS_PUBLIC_DIR, DUT_IMPORTED_CACERTS_DIR, CERT_PRIVATE_KEY_LOCATION, CERT_PUBLIC_KEY_LOCATION, \
    GLOBAL_CA_PEM_FILE_LOCATION, GLOBAL_CA_CRT_FILE_LOCATION, CA_POOL_FILE, GET_SYSTEM_VERSION_PATH, CertMsgs, \
    EXTERNAL_CA_CRT_FILE_LOCATION
from ngts.tests_nvos.general.security.nmx_cert.constants import EncryptionMode
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player

FILE_NOT_EXIST_ERR = 'No such file or directory'


def get_path_of_imported_cert_private_file(cert_id, dut_engine: LinuxSshEngine) -> str:
    path = f'{DUT_IMPORTED_CERTS_PRIVATE_DIR}/{cert_id}.key'
    out = dut_engine.run_cmd(f'sudo ls {path}')
    assert FILE_NOT_EXIST_ERR not in out, f'there is no private key file for the given cert-id "{cert_id}"'
    return path


def get_path_of_imported_cert_public_file(cert_id, dut_engine: LinuxSshEngine) -> str:
    path = f'{DUT_IMPORTED_CERTS_PUBLIC_DIR}/{cert_id}.crt'
    out = dut_engine.run_cmd(f'sudo ls {path}')
    assert FILE_NOT_EXIST_ERR not in out, f'there is no public crt file for the given cert-id "{cert_id}"'
    return path


def get_path_of_imported_cacert_public_file(cacert_id, dut_engine: LinuxSshEngine) -> str:
    path = f'{DUT_IMPORTED_CACERTS_DIR}/{cacert_id}.pem'
    out = dut_engine.run_cmd(f'sudo ls {path}')
    assert FILE_NOT_EXIST_ERR not in out, f'there is no public pem file for the given cacert-id "{cacert_id}"'
    return path


def import_certificates(scp_player: LinuxSshEngine, dut_engine: LinuxSshEngine, certs: List[CertInfo],
                        ca: bool = False, external_ca: bool = False):
    security_obj = System(force_api=ApiType.NVUE).security
    cert_obj = security_obj.ca_certificate if ca else security_obj.certificate

    with allure.step(f'import test {"ca" if ca else ""}certs'):
        current_certs = OutputParsingTool.parse_json_str_to_dictionary(cert_obj.show()).get_returned_value()
        for cert in certs:
            name = cert.cacert_name if ca else cert.name
            if name not in current_certs:
                with allure.step(f'import {"ca" if ca else ""}cert {name}'):
                    if ca:
                        with allure.step('import cacert'):
                            cert_obj.cert_id[name].action_import(uri=generate_scp_uri_using_player(scp_player, cert.cacert), external=external_ca).verify_result()
                        # with allure.step('scp cacert data into switch'):
                        #     scp_file(dut_engine, cert.cacert, '/tmp/')
                        # with allure.step('import cacert data'):
                        #     cert_obj.cert_id[name].action_import(
                        #         data=f'"$(cat /tmp/{cert.cacert_filename})"').verify_result()
                    else:
                        with allure.step(f'import cert {cert.name}'):
                            cert_obj.cert_id[cert.name].action_import(
                                uri_bundle=generate_scp_uri_using_player(scp_player, cert.p12_bundle),
                                passphrase=cert.p12_password).verify_result()


def delete_certificates(ca: bool = False):
    security_obj = System().security
    cert_obj = security_obj.ca_certificate if ca else security_obj.certificate
    ca_str = "ca" if ca else ""
    with allure.step(f'delete {ca_str}certs from the system'):
        current_certs = OutputParsingTool.parse_json_str_to_dictionary(cert_obj.show()).get_returned_value()
        for cert_name in current_certs:
            with allure.step(f'delete {ca_str}cert {cert_name}'):
                cert_obj.cert_id[cert_name].action_delete().verify_result()


def delete_crl():
    security_obj = System().security
    crl_resource = security_obj.crl
    with allure.step('delete crls from the system'):
        current_crls = OutputParsingTool.parse_json_str_to_dictionary(crl_resource.show()).get_returned_value()
        for crl_name in current_crls:
            with allure.step(f'delete {crl_name}'):
                crl_resource.crl_id[crl_name].action_delete().verify_result()


def import_test_certs(scp_player: LinuxSshEngine, dut_engine: LinuxSshEngine, certs: List[CertInfo], external_cas=False):
    import_certificates(scp_player, dut_engine, certs)
    import_certificates(scp_player, dut_engine, certs, True, external_cas)


def verify_file_exists_in_dut(path: str, dut_engine: LinuxSshEngine, should_exist=True):
    out = dut_engine.run_cmd(f'sudo ls {path}')
    file_exists = FILE_NOT_EXIST_ERR not in out
    assert file_exists == should_exist, (f'given path existence is not as expected\npath: {path}\nexpected: {should_exist}\n'
                                         f'actual: {file_exists}\nout:\n{out}')


def verify_cert_in_expected_locations(cert_name: str, dut_engine: LinuxSshEngine, should_exist=True):
    with allure.step(f'verify cert "{cert_name}" {"exists" if should_exist else "does not exist"} in expected locations'):
        with allure.independent_step(f'verify private'):
            verify_file_exists_in_dut(f'{CERT_PRIVATE_KEY_LOCATION}/{cert_name}.key', dut_engine, should_exist)
        with allure.independent_step(f'verify public'):
            verify_file_exists_in_dut(f'{CERT_PUBLIC_KEY_LOCATION}/{cert_name}.crt', dut_engine, should_exist)


def verify_ca_in_ssl_ca_pool(ca_name: str, ca_info: CertInfo, dut_engine: LinuxSshEngine, should_exist=True):
    with allure.step('verify default CAs pool'):
        content = ca_info.get_ca_content_str()
        with allure.independent_step(f'verify content in SSL CAs pool file'):
            ssl_ca_pool_content = dut_engine.run_cmd(f'sudo cat {CA_POOL_FILE}', print_output=False)
            given_ca_in_ssl_ca_pool = content in ssl_ca_pool_content
            assert given_ca_in_ssl_ca_pool == should_exist, (
                f'content of given CA "{ca_name}" existence in SSL CAs pool is not as expected\n'
                f'expected: {should_exist}\nactual: {given_ca_in_ssl_ca_pool}')
            verify_file_exists_in_dut(f'{GLOBAL_CA_CRT_FILE_LOCATION}/{ca_name}.crt', dut_engine, should_exist)
        with allure.independent_step(f'verify SSL can{"" if should_exist else "not"} validate the given ca certificate'):
            # verify the ca itself using ssl pool. only if the ca is in the pool it would be ok (ca verifies itself)
            filename = ''.join(random.choice(string.ascii_lowercase) for _ in range(10)) + '.pem'
            pem_file = f'/tmp/{filename}'
            dut_engine.run_cmd(f'echo """{content}""" > {pem_file}')
            res_out = dut_engine.run_cmd(f'sudo openssl verify -CAfile {CA_POOL_FILE} {pem_file}')
            dut_engine.run_cmd(f'sudo rm -f {pem_file}')
            verify_success = f'{filename}: OK' in res_out
            assert verify_success == should_exist, f'open ssl verify (using default CAs pool) result not as expected\nexpected: {should_exist}\nactual: {verify_success}\n{res_out}'


def verify_ca_in_expected_locations(ca_name: str, ca_info: CertInfo, dut_engine: LinuxSshEngine, external: bool = False, should_exist=True):
    with allure.step(f'verify ca "{ca_name}" ({"external" if external else "global"}) existence in expected locations'):
        with allure.independent_step(f'verify in global locations. expect: {should_exist and not external}'):
            with allure.independent_step(f'verify pem'):
                verify_file_exists_in_dut(f'{GLOBAL_CA_PEM_FILE_LOCATION}/{ca_name}.pem', dut_engine, should_exist and not external)
            with allure.independent_step(f'verify crt'):
                verify_file_exists_in_dut(f'{GLOBAL_CA_CRT_FILE_LOCATION}/{ca_name}.crt', dut_engine, should_exist and not external)
        with allure.independent_step(f'verify in external locations. expect: {should_exist and external}'):
            with allure.independent_step(f'verify crt'):
                verify_file_exists_in_dut(f'{EXTERNAL_CA_CRT_FILE_LOCATION}/{ca_name}.crt', dut_engine, should_exist and external)
        if ca_info:
            with allure.independent_step(f'verify in default linux SSL CAs pool. expect: {should_exist and not external}'):
                verify_ca_in_ssl_ca_pool(ca_name, ca_info, dut_engine, should_exist and not external)


def send_curl_with_and_verify(server_host, username, password, secure_mode, client_ca: CertInfo = None, client_cert: CertInfo = None, should_succeed: bool = True):
    cacert = None if not client_ca else client_ca.cacert
    client = CurlTool(server_host=server_host, username=username, password=password, cacert=cacert, client_cert=client_cert)

    skip_verify = secure_mode == EncryptionMode.DISABLED
    out, err = client.request(request_type=OpenApiReqType.GET, path=GET_SYSTEM_VERSION_PATH, skip_cert_verify=skip_verify)
    output = f'{out}\n{err}'

    got_ssl_error = any(msg in output for msg in CertMsgs.ALL_ERRORS)
    if should_succeed:
        assert not got_ssl_error, f'client got SSL err of {CertMsgs.ALL_ERRORS} but expected to succeed\nout: {out}\nerr: {err}'
    else:
        assert got_ssl_error, f'client succeeded and did not get any SSL err of {CertMsgs.ALL_ERRORS}, but expected to fail\nout: {out}\nerr: {err}'

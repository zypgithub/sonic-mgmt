from typing import List

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import DUT_IMPORTED_CERTS_PRIVATE_DIR, \
    DUT_IMPORTED_CERTS_PUBLIC_DIR, DUT_IMPORTED_CACERTS_DIR, CERT_PRIVATE_KEY_LOCATION, CERT_PUBLIC_KEY_LOCATION
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
                        ca: bool = False):
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
                            cert_obj.cert_id[name].action_import(uri=generate_scp_uri_using_player(scp_player, cert.cacert)).verify_result()
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


def import_test_certs(scp_player: LinuxSshEngine, dut_engine: LinuxSshEngine, certs: List[CertInfo]):
    import_certificates(scp_player, dut_engine, certs)
    import_certificates(scp_player, dut_engine, certs, True)


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

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tests_nvos.general.security.certificate.constants import DUT_IMPORTED_CERTS_PRIVATE_DIR, \
    DUT_IMPORTED_CERTS_PUBLIC_DIR, DUT_IMPORTED_CACERTS_DIR

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

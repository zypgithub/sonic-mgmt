import os
import random
import string
from typing import List, Dict

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_tools.infra.CertificateGenerator import CertificateGenerator
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.constants import ETC_HOSTS
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player


def add_etc_host_mapping_to_dn(dn, address, cmd_runner=None):
    cmd_runner = cmd_runner or CmdRunner()
    cmd_runner.run_cmd(f'echo "{address} {dn}" | sudo tee -a {ETC_HOSTS}')


def remove_etc_host_mapping_to_dn(dn, cmd_runner=None):
    cmd_runner = cmd_runner or CmdRunner()
    # cmd = f"sudo sed -i '/{dn}/d' {ETC_HOSTS}"
    cmd = f"cp -f {ETC_HOSTS} /tmp/hosts.new && sed -i '/{dn}/d' /tmp/hosts.new && sudo tee {ETC_HOSTS} < /tmp/hosts.new && rm -f /tmp/hosts.new"
    cmd_runner.run_cmd(cmd)


def prepare_tmp_test_certs(cert_names: List[str], dest_dir, engines, dut_hostname) -> Dict[str, CertInfo]:
    certs_info: Dict[str, CertInfo] = {}

    with allure.step('arrange test certs'):
        os.makedirs(dest_dir, exist_ok=True)
        for cert_name in cert_names:
            with allure.step(cert_name):
                with allure.step('make dir for cert'):
                    cert_dir = os.path.join(dest_dir, cert_name)
                    os.makedirs(cert_dir, exist_ok=True)
                with allure.step('add cert info'):
                    rand_pass = ''.join([random.choice(string.ascii_lowercase + '0123456789') for _ in range(10)])
                    cert_info = CertInfo(
                        name=cert_name,
                        info='cert for gnmi test',
                        private=os.path.join(cert_dir, 'cert.key'),
                        public=os.path.join(cert_dir, 'cert.pem'),
                        p12_bundle=os.path.join(cert_dir, 'cert.p12'),
                        p12_password=rand_pass,
                        dn=dut_hostname,
                        ip=engines.dut.ip,
                        cacert=os.path.join(cert_dir, 'ca.crt'),
                    )
                    certs_info[cert_name] = cert_info
                with allure.step('generate'):
                    CertificateGenerator.generate_cert(cert_dir, 'cert', cert_info.ip, cert_info.dn, cert_dir, 'ca',
                                                       cert_info.p12_password)
        with allure.step('chmod 777'):
            CmdRunner().run_cmd(f'chmod -R 777 {dest_dir}')

    return certs_info


def import_certs_safely(certs: List[CertInfo], scp_player):
    system = System()

    with allure.step('import test certs'):
        current_certs = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.certificate.show()).get_returned_value()
        for cert in certs:
            name = cert.name
            if name in current_certs:
                with allure.step(f'cert {name} already exist. delete existing one before import'):
                    system.security.certificate.cert_id[name].action_delete().verify_result()
            with allure.step(f'import cert {name}'):
                system.security.certificate.cert_id[name].action_import(
                    uri_bundle=generate_scp_uri_using_player(scp_player, cert.p12_bundle),
                    passphrase=cert.p12_password).verify_result()


def delete_certs_safely(certs: List[CertInfo]):
    system = System()

    with allure.step('delete certs from the system'):
        current_certs = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.certificate.show()).get_returned_value()
        for cert in certs:
            name = cert.name
            if name in current_certs:
                with allure.step(f'delete cert {name}'):
                    system.security.certificate.cert_id[name].action_delete().verify_result()


def import_cas_safely(cas: List[CertInfo], scp_player, external: bool = False):
    system = System()

    with allure.step('import test certs'):
        current_cas = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.ca_certificate.show()).get_returned_value()
        for ca in cas:
            name = ca.cacert_name
            if name in current_cas:
                with allure.step(f'ca {name} already exist. delete existing one before import'):
                    system.security.ca_certificate.cert_id[name].action_delete().verify_result()
            if name not in current_cas:
                with allure.step(f'import CA {name}'):
                    system.security.ca_certificate.cert_id[name].action_import(
                        uri=generate_scp_uri_using_player(scp_player, ca.cacert), external=external).verify_result()


def delete_cas_safely(cas: List[CertInfo]):
    system = System()

    with allure.step('delete certs from the system'):
        current_cas = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.certificate.show()).get_returned_value()
        for ca in cas:
            name = ca.cacert_name
            if name in current_cas:
                with allure.step(f'delete cert {name}'):
                    system.security.ca_certificate.cert_id[name].action_delete().verify_result()


def get_cert_with_ca_mismatch(certs: List[CertInfo]) -> CertInfo:
    assert len(certs) >= 2, 'provided cert list must contain at least 2 certs'
    cert1: CertInfo = certs[0]
    cert2: CertInfo = certs[1]
    cert_with_mismatch = cert1.copy()
    cert_with_mismatch.cacert = cert2.cacert
    return cert_with_mismatch

from typing import List

import pytest

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.linux_tools.linux_tools import scp_file
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.nmx_cert.constants import STATE, ENABLED, DISABLED
from ngts.tests_nvos.system.gnmi.conftest import scp_player
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player


def import_certificates(scp_player: LinuxSshEngine, dut_engine: LinuxSshEngine, certs: List[CertInfo],
                        ca: bool = False):
    security_obj = System().security
    cert_obj = security_obj.ca_certificate if ca else security_obj.certificate

    with allure.step(f'import test {"ca" if ca else ""}certs'):
        current_certs = OutputParsingTool.parse_json_str_to_dictionary(
            cert_obj.show()).get_returned_value()
        for cert in certs:
            name = cert.cacert_name if ca else cert.name
            if name not in current_certs:
                with allure.step(f'import {"ca" if ca else ""}cert {name}'):
                    if ca:
                        with allure.step('scp cacert data into switch'):
                            scp_file(dut_engine, cert.cacert, '/tmp/')
                        with allure.step('import cacert data'):
                            cert_obj.cert_id[name].action_import(
                                data=f'"$(cat /tmp/{cert.cacert_filename})"').verify_result()
                    else:
                        with allure.step(f'import cert {cert.name}'):
                            cert_obj.cert_id[cert.name].action_import(
                                uri_bundle=generate_scp_uri_using_player(scp_player, cert.p12_bundle),
                                passphrase=cert.p12_password).verify_result()


def delete_certificates(ca: bool = False):
    security_obj = System().security
    cert_obj = security_obj.ca_certificate if ca else security_obj.certificate
    with allure.step(f'delete {"ca" if ca else ""}certs from the system'):
        current_certs = OutputParsingTool.parse_json_str_to_dictionary(
            cert_obj.show()).get_returned_value()
        for cert_name in current_certs:
            with allure.step(f'delete {"ca" if ca else ""}cert {cert_name}'):
                cert_obj.cert_id[cert_name].action_delete().verify_result()


@pytest.fixture(scope='session', autouse=True)
def setup_import_certs(scp_player, engines):
    import_certificates(scp_player, engines.dut, [TestCert.cert_valid_1, TestCert.cert_valid_2])
    import_certificates(scp_player, engines.dut, [TestCert.cert_valid_1, TestCert.cert_valid_2], True)
    yield
    # delete_certificates()     # TODO: uncomment after finish testing
    # delete_certificates(True)


@pytest.fixture(autouse=True)
def setup_cleared_manager(scp_player, engines):
    cluster = Cluster()
    cluster.set(STATE, ENABLED, apply=True).verify_result()
    cluster.manager.encryption.action_restore().verify_result()
    cluster.manager.certificate.action_restore().verify_result()
    cluster.manager.ca_certificate.action_restore().verify_result()
    cluster.manager.action_restore().verify_result()


@pytest.fixture()
def enable_cluster(setup_cleared_manager):
    Cluster().set(STATE, ENABLED, apply=True).verify_result()


@pytest.fixture()
def disable_cluster(setup_cleared_manager):
    Cluster().set(STATE, DISABLED, apply=True).verify_result()

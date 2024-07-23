import logging
import random
from typing import Dict

import pytest

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType, AuthConsts, AaaConsts
from ngts.tests_nvos.general.security.security_test_tools.generic_remote_aaa_testing.constants import RemoteAaaType
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import RemoteAaaServerInfo
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tests_nvos.general.security.tacacs.constants import TacacsDockerServer0
from ngts.tests_nvos.general.security.test_aaa_ldap.ldap_servers_info import LdapServersP3
from ngts.tests_nvos.general.security.test_aaa_radius.constants import RadiusVmServer
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import ETC_HOSTS, GNMI_TEST_CERT, DUT_MOUNT_GNMI_CERT_DIR
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player

logger = logging.getLogger()


@pytest.fixture(scope='session')
def scp_player(engines) -> LinuxSshEngine:
    return engines.sonic_mgmt
    # return LinuxSshEngine(ip='10.237.116.70', username='root', password='12345')


@pytest.fixture(scope='session', autouse=True)
def verify_gnmi_client_tools_installed_on_player():
    player = GnmiClient('', '', '', '', 10)
    with allure.step('verify gnmic installation on test player'):
        player.verify_gnmic_installation()
    with allure.step('verify grpcurl  installation on test player'):
        player.verify_grpcurl_installation()


@pytest.fixture()
def aaa_users(engines) -> Dict[str, UserInfo]:
    with allure.step('set AAA servers'):
        with allure.step('set tacacs server'):
            tac_server: RemoteAaaServerInfo = TacacsDockerServer0.SERVER_BY_ADDRESSING_TYPE[
                random.choice(AddressingType.ALL_TYPES)]
            tac_server.configure(engines)
        with allure.step('set ldap server'):
            ldap_server: RemoteAaaServerInfo = LdapServersP3.LDAP1_SERVERS[random.choice(AddressingType.ALL_TYPES)]
            ldap_server.configure(engines)
        with allure.step('set radius server'):
            rad_server: RemoteAaaServerInfo = RadiusVmServer.SERVER_BY_ADDRESSING_TYPE[
                random.choice(AddressingType.ALL_TYPES)]
            rad_server.configure(engines)
        with allure.step('enable failthrough'):
            System().aaa.authentication.set(AuthConsts.FAILTHROUGH, AaaConsts.ENABLED, apply=True).verify_result()
    return {
        RemoteAaaType.TACACS: tac_server.users[0],
        RemoteAaaType.LDAP: ldap_server.users[0],
        RemoteAaaType.RADIUS: rad_server.users[0],
    }
    # servers config cleared in clear_conf hook func


@pytest.fixture(scope='module', autouse=True)
def add_etc_host_mapping_for_test_cert(engines):
    cert = GNMI_TEST_CERT
    with allure.step(f'add mapping of new dut hostname to {ETC_HOSTS}'):
        cmd_runner = CmdRunner()
        cmd_runner.run_cmd_in_process(f'echo "{engines.dut.ip} {cert.dn}" | sudo tee -a {ETC_HOSTS}')
    yield
    with allure.step(f'remove hostname mapping fro {ETC_HOSTS}'):
        cmd_runner.run_cmd_in_process(f"sudo sed -i '/{cert.dn}/d' {ETC_HOSTS}", wait_till_done=True)


@pytest.fixture()
def restore_gnmi_cert(engines):
    yield
    with allure.step('restore orig gnmi cert'):
        engines.dut.run_cmd(f'sudo rm -f {DUT_MOUNT_GNMI_CERT_DIR}/*')
    with allure.step('reload gnmi'):
        System().gnmi_server.disable_gnmi_server(True)
        System().gnmi_server.enable_gnmi_server(True)


@pytest.fixture(scope='module', autouse=True)
def import_test_certs(scp_player):
    system = System()
    test_certs = [TestCert.cert_valid_1, TestCert.cert_ca_mismatch]

    with allure.step('import test certs'):
        current_certs = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.certificate.show()).get_returned_value()
        for cert in test_certs:
            if cert.name not in current_certs:
                with allure.step(f'import cert {cert.name}'):
                    system.security.certificate.cert_id[cert.name].action_import(
                        uri_bundle=generate_scp_uri_using_player(scp_player, cert.p12_bundle),
                        passphrase=cert.p12_password).verify_result()
    yield
    with allure.step('delete certs from the system'):
        current_certs = OutputParsingTool.parse_json_str_to_dictionary(
            system.security.certificate.show()).get_returned_value()
        for cert in current_certs:
            with allure.step(f'delete cert {cert}'):
                system.security.certificate.cert_id[cert].action_delete().verify_result()

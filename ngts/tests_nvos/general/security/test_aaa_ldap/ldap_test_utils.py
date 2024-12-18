import time

from ngts.nvos_tools.system.Server import ServerId
from ngts.tests_nvos.general.security.security_test_tools.resource_utils import configure_resource
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.RemoteAaaServerInfo import RemoteAaaServerInfo, \
    LdapServerInfo
from ngts.tests_nvos.general.security.test_aaa_ldap.constants import LdapConsts, LdapEncryptionModes
from ngts.tools.test_utils import allure_utils as allure


class LdapTestTool:
    active_ldap_server = None


def configure_ldap_common_fields(engines, ldap_obj, apply=False):
    ldap_server_info = LdapConsts.PHYSICAL_LDAP_SERVER
    with allure.step('Configure general settings to match our test servers'):
        conf_to_set = {
            LdapConsts.PORT: ldap_server_info[LdapConsts.PORT],
            LdapConsts.BASE_DN: ldap_server_info[LdapConsts.BASE_DN],
            LdapConsts.BIND_DN: ldap_server_info[LdapConsts.BIND_DN],
            # LdapConsts.LOGIN_ATTR: ldap_server_info[LdapConsts.LOGIN_ATTR],  not supported now
            LdapConsts.SECRET: ldap_server_info[LdapConsts.SECRET],
            LdapConsts.TIMEOUT_BIND: ldap_server_info[LdapConsts.TIMEOUT_BIND],
            LdapConsts.TIMEOUT: ldap_server_info[LdapConsts.TIMEOUT],
            LdapConsts.VERSION: ldap_server_info[LdapConsts.VERSION]
        }
        configure_resource(engines, ldap_obj, conf_to_set, apply=apply)


def configure_ldap_encryption(engines, ldap_obj, encryption_mode, apply=False, dut_engine=None,
                              server_info: LdapServerInfo = None, verify_apply=False, disable_cert_verify: bool = True):
    """
    @summary: Configure ldap settings according to the given encryption mode
    @param engines: engines object
    @param ldap_obj: Ldap object (under System.Aaa object)
    @param encryption_mode: in [NONE, START_TLS, SSL]
    """
    with allure.step(f'Configure ldap encryption: {encryption_mode}'):
        conf_to_set = {
            LdapConsts.SSL_PORT: server_info.ssl_port
        }
        if disable_cert_verify:
            conf_to_set[LdapConsts.SSL_CERT_VERIFY] = LdapConsts.DISABLED
        if encryption_mode == LdapEncryptionModes.START_TLS:
            conf_to_set[LdapConsts.SSL_MODE] = LdapEncryptionModes.START_TLS
        elif encryption_mode == LdapEncryptionModes.SSL:
            conf_to_set[LdapConsts.SSL_MODE] = LdapEncryptionModes.SSL
        elif encryption_mode == LdapEncryptionModes.NONE:
            conf_to_set[LdapConsts.SSL_MODE] = LdapEncryptionModes.NONE
        configure_resource(engines, ldap_obj.ssl, conf=conf_to_set, apply=apply, verify_apply=verify_apply,
                           dut_engine=dut_engine)


def update_ldap_encryption_mode(engines, item, server_info: RemoteAaaServerInfo, server_resource: ServerId,
                                encryption_mode: str, disable_cert_verify: bool = True):
    engine = getattr(item, 'active_remote_admin_engine', False)
    if engine is False:
        engine = None
    configure_ldap_encryption(engines, server_resource.parent_obj.parent_obj, encryption_mode, apply=True,
                              dut_engine=engine, server_info=server_info, disable_cert_verify=disable_cert_verify)


def add_ldap_server_certificate_to_switch(dut_engine):
    """
    @summary: Add ldap server certificate to the switch
    """
    with allure.step('Append server certificate to certificates file'):
        dut_engine.run_cmd(
            f"sudo sh -c 'cat {LdapConsts.SERVER_CERT_FILE_IN_SWITCH} >> {LdapConsts.SWITCH_CA_FILE}'")

    with allure.step('Restart nslcd service'):
        dut_engine.run_cmd('sudo service nslcd restart')
        time.sleep(3)

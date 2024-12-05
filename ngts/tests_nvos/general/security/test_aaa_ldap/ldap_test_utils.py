import logging
import random
import time

from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.Hostname import HostnameId
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.security_test_tools.constants import AuthConsts, AaaConsts
from ngts.tests_nvos.general.security.security_test_tools.resource_utils import configure_resource
from ngts.tests_nvos.general.security.security_test_tools.security_test_utils import configure_authentication, \
    validate_services_and_dockers_availability, find_server_admin_user
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


def configure_ldap(ldap_server_info):
    """
    @summary: configure ldap server from the given ldap_server_info
    :param ldap_server_info: a dict containing the ldap server info. e.g.:
    {
        "hostname" : <value>,
        "base-dn" : <value>,
        "bind-dn" " <value>,
        "secret" : <value>,
        "login-attribute" : <value>,
        "group-attribute" : <value>,
        "scope" : <value>,
        "port" : <value>,
        "timeout-bind" : <value>,
        "timeout" : <value>,
        "version" : <value>,
        "priority" : <value>
    }
    """
    system = System(None)

    with allure.step("Configuring ldap server"):
        if ldap_server_info.get(LdapConsts.SCOPE):
            system.aaa.ldap.set(LdapConsts.SCOPE, ldap_server_info[LdapConsts.SCOPE])
        if ldap_server_info.get(LdapConsts.BASE_DN):
            system.aaa.ldap.set(LdapConsts.BASE_DN, ldap_server_info[LdapConsts.BASE_DN])
        if ldap_server_info.get(LdapConsts.BIND_DN):
            system.aaa.ldap.set(LdapConsts.BIND_DN, ldap_server_info[LdapConsts.BIND_DN])
        if ldap_server_info.get(LdapConsts.SECRET):
            system.aaa.ldap.set(LdapConsts.SECRET, ldap_server_info[LdapConsts.SECRET])
        if ldap_server_info.get(LdapConsts.PORT):
            system.aaa.ldap.set(LdapConsts.PORT, ldap_server_info[LdapConsts.PORT])
        if ldap_server_info.get(LdapConsts.TIMEOUT):
            system.aaa.ldap.set(LdapConsts.TIMEOUT, ldap_server_info[LdapConsts.TIMEOUT])
        if ldap_server_info.get(LdapConsts.TIMEOUT_BIND):
            system.aaa.ldap.set(LdapConsts.TIMEOUT_BIND, ldap_server_info[LdapConsts.TIMEOUT_BIND])
        if ldap_server_info.get(LdapConsts.VERSION):
            system.aaa.ldap.set(LdapConsts.VERSION, ldap_server_info[LdapConsts.VERSION])
        if ldap_server_info.get(LdapConsts.PRIORITY):
            priority = int(ldap_server_info[LdapConsts.PRIORITY])
        else:
            priority = LdapConsts.DEFAULT_PRIORTIY
        system.aaa.ldap.hostname.hostname_id[ldap_server_info[LdapConsts.HOSTNAME]].set(LdapConsts.PRIORITY, priority,
                                                                                        apply=True).verify_result()


def validate_ldap_configurations(ldap_server_info):
    """
    @summary: validate ldap server configurations same as the given ldap_server_info
    :param ldap_server_info: a dict containing the ldap server info. e.g.:
    {
        "hostname" : <value>,
        "base-dn" : <value>,
        "bind-dn" " <value>,
        "secret" : <value>,
        "login-attribute" : <value>,
        "group-attribute" : <value>,
        "scope" : <value>,
        "port" : <value>,
        "timeout-bind" : <value>,
        "timeout" : <value>,
        "version" : <value>,
        "priority" : <value>
    }
    """
    system = System(None)

    with allure.step("Validating the configuration of ldap to be the same as {}".format(ldap_server_info)):
        output = system.aaa.ldap.show()
        output = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()
        expected_field = [LdapConsts.PORT, LdapConsts.BASE_DN, LdapConsts.BIND_DN,
                          # LdapConsts.LOGIN_ATTR,  not supported now
                          LdapConsts.TIMEOUT_BIND, LdapConsts.TIMEOUT]
        expected_values = [ldap_server_info[LdapConsts.PORT], ldap_server_info[LdapConsts.BASE_DN],
                           ldap_server_info[LdapConsts.BIND_DN],
                           # ldap_server_info[LdapConsts.LOGIN_ATTR],  not supported now
                           ldap_server_info[LdapConsts.TIMEOUT_BIND], ldap_server_info[LdapConsts.TIMEOUT],
                           ldap_server_info[LdapConsts.VERSION]]
        ValidationTool.validate_fields_values_in_output(expected_fields=expected_field,
                                                        expected_values=expected_values,
                                                        output_dict=output).verify_result()
        output = system.aaa.ldap.hostname.hostname_id[ldap_server_info[LdapConsts.HOSTNAME]].show()
        output = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()
        expected_field = [LdapConsts.PRIORITY]
        expected_values = [ldap_server_info[LdapConsts.PRIORITY]]
        ValidationTool.validate_fields_values_in_output(expected_fields=expected_field,
                                                        expected_values=expected_values,
                                                        output_dict=output).verify_result()


def enable_ldap_feature(engines, devices):
    """
    @summary:
        in this function we want to enable the LDAP server functionality,
        in the current implementation we use sonic commands, once the nv commands
        are available we will change this function
    """
    with allure.step("Enabling LDAP by setting LDAP auth. method as first auth. method"):
        configure_authentication(engines, devices, order=[AuthConsts.LDAP, AuthConsts.LOCAL],
                                 failthrough=LdapConsts.ENABLED, fallback=LdapConsts.ENABLED, apply=True)


def configure_ldap_and_validate(engines, ldap_server_list, devices, should_validate_conf=True):
    """
    @summary: in this function we will configure ldap servers in he ldap server list
    and validate the ldap configurations per server
    """
    ldap_is_enabled = False

    for ldap_server_info in ldap_server_list:
        with allure.step("Configuring ldap server {}".format(ldap_server_info)):
            configure_ldap(ldap_server_info)

        if should_validate_conf:
            with allure.step("Validating ldap server configurations"):
                validate_ldap_configurations(ldap_server_info)

        if not ldap_is_enabled:
            enable_ldap_feature(engines, devices)
            ldap_is_enabled = True

    validate_services_and_dockers_availability(engines, devices)


def randomize_ldap_server():
    """
    @summary:
        in this function we randomize ldap server dictionary and return it.
        e.g. of return value:
        {
            "hostname" : <value>
        }
    """
    randomized_ldap_server_info = {
        "hostname": f"1.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}",
    }
    return randomized_ldap_server_info


def configure_ldap_server(engines, ldap_obj, ldap_server_info, apply=False):
    """
    @summary: Configure ldap server according to the given server information
    @param engines: engines object
    @param ldap_obj: Ldap object (under System.Aaa object)
    @param ldap_server_info: dictionary that holds information about the given server
    """
    with allure.step(f'Configure ldap server: {ldap_server_info[LdapConsts.HOSTNAME]}'):
        logging.info(f'Server details:\n{ldap_server_info}')

        with allure.step('Configure general settings to match the given server'):
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
            configure_resource(engines, ldap_obj, conf_to_set, apply=False)

        with allure.step('Configure the given server with its priority'):
            priority = int(ldap_server_info[LdapConsts.PRIORITY])
            ldap_obj.hostname.hostname_id[ldap_server_info[LdapConsts.HOSTNAME]].set(LdapConsts.PRIORITY, priority,
                                                                                     apply=apply).verify_result()


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


def update_ldap_encryption_mode(engines, item, server_info: RemoteAaaServerInfo, server_resource: HostnameId,
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


def get_active_dut_engine(engines):
    with allure.step('Get active engine'):
        with allure.step(f'Check active ldap server from LdapTestActiveServer'):
            ldap_server_info = LdapTestTool.active_ldap_server

        if not ldap_server_info:
            logging.info('Active engine to use: default dut engine')
            active_engine = engines.dut
        else:
            logging.info('Active engine to use: New engine with ldap admin user')
            with allure.step(f'Find admin user in ldap server {ldap_server_info[LdapConsts.HOSTNAME]}'):
                ldap_admin_user_info = find_server_admin_user(ldap_server_info)
                logging.info(f'Found admin user: {ldap_admin_user_info[AaaConsts.USERNAME]}')

            with allure.step(f"Creating engine to switch with username: {ldap_admin_user_info[AaaConsts.USERNAME]}"):
                active_engine = ProxySshEngine(device_type=engines.dut.device_type,
                                               ip=engines.dut.ip,
                                               username=ldap_admin_user_info[AaaConsts.USERNAME],
                                               password=ldap_admin_user_info[AaaConsts.PASSWORD])
        return active_engine


def disable_ldap(engines):
    """
    @summary: Remove ldap from authentication order configuration using an admin user from the given ldap server
    """
    with allure.step('Get active engine to use to disable ldap'):
        active_engine = get_active_dut_engine(engines)

    with allure.step('Remove ldap from authentication order using active engine'):
        with allure.step('Unset authentication order configuration through new engine'):
            orig_api = TestToolkit.tested_api
            TestToolkit.tested_api = ApiType.NVUE
            System().aaa.authentication.unset(op_param=AuthConsts.ORDER, apply=True, dut_engine=active_engine)
            TestToolkit.tested_api = orig_api

    with allure.step('Reset active ldap server info in LdapTestTool'):
        LdapTestTool.active_ldap_server = None

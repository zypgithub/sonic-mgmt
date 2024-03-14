import allure as orig_allure
import pytest

from tests.common.constants import DEFAULT_SSH_CONNECT_PARAMS
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.ldap.constants import USERNAME, PASSWORD
from tests.ldap.helpers import LdapServer, start_ldap_server, stop_ldap_server, clear_ldap_global_config, \
    clear_ldap_servers, clear_authentication_config, User


@pytest.fixture()
def dut(duthosts, enum_rand_one_per_hwsku_hostname):
    return duthosts[enum_rand_one_per_hwsku_hostname]


@pytest.fixture(scope='module', autouse=False)
def ldap_server(ptfhost) -> LdapServer:
    with allure.step('install and start ldap server on ptf'):
        server_details = start_ldap_server(ptfhost)

    yield server_details

    with allure.step('stop and remove ldap server'):
        stop_ldap_server(ptfhost)


@pytest.fixture(scope='function', autouse=True)
def clear_ldap_config(duthost):
    ldap_global_config = duthost.command('show ldap global')['stdout']
    ldap_server_config = duthost.command('show ldap-server')['stdout']
    aaa_config = duthost.command('show aaa')['stdout']
    orig_allure.attach(f'{ldap_global_config}', 'ldap_global_config', orig_allure.attachment_type.TEXT)
    orig_allure.attach(f'{ldap_server_config}', 'ldap_server_config', orig_allure.attachment_type.TEXT)
    orig_allure.attach(f'{aaa_config}', 'aaa_config', orig_allure.attachment_type.TEXT)
    yield
    with allure.step('clear ldap global config'):
        clear_ldap_global_config(duthost)
    with allure.step('clear ldap servers'):
        clear_ldap_servers(duthost)
    with allure.step('clear ldap authentication'):
        clear_authentication_config(duthost)


@pytest.fixture()
def local_user(dut) -> User:
    default_creds = DEFAULT_SSH_CONNECT_PARAMS['public']
    return User(default_creds[USERNAME], default_creds[PASSWORD])

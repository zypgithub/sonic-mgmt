import logging

import pytest

from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.ldap.constants import BIND_DN, BIND_PASSWORD, BIND_TIMEOUT, VERSION, BASE_DN, PORT, TIMEOUT, LDAP
from tests.ldap.helpers import LdapServer, User, verify_ssh_login, get_configured_servers, verify_nslcd_running_on_dut

pytestmark = [
    pytest.mark.disable_loganalyzer,
    pytest.mark.topology('any'),
    pytest.mark.device_type('vs')
]


def test_ldap_cli(dut):
    """
    Verify ldap cli is working properly

    1. set global ldap config and verify in show
    2. set server ldap config and verify in show
    3. set ldap authentication and verify in show
    """
    with allure.step('ldap global config'):
        with allure.step('configure'):
            expected_config = {
                BIND_DN: 'asd',
                BIND_PASSWORD: 'asd',
                BIND_TIMEOUT: 6,
                VERSION: 1,
                BASE_DN: 'asd',
                PORT: 6692,
                TIMEOUT: 6
            }
            fields = list(expected_config.keys())
            cmds = [f'sudo config ldap global {field} {val}' for field, val in expected_config.items()]
            dut.shell_cmds(cmds=cmds)
        with allure.step('verify in show'):
            actual_config = dut.show_and_parse(show_cmd='show ldap global')[0]
            actual_config = {k.replace(' ', '-'): v for k, v in actual_config.items()}
            logging.info(f'values dict:\n{actual_config}')
            assert len(list(actual_config.keys())) == len(fields), "number of fields don't match. expected"
            errs = []
            for field in fields:
                if field not in actual_config:
                    errs.append(f'field {field} does not exist')
                elif str(expected_config[field]) != str(actual_config[field]):
                    errs.append(f'field {field} - expected: {expected_config[field]} actual: {actual_config[field]}')
            assert not errs, '\n'.join(errs)

    with allure.step('ldap server config'):
        with allure.step('configure'):
            expected_servers = {f'{i}.{2 * i}.{3 * i}.{4 * i}': i for i in range(1, 9)}
            cmds = [f'sudo config ldap-server add {hostname} --priority {priority}'
                    for hostname, priority in expected_servers.items()]
            dut.shell_cmds(cmds=cmds)
        with allure.step('verify in show'):
            configured_servers = get_configured_servers(dut)
            assert len(configured_servers) == 8, f'''number of servers in output not as expected.
                                                        expected: 8
                                                        actual: {len(configured_servers)}'''
            errs = []
            for hostname, priority in configured_servers.items():
                if hostname not in expected_servers:
                    errs.append(f'''hostname {hostname} was not expected''')
                elif str(priority) != str(expected_servers[hostname]):
                    errs.append(f'''priority of hostname {hostname} not as expected
                                    expected: {expected_servers[hostname]}
                                    actual: {priority}''')
            assert not errs, '\n'.join(errs)

    with allure.step('ldap authentication config'):
        with allure.step('configure'):
            dut.command(f'sudo config aaa authentication login {LDAP}')
        with allure.step('verify in show'):
            login_value = dut.command('show aaa')['stdout_lines'][0] \
                .replace('AAA authentication login', '') \
                .replace('(default)', '') \
                .strip()
            assert login_value == LDAP, f'''login value in output not as expected.
                                                    expected: {LDAP}
                                                    actual: {login_value}'''


def test_ldap_authentication(dut, ldap_server: LdapServer, local_user: User):
    with allure.step('configure ldap server'):
        ldap_server.configure(dut)
    with allure.step('enable ldap authentication'):
        ldap_server.configure_authentication(dut)
    with allure.step('wait for ldap service to be ready'):
        assert verify_nslcd_running_on_dut(dut), 'nslcd service is not ready'
    with allure.step('verify ldap authentication success'):
        verify_ssh_login(ip=dut.mgmt_ip, username=ldap_server.users[0].username,
                         password=ldap_server.users[0].password, expect_success=True)
    with allure.step('verify local authentication fail'):
        verify_ssh_login(ip=dut.mgmt_ip, username=local_user.username, password=local_user.password,
                         expect_success=False)

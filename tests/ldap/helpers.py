import base64
import logging
import os
import random
import string
from typing import List

import paramiko

from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.common.utilities import wait_until
from tests.ldap.constants import BIND_DN, BIND_PASSWORD, BIND_TIMEOUT, VERSION, BASE_DN, PORT, TIMEOUT, LDAP, ENABLE, \
    DISABLE, SERVER_BASE_DN, SERVER_PORT, LDAP_SCRIPT_FILENAME, USERNAME, PLACEHOLDERS, PASSWORD, BIND_USERNAME, \
    HOSTNAME, PRIORITY, GLOBAL_FIELDS

TIMEOUT_LIMIT = 120


def ssh_connect_remote(remote_ip, remote_username, remote_password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        remote_ip, username=remote_username, password=remote_password, allow_agent=False,
        look_for_keys=False, auth_timeout=TIMEOUT_LIMIT)
    return ssh


class User:
    def __init__(self, username, password):
        self.username = username
        self.password = password

    def string(self) -> str:
        return f'{self.username} / {self.password}'


class LdapServer:
    def __init__(self, ip: str, port, bind_dn_username: str, bind_password: str, base_dn: str, bind_timeout=5,
                 timeout=5, priority=1, version=3, users: List[User] = None):
        self.ip = ip
        self.port = port
        self.bind_dn_username = bind_dn_username
        self.bind_dn = bind_dn_username
        if not self.bind_dn.startswith('cn='):
            self.bind_dn = f'cn={self.bind_dn}'
        if not self.bind_dn.endswith(base_dn):
            self.bind_dn = f'{self.bind_dn},{base_dn}'
        self.bind_password = bind_password
        self.bind_timeout = bind_timeout
        self.base_dn = base_dn
        self.timeout = timeout
        self.priority = priority
        self.version = version
        self.users: List[User] = users if users else []

    def configure(self, duthost, change_priority=None):
        expected_config = {
            BIND_DN: self.bind_dn,
            BIND_PASSWORD: self.bind_password,
            BIND_TIMEOUT: self.bind_timeout,
            VERSION: self.version,
            BASE_DN: self.base_dn,
            PORT: self.port,
            TIMEOUT: self.timeout
        }
        cmds = [f'sudo config ldap global {field} {val}' for field, val in expected_config.items()]
        self.priority = change_priority if change_priority else self.priority
        cmds.append(f'sudo config ldap-server add {self.ip} --priority {self.priority}')
        duthost.shell_cmds(cmds=cmds)

    def configure_authentication(self, duthost, first: str = LDAP, second: str = '', failthrough=None):
        cmds = [
            f'sudo config aaa authentication login {first} {second}'.strip(),
        ]
        if failthrough is not None and isinstance(failthrough, bool):
            cmds.append(f'sudo config aaa authentication failthrough {ENABLE if failthrough else DISABLE}')
        duthost.shell_cmds(cmds=cmds)

    def string(self) -> str:
        info: str = f'''ldap server info:
        ip: {self.ip}
        port: {self.port}
        bind_dn: {self.bind_dn}
        bind_password: {self.bind_password}
        base_dn: {self.base_dn}
        priority: {self.priority}
        bind_timeout: {self.bind_timeout}
        timeout: {self.timeout}
        version: {self.version}
        --------------
        users:
        '''
        info += '\n'.join(user.string() for user in self.users)
        return info


def stop_ldap_server(ptfhost):
    ptfhost.command('service slapd stop', module_ignore_errors=True)
    ptfhost.command('apt remove slapd -y', module_ignore_errors=True)
    ptfhost.command('apt purge slapd -y', module_ignore_errors=True)


def start_ldap_server(ptfhost) -> LdapServer:
    with allure.step('generate concrete server details for the test'):
        server_details = generate_server_details(ptfhost.mgmt_ip)
    with allure.step('modify setup script placeholders according to server details'):
        server_setup_script = modify_server_setup_script(server_details)
    with allure.step('upload setup script to PTF'):
        script_path_on_ptf = upload_script_to_ptf(ptfhost, server_setup_script)
    with allure.step('run setup script on PTF'):
        log_ptf_services_status(ptfhost)
        run_setup_script_on_ptf(ptfhost, script_path_on_ptf)
        assert verify_slapd_running_on_ptf(ptfhost)
        log_ptf_services_status(ptfhost)
        return server_details


def log_ptf_services_status(ptfhost):
    res = ptfhost.command("service --status-all")
    logging.info(res["stdout_lines"])


def generate_server_details(server_ip) -> LdapServer:
    rand_username = ''.join(random.choices(string.ascii_lowercase, k=6))
    rand_password = ''.join(random.choices(string.ascii_lowercase, k=6))
    rand_bind_dn_username = ''.join(random.choices(string.ascii_lowercase, k=6))
    rand_bind_password = ''.join(random.choices(string.ascii_lowercase, k=6))
    server_details = LdapServer(server_ip, SERVER_PORT, rand_bind_dn_username, rand_bind_password, SERVER_BASE_DN,
                                users=[User(rand_username, rand_password)])
    logging.info(server_details.string())
    return server_details


def modify_server_setup_script(server_details: LdapServer) -> str:
    base_dir_path = os.path.dirname(os.path.realpath(__file__))
    script_file_path = os.path.join(base_dir_path, LDAP_SCRIPT_FILENAME)
    modified_script_file_path = os.path.join(base_dir_path, f'copy_{LDAP_SCRIPT_FILENAME}')
    with open(script_file_path, 'r') as f:
        script_content = f.read()
    modified_content = script_content \
        .replace(PLACEHOLDERS[BASE_DN], server_details.base_dn) \
        .replace(PLACEHOLDERS[USERNAME], server_details.users[0].username) \
        .replace(PLACEHOLDERS[PASSWORD], base64.b64encode(server_details.users[0].password.encode()).decode()) \
        .replace(PLACEHOLDERS[BIND_USERNAME], server_details.bind_dn_username) \
        .replace(PLACEHOLDERS[BIND_PASSWORD], server_details.bind_password)
    with open(modified_script_file_path, 'w') as f:
        f.write(modified_content)
    return modified_script_file_path


def upload_script_to_ptf(ptfhost, script_file) -> str:
    ptfhost.command('mkdir -p /tmp/ldap/')
    setup_script_path_on_ptf = f'/tmp/ldap/{LDAP_SCRIPT_FILENAME}'
    with allure.step(f'copy {script_file} to PTF, at: {setup_script_path_on_ptf}'):
        ptfhost.copy(src=script_file, dest=setup_script_path_on_ptf)
        return setup_script_path_on_ptf


def run_setup_script_on_ptf(ptfhost, script_path_on_ptf):
    cmd = f'chmod +x {script_path_on_ptf}'
    with allure.step(f'run: {cmd}'):
        ptfhost.command(cmd)
    cmd = f'bash {script_path_on_ptf}'
    with allure.step(f'run: {cmd}'):
        ptfhost.command(cmd)


def verify_slapd_running_on_ptf(ptfhost):
    def slapd_running(ptf):
        out = ptf.command("service slapd status", module_ignore_errors=True)["stdout"]
        return "slapd is running" in out

    ptfhost.command("service slapd restart", module_ignore_errors=True)
    return wait_until(5, 1, 0, slapd_running, ptfhost)


def verify_ssh_login(ip: str, username: str, password: str, expect_success: bool = True):
    with allure.step('try ssh login'):
        success: bool = True
        try:
            ssh_connect_remote(remote_ip=ip, remote_username=username, remote_password=password)
        except paramiko.AuthenticationException:
            success = False
    with allure.step(f'assert success result is: {expect_success}'):
        assert success == expect_success, f'actual login success: {success}. expected: {expect_success}'


def get_configured_servers(duthost):
    servers = duthost.show_and_parse(show_cmd='show ldap-server')
    return {server[HOSTNAME]: server[PRIORITY] for server in servers}


def clear_ldap_global_config(duthost):
    # reset all related configurations to default
    cmds = [f'sudo config ldap global {field} 3' for field in GLOBAL_FIELDS]
    duthost.shell_cmds(cmds=cmds)


def clear_ldap_servers(duthost):
    servers = get_configured_servers(duthost)
    cmds = [f'sudo config ldap-server delete {server}' for server in servers.keys()]
    duthost.shell_cmds(cmds=cmds)


def clear_authentication_config(duthost):
    cmds = [
        'sudo config aaa authentication login default',
        'sudo config aaa authentication failthrough default'
    ]
    duthost.shell_cmds(cmds=cmds)


def verify_nslcd_running_on_dut(duthost):
    def nslcd_running(dut):
        out = dut.command("sudo service nslcd status", module_ignore_errors=True)["stdout"]
        return "Active: active (running)" in out

    return wait_until(6, 1, 0, nslcd_running, duthost)

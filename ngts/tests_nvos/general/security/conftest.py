import logging
import time

import pexpect
import pytest

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.general_constants.constants import DefaultConnectionValues
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.Devices.EthDevice import EthSwitch  # temporary, needed until nv unification RM 3735390.
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.PexpectTool import PexpectTool
from ngts.nvos_tools.infra.SshCmdBuilder import SshPassCmdBuilder
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.conftest import security_cleanup
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts, AuthConsts
from ngts.tests_nvos.general.security.security_test_tools.security_test_utils import set_local_users
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.UserInfo import UserInfo
from ngts.tools.test_utils.switch_recovery import generate_strong_password, recover_dut_with_remote_reboot

logger = logging.getLogger(__name__)


@pytest.fixture()
def cleanup_after_aaa(topology_obj, engines, request):
    dut: LinuxSshEngine = engines.dut

    with allure.step('ssh the switch with long logout time'):
        # ssh_cmd = f'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=60 -o ServerAliveCountMax=5 {dut.username}@{dut.ip}'
        sshpass_cmd = SshPassCmdBuilder(dut.username, dut.password, dut.ip).set_ssn().set_long_lasting_session().build()
        ssh_session = PexpectTool(sshpass_cmd)
        # ssh_session.expect('[Pp]assword:')
        i = ssh_session.expect(DefaultConnectionValues.DEFAULT_PROMPTS)
        assert i < len(DefaultConnectionValues.DEFAULT_PROMPTS), 'could not ssh the switch'
    with allure.step('update pytest item for the cleanup stage'):
        item = request.node
        item.security_pexpect_ssh_session = ssh_session

    yield

    skip_rr = security_cleanup(ssh_session)

    if engines and topology_obj and not skip_rr:
        with allure.step('try recover with remote reboot'):
            recover_dut_with_remote_reboot(topology_obj, engines)


def create_ssh_login_engine(dut_ip, username, port=22, custom_ssh_options=None):
    '''
    @summary: in this function we want to create ssh connection to device,
    ssh connection means that only executing the command:
    'ssh {-o OPTIONS} -l {username} {dut_ip}'
    without entering password!
    :param dut_ip: device IP
    :param username: username initiating the ssh connection
    :param port: connection port, by default 22
    :return: pexpect python module with ssh connection command executed
    '''
    ssh_options = custom_ssh_options if custom_ssh_options is not None else DefaultConnectionValues.BASIC_SSH_CONNECTION_OPTIONS
    _ssh_command = 'ssh {} -p {} -l {} {}'.format(ssh_options,
                                                  port,
                                                  username,
                                                  dut_ip)
    # connect to device
    child = pexpect.spawn(_ssh_command, env={'TERM': 'dumb'}, timeout=10)
    return child


def ssh_to_device_and_retrieve_raw_login_ssh_notification(dut_ip,
                                                          username=None,
                                                          password=None,
                                                          port=22):
    '''
    @summary: in this function we create ssh connection
    and return the raw output after connecting to device
    '''
    notification_login_message = ''
    device = TestToolkit.devices.dut
    if not username or not password:
        username = device.default_username
        password = device.default_password

    with allure.step("Connection to dut device with SSH"):
        logger.info("Connection to dut device with SSH")
        # connecting using pexpect
        try:
            child = create_ssh_login_engine(dut_ip, username, port)
            respond = child.expect([DefaultConnectionValues.PASSWORD_REGEX, '~'])
            if respond == 0:
                notification_login_message += child.before.decode('utf-8')
                child.sendline(password)
                child.expect(DefaultConnectionValues.DEFAULT_PROMPTS[0])

            # convert output to decode
            notification_login_message += child.before.decode('utf-8')
            # close connection
        finally:
            child.close()
        return notification_login_message


@pytest.fixture(scope='function')
def post_test_remote_reboot(topology_obj):
    '''
    @summary: perform remote reboot from the physical server using the noga remote reboot command,
    usually the command should be like this: '/auto/mswg/utils/bin/rreboot <ip|hostname>'
    after the test is done as a part of cleanup
    '''
    yield

    logging.info("Performing remote reboot to switch")
    cmd = topology_obj.players['dut_serial']['attributes'].noga_query_data['attributes']['Specific'][
        'remote_reboot']
    assert cmd, "Reboot command is empty"
    topology_obj.players['server']['engine'].run_cmd(cmd)
    SLEEP_AFTER_REBOOT = 60
    logging.info("Sleeping {} secs after reboot".format(SLEEP_AFTER_REBOOT))
    time.sleep(SLEEP_AFTER_REBOOT)
    # verify dockers are up
    logging.info("Verifying that dockers are up")
    TestToolkit.engines.dut.disconnect()
    nvue_cli = NvueGeneralCli(TestToolkit.engines.dut, TestToolkit.devices.dut)
    nvue_cli.verify_dockers_are_up()


@pytest.fixture(scope='function')
def is_secure_boot_enabled(engines):
    res = "0"
    try:
        res = engines.dut.run_cmd('bootctl status 2>/dev/null | grep -c "Secure Boot: enabled"')
    except BaseException as err:
        logging.info(err)

    if res != "1":
        logging.info("The test is skipped - secure boot is disabled")
        pytest.skip("The test is skipped - secure boot is disabled")


@pytest.fixture(scope='module', autouse=True)
def show_sys_version(engines):
    """
    For regression analysis, show the system info (and version) before each test case/file
    """
    with allure.step('Before test case: show system info'):
        system = System()
        if isinstance(TestToolkit.devices.dut, EthSwitch):  # temporary, needed until nv unification RM 3735390.
            attachment = '\n'.join(
                [system.show(), engines.dut.run_cmd('cat /etc/image-release'), NvueGeneralCli.show_config(engines.dut)])
        else:
            attachment = '\n'.join([system.show(), system.version.show(), NvueGeneralCli.show_config(engines.dut)])
        allure.orig_allure.attach(attachment, 'system_version_and_conf', allure.orig_allure.attachment_type.TEXT)


@pytest.fixture(scope='function')
def local_adminuser(engines, devices) -> UserInfo:
    adminrole = devices.dut.aaa_admin_role
    adminuser = UserInfo(username=AaaConsts.LOCALADMIN, password=generate_strong_password(), role=adminrole)
    logging.info(f'Local admin user for test: "{adminuser.username}", "{adminuser.password}"')
    set_local_users(engines, [adminuser], apply=True)
    return adminuser


@pytest.fixture(scope='session', autouse=False)
def prepare_scp(engines):
    """
    @summary: Upload a dummy text file to the switch, that will be used in tests for scp verification
    """
    admin_monitor_mutual_group = 'adm'
    # admins_group = 'admin'

    logging.info('Prepare directory for admin users only')
    engines.dut.run_cmd(f'mkdir -p {AuthConsts.SWITCH_SCP_TEST_DIR}')
    engines.dut.run_cmd(f'mkdir -p {AuthConsts.SWITCH_ADMINS_DIR}')
    # engines.dut.run_cmd(f'chgrp {admins_group} {AuthConsts.SWITCH_ADMINS_DIR}')
    engines.dut.run_cmd(f'chmod 770 {AuthConsts.SWITCH_ADMINS_DIR}')
    engines.dut.run_cmd(f'echo "Alon The King" > {AuthConsts.SWITCH_ADMIN_SCP_DOWNLOAD_TEST_FILE}')
    # engines.dut.run_cmd(f'chgrp {admins_group} {AuthConsts.SWITCH_ADMIN_SCP_DOWNLOAD_TEST_FILE}')
    engines.dut.run_cmd(f'chmod 770 {AuthConsts.SWITCH_ADMIN_SCP_DOWNLOAD_TEST_FILE}')

    logging.info('Prepare non-privileged directory')
    engines.dut.run_cmd(f'mkdir -p {AuthConsts.SWITCH_MONITORS_DIR}')
    engines.dut.run_cmd(f'chgrp {admin_monitor_mutual_group} {AuthConsts.SWITCH_MONITORS_DIR}')
    engines.dut.run_cmd(f'chmod 770 {AuthConsts.SWITCH_MONITORS_DIR}')
    engines.dut.run_cmd(f'echo "Alon The King" > {AuthConsts.SWITCH_MONITOR_SCP_DOWNLOAD_TEST_FILE}')
    engines.dut.run_cmd(f'chgrp {admin_monitor_mutual_group} {AuthConsts.SWITCH_MONITOR_SCP_DOWNLOAD_TEST_FILE}')
    engines.dut.run_cmd(f'chmod 770 {AuthConsts.SWITCH_MONITOR_SCP_DOWNLOAD_TEST_FILE}')

    yield

    logging.info('Clean scp test files')
    engines.dut.run_cmd(f'rm -rf {AuthConsts.SWITCH_SCP_TEST_DIR}')


@pytest.fixture(scope='session')
def switch_hostname(engines):
    return OutputParsingTool.parse_json_str_to_dictionary(System().show()).get_returned_value()[SystemConsts.HOSTNAME]

# @pytest.fixture(scope='function')
# def disable_remote_auth_after_test(engines):
#     """
#     @summary: disable remote authentication after test
#         * aaa tests should update SecurityTestToolKit.active_remote_server each time configuring a remote server.
#     """
#     yield
#
#     active_remote_server = SecurityTestToolKit.active_remote_server
#     if not active_remote_server:
#         return
#
#     active_admin_user = [user for user in active_remote_server.users if user.role == AaaConsts.ADMIN][0]
#     orig_username, orig_password = engines.dut.username, engines.dut.password
#     engines.dut.update_credentials(username=active_admin_user.username, password=active_admin_user.password)
#
#     System().aaa.unset(apply=True)
#     if isinstance(active_remote_server, LdapServerInfo):
#         DutUtilsTool.wait_for_nvos_to_become_functional(TestToolkit.engines.dut).verify_result()
#
#     engines.dut.update_credentials(username=orig_username, password=orig_password)
#
#     TestToolkit.active_remote_auth_server = None

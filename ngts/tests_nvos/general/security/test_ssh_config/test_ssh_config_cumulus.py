import logging
import random
import re
import time

import pexpect
import pytest

from infra.tools.general_constants.constants import DefaultConnectionValues
from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.PexpectTool import PexpectTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.SshCmdBuilder import SshCmdBuilder
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.conftest import create_ssh_login_engine, \
    ssh_to_device_and_retrieve_raw_login_ssh_notification
from ngts.tests_nvos.general.security.test_login_ssh_notification.constants import LoginSSHNotificationConsts
from ngts.tests_nvos.general.security.test_ssh_config.constants import SshConfigConsts
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger(__name__)


@pytest.mark.ssh_config
@pytest.mark.cumulus_only
def test_denied_user(engines, devices):
    """
    Name:
    ============
    test_05_denied_user

    Description:
    ============
    Verify ssh connection is not established with user-id configured through cli in deny users.

    Steps:
    ============
        1) Configure ssh options to not allow connections with only specific user-ids

        2) Verify that these user-ids are unable to establish connections while others are allowed.
    """

    with allure.step("Creating a new username"):
        system = System()

        user_name, password = system.aaa.user.set_new_user(role='nvue-monitor', apply=True)

    with allure.step(f"Configuring deny users"):
        system.ssh_server.set(SshConfigConsts.DENY_USERS, user_name, apply=True, ask_for_confirmation='-y').verify_result()
        time.sleep(3)

        with allure.step("Failing to Connect {} times to get logged out of session".format(1)):
            try:
                _ssh_command = SshCmdBuilder(user_name, engines.dut.ip, SshConfigConsts.DEFAULT_PORT).set_ssn().set_num_password_prompts(1).build()
                connection = PexpectTool(_ssh_command)
                connection.expect('[Pp]assword[:?]')
                connection.sendline(password)
                connection.expect('Permission denied')
            finally:
                # connection.close()
                pass

    with allure.step(f"Remove deny users configuration"):
        system.ssh_server.deny_user.unset(user_name, apply=True, ask_for_confirmation='-y').verify_result()
        time.sleep(3)

        with allure.step(f"Verify that the user is able to establish connections"):
            ssh_to_device_and_retrieve_raw_login_ssh_notification(engines.dut.ip, username=user_name, password=password)


@pytest.mark.ssh_config
@pytest.mark.cumulus_only
def test_allowed_and_denied_users(engines, devices):
    """
    Name:
    ============
    test_allowed_and_denied_users

    Description:
        ============
        Verify that combination of allow and deny users work

        Steps:
        ============
            1) Configure ssh options with allow and deny users both

            2) Verify that combination of allow and deny users work

            3) Verify that only the users which satisfy both the criterias are allowed
        """

    with allure.step("Creating a new users"):
        system = System()
        denied_user, denied_password = system.aaa.user.set_new_user(role='nvue-monitor', apply=True)
        logging.info(f"User created: \nusername: {denied_user} \npassword: {denied_password}\ncapability: {'nvue-monitor'}")

        allowed_user, allowed_password = system.aaa.user.set_new_user(role='nvue-monitor', apply=True)
        logging.info(f"User created: \nusername: {allowed_user} \npassword: {allowed_password}\ncapability: {'nvue-monitor'}")

    with allure.step(f"Configuring allowed and deny users"):
        system.ssh_server.set(SshConfigConsts.ALLOW_USERS, SshConfigConsts.CUMULUS_USER, apply=True, ask_for_confirmation='-y').verify_result()
        system.ssh_server.set(SshConfigConsts.DENY_USERS, denied_user, apply=True, ask_for_confirmation='-y').verify_result()
        system.ssh_server.set(SshConfigConsts.ALLOW_USERS, allowed_user, apply=True, ask_for_confirmation='-y').verify_result()
        time.sleep(3)

    with allure.step("Failing to Connect {} times to get logged out of session".format(1)):
        try:
            _ssh_command = SshCmdBuilder(denied_user, engines.dut.ip, SshConfigConsts.DEFAULT_PORT).set_ssn().set_num_password_prompts(1).build()
            connection = PexpectTool(_ssh_command)
            connection.expect('[Pp]assword[:?]')
            connection.sendline(denied_password)
            connection.expect('Permission denied')
        finally:
            # connection.close()
            pass

    with allure.step(f"Verify that the allowed user is able to establish connections"):
        ssh_to_device_and_retrieve_raw_login_ssh_notification(engines.dut.ip, username=allowed_user, password=allowed_password)

    with allure.step(f"Remove allow and deny users configuration"):
        system.ssh_server.deny_user.unset(denied_user, apply=True, ask_for_confirmation='-y').verify_result()
        time.sleep(3)
        system.ssh_server.allow_user.unset(allowed_user, apply=True, ask_for_confirmation='-y').verify_result()
        system.ssh_server.allow_user.unset(SshConfigConsts.CUMULUS_USER, apply=True, ask_for_confirmation='-y').verify_result()

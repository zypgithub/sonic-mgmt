import logging
from typing import List

import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.IpTool import IpTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.test_login_ssh_notification.constants import LoginSSHNotificationConsts
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def login_source_ip_addresses(engines) -> List[str]:
    '''
    @summary: extract ip address initiating the ssh connection
    '''
    logger.info("Extract login IP address")
    src_ipv4 = IpTool.get_player_ipv4_addr(engines.dut)
    logger.info(f"Login source IPv4 address is {src_ipv4}")
    src_ipv6 = IpTool.get_player_ipv6_addr(src_ipv4)
    logger.info(f"Login source IPv6 address is {src_ipv6}")
    return [src_ipv4, src_ipv6]


@pytest.fixture(scope='function')
def disable_password_hardening_rules(engines):
    '''
    @summary: disabling password hardening rules for dut
    to able to change password
    '''
    system = System()
    with allure.step("Disabling password hardening rules"):
        logger.info("Disabling password hardening rules")
        system.security.password_hardening.set(SystemConsts.USERNAME_PASSWORD_HARDENING_STATE,
                                               SystemConsts.USER_STATE_DISABLED)
        NvueGeneralCli.apply_config(engines.dut, True)

    yield

    with allure.step('Enabling back password hardening rules'):
        logger.info('Enabling back password hardening rules')
        system.security.password_hardening.set(SystemConsts.USERNAME_PASSWORD_HARDENING_STATE,
                                               SystemConsts.USER_STATE_ENABLED)
        NvueGeneralCli.apply_config(engines.dut, True)


@pytest.fixture(scope='function')
def restore_original_record_period():
    '''
    @summary: reset the login record period param back to default
    '''
    system = System()

    yield

    logger.info("Restoring login-record-period original value")
    system.ssh_server.unset(LoginSSHNotificationConsts.RECORD_PERIOD)


@pytest.fixture(scope='function')
def delete_auth_logs(engines):
    '''
    @summary: will be used to delete all the auth.logs under /var/log/
    '''
    logger.info("Deleting all the auth. logs in the switch")
    engines.dut.run_cmd('sudo rm -f /var/log/auth.log*')

    yield

    logger.info("Deleting all the auth. logs in the switch (after test)")
    engines.dut.run_cmd('sudo rm -f /var/log/auth.log*')

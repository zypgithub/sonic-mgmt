import logging
import random
import pytest
import time

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import PlatformConsts, ApiType
from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tests_nvos.general.security.bmc.bmc_creds.constants import BmcUsers, CURL_AUTHORIZATION_ERR_MSGS
from ngts.tests_nvos.general.security.bmc.bmc_creds.helpers import enable_mctp_pcie_ctrl_service_in_bmc
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.BmcSshEngine import BmcSshEngine
from ngts.nvos_tools.infra.BmcTool import BmcTool
from infra.tools.validations.traffic_validations.ping.send import ping_till_alive

logger = logging.getLogger()
BMC_DEFAULT_KNOWN_PASSWORD = 'ABYX12#14artb'
BMC_ROOT_PASS_MANUAL_CHANGED = 'dummypassword'
AUTHENTICATION_FAILED = 'Authentication failure: unable to connect linux'


@pytest.mark.bmc
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_reset_bmc_password_to_default(engines, topology_obj, test_api):
    """
    1. Reset BMC password.
    2. Login with default.
    3. Change password - try to re-login with default
    4. reset and login with default.
    5. restore to original
    """

    dut: LinuxSshEngine = engines.dut
    platform = Platform()
    root_pass = BmcUsers.root.another_password
    client = CurlTool(server_host=PlatformConsts.BMC_INTERNAL_IP, username=BmcUsers.root.username,
                      password=root_pass)
    with allure.step("get bmc addresses"):
        ip_addresses = BmcTool.get_bmc_ip_addresses(engines, topology_obj)
    bmc_ip_address = ip_addresses["IPv4"]
    try:
        with allure.step("Log into bmc root with default known password"):
            bmc_engine = LinuxSshEngine(ip=bmc_ip_address, username='root', password=root_pass)
            output = bmc_engine.run_cmd('whoami')
            client.change_root_password(password=root_pass, new_password=BMC_ROOT_PASS_MANUAL_CHANGED)
            root_pass = BMC_ROOT_PASS_MANUAL_CHANGED
        with allure.step("Reset BMC Root password"):
            iterations_number = random.randint(1, 20)
            with allure.step(f"Resetting root password {iterations_number} times"):
                for _ in range(iterations_number):
                    platform.bmc_password.action_reset().verify_result()
                    root_pass = PlatformConsts.BMC_DEFAULT_ROOT_PASSWORD_AFTER_RESET_VIA_NOS
                    bmc_engine = LinuxSshEngine(ip=bmc_ip_address, username='root', password=root_pass)
                    output = bmc_engine.run_cmd('whoami')
        with allure.step("login with old bmc password, expected to fail"):
            connection_failed = False
            try:
                bmc_engine = LinuxSshEngine(ip=bmc_ip_address, username='root', password=BmcUsers.root.another_password)
                output = bmc_engine.run_cmd('whoami')
            except Exception as e:
                connection_failed = True
                assert AUTHENTICATION_FAILED in e.args[0], f'Expected to fail to connect with error message that includes {AUTHENTICATION_FAILED}, instead got {e.args[0]}'
            assert connection_failed, 'Connection with password {} was expected to fail, but it passed!'
    finally:
        client = CurlTool(server_host=PlatformConsts.BMC_INTERNAL_IP, username=BmcUsers.root.username,
                          password=root_pass)
        client.change_root_password(password=root_pass)


@pytest.mark.bmc
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_reset_bmc_password_to_default_while_locked_out(engines, topology_obj, test_api):
    '''
    Run the reset command after being temporarily locked out from the BMC due to too many failed connection attempts to root user.
    Expected: The password will reset, and after the temporary block will end (600 sec) you will be able to connect with ‘0penBmcTempPass!’.
    '''
    dut: LinuxSshEngine = engines.dut
    platform = Platform()
    root_pass = BmcUsers.root.another_password
    client = CurlTool(server_host=PlatformConsts.BMC_INTERNAL_IP, username=BmcUsers.root.username,
                      password=root_pass)
    with allure.step("get bmc addresses"):
        ip_addresses = BmcTool.get_bmc_ip_addresses(engines, topology_obj)
    bmc_ip_address = ip_addresses["IPv4"]
    try:
        with allure.step("Log into bmc root with wrong password - 10 times to get locked out"):
            wrong_pass = 'some#wrong#pass'
            for _ in range(3):
                logger.info("Trying to connect with wrong credentials")
                try_to_connect_expecting_failure(bmc_ip_address, wrong_pass, err_msg=f'Connection succeeded with wrong bmc password: {wrong_pass}')

        with allure.step("Reset BMC Root password while locked out"):
            platform.bmc_password.action_reset()
            root_pass = PlatformConsts.BMC_DEFAULT_ROOT_PASSWORD_AFTER_RESET_VIA_NOS
            time.sleep(600)
            bmc_engine = LinuxSshEngine(ip=bmc_ip_address, username='root', password=root_pass)
            output = bmc_engine.run_cmd('whoami')
        with allure.step("login with old bmc password, expected to fail"):
            try_to_connect_expecting_failure(bmc_ip_address, BmcUsers.root.another_password, err_msg=f'Connection succeeded with wrong bmc password: {BmcUsers.root.another_password}')

    finally:
        client = CurlTool(server_host=PlatformConsts.BMC_INTERNAL_IP, username=BmcUsers.root.username,
                          password=root_pass)
        client.change_root_password(password=root_pass)


@pytest.mark.bmc
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_reset_bmc_root_password_while_bmc_down(engines, devices, topology_obj, test_api):
    """
    1. factory reset the BMC
    2. verify bmc admin can login only with default password
    3. run show cmd - triggers bmc user password initialization via TPM
    4. verify bmc admin can login only with TPM password
    """

    dut: LinuxSshEngine = engines.dut
    platform = Platform()
    root_password = BmcUsers.root.another_password
    bmc_password_restored = False
    with allure.step("get bmc addresses"):
        ip_addresses = BmcTool.get_bmc_ip_addresses(engines, topology_obj)
    bmc_ip_address = ip_addresses["IPv4"]
    try:

        with allure.step('factory reset the bmc'):
            client = CurlTool(server_host=PlatformConsts.BMC_INTERNAL_IP, username=BmcUsers.root.username,
                              password=BmcUsers.root.another_password)
            client.change_root_password(password=BmcUsers.root.default_password)
            root_password = BmcUsers.root.default_password
            client.reset_bmc_to_factory()

            with allure.independent_step("Wait for BMC to boot after factory reset"):
                with allure.step("Try To reset bmc root password while BMC is down"):
                    output = platform.bmc_password.action_reset().verify_result(should_succeed=False)
                    failed_to_connect_err = "Failed to reset password: Can't connect to BMC"
                    assert failed_to_connect_err in output, f'output expected to contain {failed_to_connect_err}, but instead got {output}'
                with allure.step('Ping BMC until back alive'):
                    time.sleep(15)
                    output = engines.sonic_mgmt.run_cmd(f"timeout 3 telnet {bmc_ip_address} 22")
                    while "Connected to" not in output:
                        output = engines.sonic_mgmt.run_cmd(f"timeout 3 telnet {bmc_ip_address} 22")
                    logger.info("Wait for 30 seconds before trying to reset bmc root password")
                    time.sleep(30)

            with allure.step("Reset BMC Password to default - using nvos command"):
                output = platform.bmc_password.action_reset().verify_result()
                root_password = PlatformConsts.BMC_DEFAULT_ROOT_PASSWORD_AFTER_RESET_VIA_NOS
                logger.info("Verify login is available with default bmc password for reset bmc root password")
                bmc_engine = LinuxSshEngine(ip=bmc_ip_address, username='root', password=root_password)
                output = bmc_engine.run_cmd('whoami')

            client.change_root_password(password=root_password)
            bmc_password_restored = True

    finally:
        if not bmc_password_restored:
            client.change_root_password(password=root_password)


def try_to_connect_expecting_failure(bmc_ip_address, password, err_msg):
    connection_failed = False
    try:
        bmc_engine = LinuxSshEngine(ip=bmc_ip_address, username='root', password=password)
        output = bmc_engine.run_cmd('whoami')
    except Exception as e:
        connection_failed = True
    assert connection_failed, f'{err_msg}'

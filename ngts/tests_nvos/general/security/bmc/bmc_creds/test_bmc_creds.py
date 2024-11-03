import logging

import pytest

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tests_nvos.general.security.bmc.bmc_creds.constants import BmcUsers, CURL_AUTHORIZATION_ERR_MSGS
from ngts.tests_nvos.general.security.bmc.bmc_creds.helpers import enable_mctp_pcie_ctrl_service_in_bmc
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.bmc
def test_bmc_creds_flow(engines, devices, topology_obj):
    """
    1. factory reset the BMC
    2. verify bmc admin can login only with default password
    3. run show cmd - triggers bmc user password initialization via TPM
    4. verify bmc admin can login only with TPM password
    """

    def check_auth_with_curl(dut_engine: LinuxSshEngine, username: str, password: str, expect_success: bool):
        curl_cmd = f'curl -k -u {username}:{password} https://10.0.1.1/redfish/v1/AccountService/Accounts'
        out = dut_engine.run_cmd(curl_cmd)
        auth_success = all(err_msg not in out for err_msg in CURL_AUTHORIZATION_ERR_MSGS)
        assert auth_success == expect_success, (f"authorization success result not as expected.\n"
                                                f"expected: {expect_success}\n"
                                                f"actual: {auth_success}\n"
                                                f"curl_cmd: {curl_cmd}\nout:\n{out}")

    dut: LinuxSshEngine = engines.dut

    with allure.step(f'get password for nvos-bmc user "{BmcUsers.admin.username}" from tpm cipher'):
        admin_password_from_tpm = TpmTool(dut).get_bmc_admin_password_from_tpm()
        BmcUsers.admin.another_password = admin_password_from_tpm

    with allure.step('factory reset the bmc'):
        with allure.step("run factory reset to bmc"):
            client = CurlTool(server_host=PlatformConsts.BMC_INTERNAL_IP, username=BmcUsers.root.username,
                              password=BmcUsers.root.another_password)
            client.change_root_password(password=BmcUsers.root.default_password)
            client.reset_bmc_to_factory()  # Causes switch to reboot
            dut.disconnect()
            DutUtilsTool.wait_on_system_reboot(dut, topology_obj=TestToolkit.topology_obj)
            client.change_root_password(password=BmcUsers.root.default_password)

    with allure.step(f'verify bmc user "{BmcUsers.admin.username}" can login only with TPM password'):
        with allure.step(f'curl with user "{BmcUsers.admin.username}" + default password - expect fail'):
            check_auth_with_curl(dut, BmcUsers.admin.username, BmcUsers.admin.default_password, False)
        with allure.step("Run nv command to restore admin password"):
            Platform().firmware.show().verify_result()
        with allure.step(f'curl with user "{BmcUsers.admin.username}" + password from tpm cipher - expect success'):
            check_auth_with_curl(dut, BmcUsers.admin.username, BmcUsers.admin.another_password, True)

    with allure.step('cleanup - after bmc factory reset - enable mctp-pcie-ctrl service'):
        enable_mctp_pcie_ctrl_service_in_bmc(dut)

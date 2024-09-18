import logging

import pytest

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.BmcSshEngine import BmcSshEngine
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.tests_nvos.general.security.bmc.bmc_creds.constants import BmcUsers, CURL_AUTHORIZATION_ERR_MSGS
from ngts.tests_nvos.general.security.bmc.bmc_creds.helpers import bmc_factory_reset, \
    enable_mctp_pcie_ctrl_service_in_bmc
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
        with allure.step(f'ssh to bmc with user "{BmcUsers.root.username}"'):
            bmc_session = BmcSshEngine(dut, BmcUsers.root.username, BmcUsers.root.default_password,
                                       BmcUsers.root.another_password)
        with allure.step("run factory reset to bmc"):
            bmc_factory_reset(bmc_session, dut, topology_obj)

    # NOTE: skipping the part of checking that admin can login only with default, because now the tpm password comes right after init
    # with allure.step(f'verify bmc "{BmcUsers.admin.username}" can login only with default password'):
    #     with allure.step(f'curl with "{BmcUsers.admin.username}" + default password - expect success'):
    #         check_auth_with_curl(dut, BmcUsers.admin.username, BmcUsers.admin.default_password, True)
    #     with allure.step(f'curl with "{BmcUsers.admin.username}" + password from tpm cipher - expect fail'):
    #         check_auth_with_curl(dut, BmcUsers.admin.username, BmcUsers.admin.another_password, False)
    # with allure.step(f'run nv show cmd- triggers bmc user "{BmcUsers.admin.username}" password initialization via TPM'):
    #     DutUtilsTool.wait_for_nvos_to_become_functional(dut).verify_result()

    with allure.step(f'verify bmc user "{BmcUsers.admin.username}" can login only with TPM password'):
        with allure.step(f'curl with user "{BmcUsers.admin.username}" + default password - expect fail'):
            check_auth_with_curl(dut, BmcUsers.admin.username, BmcUsers.admin.default_password, False)
        with allure.step(f'curl with user "{BmcUsers.admin.username}" + password from tpm cipher - expect success'):
            check_auth_with_curl(dut, BmcUsers.admin.username, BmcUsers.admin.another_password, True)

    with allure.step('cleanup - after bmc factory reset - enable mctp-pcie-ctrl service'):
        enable_mctp_pcie_ctrl_service_in_bmc(dut)

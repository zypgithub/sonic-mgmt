"""
CRDT (Debug Image Token) Functionality Test

Test Plan Section 6.2: CRDT Complete Flow - IPN Systems
"""
import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts, HealthConsts, RebootConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.system.test_system_reboot import validate_reboot_reason_and_user
from ngts.tools.test_utils import allure_utils as allure

from .helpers import (
    CRDTTokenManager,
    DebugTokenConsts,
    TokenVerifier,
)
from .token_signing import CRDTTokenSigner


@pytest.mark.timeout(30 * MINUTE)
@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.crdt
@pytest.mark.functionality
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_crdt_complete_flow(engines, devices, nv_command, test_name, test_api,
                            topology_obj, serial_log_analyzers, skip_if_opn_system):
    """
    Test Plan Section 6.2: CRDT Complete Flow with Firmware

    Comprehensive CRDT token lifecycle with firmware operations:
    1. Verify initial state (token disabled)
    2. Fetch debug BIN firmware for token generation
    3. Generate token info from BIN file
    4. Sign token on switch using mlxconfig (private key already copied)
    5. Install CRDT token
    6. Verify token status enabled for all ASICs
    7. Fetch and install MFA firmware (without reboot)
    8. Verify token is still applied after MFA install
    9. Reboot with default firmware
    10. Verify token persistence (token should remain enabled after reboot)
    Cleanup: Factory reset to ensure clean state

    Test Scope: Token signing on switch with BIN/MFA firmware operations and persistence verification
    """
    serial_analyzer, = serial_log_analyzers.values()
    TestToolkit.tested_api = test_api
    manager = CRDTTokenManager()
    system = System()
    debug_fw_bin = DebugTokenConsts.DEBUG_FW_FILENAME

    try:
        with allure.step('Step 1: Verify initial state'):
            token_status = manager.get_token_status()
            assert not token_status.is_enabled, "Token should be disabled initially"
            nv_command.system.validate_health_status(HealthConsts.OK)

        with allure.step('Step 2: Fetch debug BIN firmware for token generation'):
            manager.fetch_debug_fw().verify_result()

        with allure.step('Step 3: Generate CRDT token info from BIN file'):
            token_info_file = DebugTokenConsts.CRDT_TOKEN_INFO
            manager.generate_token_info(token_info_file, test_name, fw_signed_filename=debug_fw_bin)
            manager.verify_files_output(expected_files=[token_info_file])

        with allure.step('Step 4: Sign token on switch'):
            signer = CRDTTokenSigner(engines)
            signed_token_path, signed_token_name = signer.sign_on_switch(token_info_file)

        with allure.step('Step 5: Install signed CRDT token'):
            manager.install_token(signed_token_name).verify_result()

        with allure.step('Step 6: Verify token status ENABLED for all ASICs'):
            TokenVerifier.verify_token_enabled(manager, expected_enabled=True)

        with allure.step('Step 7: Fetch and install MFA firmware'):
            manager.fetch_and_install_mfa_fw(nv_command, engines).verify_result()

        with allure.step('Step 8: Verify token is still applied after MFA install'):
            TokenVerifier.verify_token_enabled(manager, expected_enabled=True)
            nv_command.system.validate_health_status(HealthConsts.OK)

        with allure.step('Step 9: Reboot with default firmware'):
            nv_command.platform.firmware.asic.set(
                PlatformConsts.FW_SOURCE,
                PlatformConsts.FW_SOURCE_DEFAULT,
                apply=True
            )
            NvueGeneralCli.save_config(engines.dut)

            res_obj, duration = OperationTime.save_duration(
                'reboot with default FW', '', test_name,
                nv_command.system.reboot.action_reboot,
                system_is_ready_timeout=PlatformConsts.TIMEOUT_AFTER_FW_INSTALL
            )
            OperationTime.verify_operation_time(duration, 'reboot with default FW').verify_result()
            nv_command.system.validate_health_status(HealthConsts.OK)

        with allure.step('Step 10: Verify token persistence after reboot'):
            TokenVerifier.verify_token_enabled(manager, expected_enabled=True)

    finally:
        # Cleanup: Factory reset to ensure clean state
        with allure.step('Cleanup: Factory reset'):
            with serial_analyzer.stage('Reset-factory'):
                result_obj = system.factory_default.action_reset(
                    operation=devices.dut.reset_factory,
                    param="",
                    topology_obj=topology_obj,
                    test_name=test_name
                )
                result_obj.verify_result()

            TokenVerifier.verify_token_enabled(manager, expected_enabled=False)

            expected_reason, expected_user = devices.dut.reboot_reason_dict[RebootConsts.FACTORY_RESET]
            validate_reboot_reason_and_user(system, expected_reason, expected_user)

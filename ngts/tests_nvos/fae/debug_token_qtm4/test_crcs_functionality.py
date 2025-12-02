"""
CRCS (Customer Support Token) Functionality Test

Test Plan Section 6.1: CRCS Complete Flow - IPN Systems
"""
import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure

from .helpers import (
    CRCSTokenManager,
    DebugTokenConsts,
    TokenVerifier,
)
from .token_signing import CRCSTokenSigner


@pytest.mark.timeout(15 * MINUTE)
@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.crcs
@pytest.mark.functionality
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_crcs_complete_flow(engines, nv_command, test_name, test_api,
                            topology_obj, skip_if_opn_system):
    """
    Test Plan Section 6.1: CRCS Complete Flow

    Complete CRCS token lifecycle:
    1. Verify initial state (disabled)
    2. Generate token info (XML)
    3. Sign token on switch using mlxconfig
    4. Install signed token
    5. Verify status enabled for all ASICs
    6. Uninstall token
    7. Test token re-installation (should fail per test plan)
    8. Test token switching (different token)
    Cleanup: Reboot to clear token
    """
    TestToolkit.tested_api = test_api
    manager = CRCSTokenManager()

    try:
        with allure.step('Step 1: Verify initial token status is disabled'):
            status = manager.get_token_status()
            assert not status.is_enabled, "Token should be disabled initially"

        with allure.step('Step 2: Generate CRCS token info (XML)'):
            token_info_file = DebugTokenConsts.CRCS_TOKEN_INFO
            manager.generate_token_info(token_info_file, test_name)
            manager.verify_files_output(expected_files=[token_info_file])

        with allure.step('Step 3: Sign token on switch using mlxconfig'):
            signer = CRCSTokenSigner(engines)
            signed_token_path, signed_token_name = signer.sign_on_switch(token_info_file)

        with allure.step('Step 4: Install signed CRCS token'):
            manager.install_token(signed_token_name).verify_result()

        with allure.step('Step 5: Verify token status ENABLED for all ASICs'):
            TokenVerifier.verify_token_enabled(manager, expected_enabled=True)

        with allure.step('Step 6: Uninstall CRCS token'):
            manager.uninstall_token()
            TokenVerifier.verify_token_enabled(manager, expected_enabled=False)

        with allure.step('Step 7: Attempt to reinstall same token (expect failure per test plan)'):
            manager.install_token(signed_token_name).verify_result(False)
            TokenVerifier.verify_token_enabled(manager, expected_enabled=False)

        with allure.step('Step 8: Generate and install DIFFERENT token (token switching)'):
            token_info_file_2 = 'crcs_flow_2.xml'
            manager.generate_token_info(token_info_file_2, test_name)

            signed_token_path_2, signed_token_name_2 = signer.sign_on_switch(token_info_file_2)

            manager.install_token(signed_token_name_2).verify_result()
            TokenVerifier.verify_token_enabled(manager, expected_enabled=True)

    finally:
        # Cleanup: Reboot to clear token
        with allure.step('Cleanup: Reboot to clear token'):
            nv_command.system.reboot.action_reboot()

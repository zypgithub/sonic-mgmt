import logging
import pytest
import random

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


def _set_write_protection_via_redfish(engines, bmc_user, bmc_password, enable: bool):
    """
    Set write protection state via Redfish BMC command

    Args:
        engines: Test engines
        bmc_user: BMC username
        bmc_password: BMC password
        enable: True to enable, False to disable

    Returns:
        str: Redfish command response
    """
    state = 'true' if enable else 'false'
    action = 'enable' if enable else 'disable'

    cmd = (
        f"curl -k -u {bmc_user}:{bmc_password} "
        f"-H 'Content-Type: application/json' "
        f"-X PATCH "
        f"-d '{{\"Oem\": {{\"Nvidia\": {{\"HardwareWriteProtectEnable\": {state}}}}}}}' "
        f"https://{PlatformConsts.BMC_INTERNAL_IP}/redfish/v1/Chassis/System_0"
    )
    result = engines.dut.run_cmd(cmd)
    logger.info(f"Redfish {action} response: {result}")
    return result


def _verify_write_protection_state(fae, expected_state: str):
    """
    Verify write protection state via CLI

    Args:
        fae: Fae object
        expected_state: 'enabled' or 'disabled'
    """
    output_dictionary = OutputParsingTool.parse_show_output_to_dict(
        fae.platform.write_protection.show().get_returned_value())
    ValidationTool.verify_field_value_in_output(
        output_dictionary=output_dictionary,
        field_name='write-protection',
        expected_value=expected_state
    ).verify_result()
    logger.info(f"✓ Write protection is {expected_state}")


@pytest.mark.fae
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_platform_write_protection_enabled(engines, test_api):
    """
    Test write protection can be controlled via Redfish and verified via CLI

    Test flow:
        1. Check write protection enabled by default (via CLI)
        2. Disable write protection via Redfish BMC command
        3. Verify disabled via CLI
        4. Finally: Re-enable write protection and verify (cleanup)
    """
    TestToolkit.tested_api = test_api
    fae = Fae()

    # Get BMC admin password from TPM
    bmc_password = TpmTool(engines.dut).get_bmc_admin_password_from_tpm()
    bmc_user = 'admin'

    try:
        with allure.step("1. Verify write protection enabled by default"):
            _verify_write_protection_state(fae, 'enabled')

        with allure.step("2. Disable write protection via Redfish BMC command"):
            _set_write_protection_via_redfish(engines, bmc_user, bmc_password, enable=False)

        with allure.step("3. Verify write protection disabled via CLI"):
            _verify_write_protection_state(fae, 'disabled')

    finally:
        # Cleanup: Always ensure write protection is enabled
        with allure.step("Cleanup: Ensure write protection is enabled"):
            try:
                _set_write_protection_via_redfish(engines, bmc_user, bmc_password, enable=True)
                _verify_write_protection_state(fae, 'enabled')
                logger.info("✓ Cleanup: Write protection confirmed enabled")
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")
                raise

import json
import logging
import pytest

from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()

REDFISH_AUTH_ERROR_INDICATORS = ['ResourceAtUriUnauthorized', 'Invalid username or password', '"error"']


def _set_write_protection_via_redfish(client, enable: bool):
    """
    Set write protection state via Redfish BMC command using CurlTool.
    """
    action = 'enable' if enable else 'disable'
    data = json.dumps({"Oem": {"Nvidia": {"HardwareWriteProtectEnable": enable}}})

    with allure.step(f"Redfish: {action} write protection"):
        result = client.run_redfish_command(rest_op='PATCH', data=data, path='/Chassis/Chassis_0')
        logger.info(f"Redfish {action} response: {result}")

        assert not any(indicator in result for indicator in REDFISH_AUTH_ERROR_INDICATORS), \
            f"Redfish {action} write protection failed. Response:\n{result}"

    return result


def _verify_write_protection_state(fae, expected_state: str):
    """
    Verify write protection state via CLI
    """
    output_dictionary = OutputParsingTool.parse_show_output_to_dict(
        fae.platform.write_protection.show()).get_returned_value()
    ValidationTool.verify_field_value_in_output(
        output_dictionary=output_dictionary,
        field_name='write-protection',
        expected_value=expected_state
    ).verify_result()


@pytest.mark.fae
def test_platform_write_protection_enabled(engines, random_api):
    """
    Test write protection can be controlled via Redfish and verified via CLI

    Test flow:
        1. Check write protection enabled by default (via CLI)
        2. Disable write protection via Redfish BMC command
        3. Verify disabled via CLI
        4. Finally: Re-enable write protection and verify (cleanup)
    """
    fae = Fae()
    dut_engine = TestToolkit.engines.dut

    bmc_password = TpmTool(dut_engine).get_bmc_admin_password_from_tpm()
    client = CurlTool(server_host=PlatformConsts.BMC_INTERNAL_IP,
                      username=PlatformConsts.BMC_LOGIN, password=bmc_password)

    try:
        with allure.step("1. Verify write protection enabled by default"):
            _verify_write_protection_state(fae, 'enabled')

        with allure.step("2. Disable write protection via Redfish BMC command"):
            _set_write_protection_via_redfish(client, enable=False)

        with allure.step("3. Verify write protection disabled via CLI"):
            _verify_write_protection_state(fae, 'disabled')

    finally:
        with allure.step("Cleanup: Ensure write protection is enabled"):
            try:
                _set_write_protection_via_redfish(client, enable=True)
                _verify_write_protection_state(fae, 'enabled')
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")
                raise

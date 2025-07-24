import pytest

from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.DutUtilsTool import RebootParams


@pytest.mark.platform
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_platform_ps_redundancy_check_default_policy_after_reboot(engines, devices, test_api, min_psu_not_available_eth):
    TestToolkit.tested_api = test_api

    if min_psu_not_available_eth:
        with allure.step("Verify testcase applicable for cumulus devices"):
            pytest.skip("Skipping test_platform_ps_redundancy_check_default_policy_after_reboot test on Cumulus devices as PS Redundancy is not supported because MIN_PSU is not available")

    with allure.step("Create Platform object"):
        platform = Platform()

    try:
        output_before_reboot = None
        output_after_reboot = None

        with allure.step("Set platform ps-redundancy to {} and verify in functionality".format(PlatformConsts.PS_REDUNDANCY_PS)):
            platform.ps_redundancy.set(PlatformConsts.PS_REDUNDANCY_POLICY, PlatformConsts.PS_REDUNDANCY_PS, apply=True,
                                       ask_for_confirmation=devices.dut.ask_for_confirmation, dut_engine=engines.dut)

            output_before_reboot = OutputParsingTool.parse_json_str_to_dictionary(platform.ps_redundancy.show()).get_returned_value()

        with allure.step("Reboot DUT"):
            DutUtilsTool.reload(engine=engines.dut, device=devices.dut, command="sudo reboot", confirm=False, reboot_params=RebootParams(should_wait_till_system_ready=True))

        with allure.step("Verify platform ps-redundancy policy is still set to {}".format(PlatformConsts.PS_REDUNDANCY_PS)):
            output_after_reboot = OutputParsingTool.parse_json_str_to_dictionary(platform.ps_redundancy.show()).get_returned_value()

        with allure.step("compare show outputs"):
            platform_ps_redundancy_check(output_before_reboot, output_after_reboot)

    finally:
        with allure.step('Run unset platform ps-redundancy command and apply config'):
            platform.ps_redundancy.unset(apply=True, ask_for_confirmation=TestToolkit.devices.dut.ask_for_confirmation, dut_engine=engines.dut).verify_result()

        with allure.step("Verify platform ps-redundancy policy is set to default policy"):
            output = OutputParsingTool.parse_json_str_to_dictionary(platform.ps_redundancy.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(output, PlatformConsts.PS_REDUNDANCY_POLICY, PlatformConsts.PS_REDUNDANCY_POLICY_TYPE_DEF).verify_result()


@pytest.mark.platform
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_platform_ps_redundancy_unsupported_devices_check(engines, devices, test_api, min_psu_not_available_eth):
    TestToolkit.tested_api = test_api

    if not min_psu_not_available_eth:
        with allure.step("Verify testcase applicable for cumulus devices"):
            pytest.skip("Skipping test_platform_ps_redundancy_unsupported_devices_check test on Cumulus devices as PS Redundancy supported negative scenario")

    with allure.step("Create Platform object"):
        platform = Platform()

    with allure.step("Verify applicable for cumulus devices"):
        with allure.step("Set platform ps-redundancy to {} and verify in functionality".format(PlatformConsts.PS_REDUNDANCY_PS)):
            platform.ps_redundancy.set(PlatformConsts.PS_REDUNDANCY_POLICY, PlatformConsts.PS_REDUNDANCY_PS, ask_for_confirmation=devices.dut.ask_for_confirmation, apply=True, dut_engine=engines.dut).verify_result(should_succeed=False)


def platform_ps_redundancy_check(output_before_reboot, output_after_reboot):
    ps_policy_before_reboot = output_before_reboot[PlatformConsts.PS_REDUNDANCY_POLICY]
    ps_policy_after_reboot = output_after_reboot[PlatformConsts.PS_REDUNDANCY_POLICY]
    ps_min_req_before_reboot = output_before_reboot[PlatformConsts.PS_REDUNDANCY_MIN_REQ]
    ps_min_req_after_reboot = output_after_reboot[PlatformConsts.PS_REDUNDANCY_MIN_REQ]
    with allure.step("Verify platform ps-redundancy policy is still set to {}".format(PlatformConsts.PS_REDUNDANCY_PS)):
        assert ps_policy_before_reboot == ps_policy_after_reboot, "Platform ps-redundancy policy is not the same after reboot"
        assert ps_min_req_before_reboot == ps_min_req_after_reboot, "Min required is not the same after reboot"

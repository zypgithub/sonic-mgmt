import logging
import pytest
import random
import string

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.NvCommand import NvCommand
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

from ngts.nvos_constants.constants_nvos import ApiType, PowerCappingConsts

logger = logging.getLogger()


@pytest.fixture(scope='function', autouse=True)
def enable_power_capping_state():
    platform = NvCommand().platform
    platform.power_capping.set(op_param_name=PowerCappingConsts.STATE,
                               op_param_value=PowerCappingConsts.State.ENABLED.value, apply=True).verify_result()
    yield

    platform.power_capping.unset(op_param=PowerCappingConsts.STATE, apply=True).verify_result()


@pytest.fixture(scope='function')
def cleanup_profiles(engines):
    yield
    platform = NvCommand().platform
    fae = NvCommand().fae

    with allure.step('return to default config after test'):
        NvueGeneralCli.detach_config(engines.dut)
        platform.power_capping.unset_active_profile(apply=True).verify_result()
        fae.platform.power_capping.unset(apply=True).verify_result()


@pytest.mark.platform
@pytest.mark.power_capping
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_platform_power_capping(engines, devices, test_api):
    """
    Test Objective:
    Verify that setting and unsetting power capping profiles works as expected.

    Test Flow:
    1. Set a power capping profile from the list of profiles.
    2. Verify the power capping profile is active and others are inactive.
    3. Verify the active profile using the ASIC power show command.
    4. Unset the power capping profile.
    5. Verify the default power capping profile is active.
    6. Repeat the above steps for all profiles.
    """
    TestToolkit.tested_api = test_api

    with allure.step("Create Platform object"):
        platform = NvCommand().platform

    with allure.step("Test set command for all profiles"):
        for profile_id in PowerCappingConsts.PROFILES:
            with allure.independent_step(f"Set power-capping profile {profile_id}"):
                platform.power_capping.set_active_profile(profile_id, apply=True)

                with allure.independent_step("Verify power-capping profile is active"):
                    profile_show_output = platform.power_capping.show()
                    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
                    ValidationTool.verify_field_value_in_output(output_dictionary, PowerCappingConsts.ACTIVE_PROFILE, profile_id).verify_result()

                with allure.independent_step(f"Verify all fields and values under power-capping profile {profile_id}"):
                    profile_show_output = platform.power_capping.profiles.show()
                    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
                    ValidationTool.compare_dictionaries(output_dictionary, PowerCappingConsts.PROFILES_DEFAULT_DICT)

                with allure.independent_step(f"Verify {profile_id} in platform asic"):
                    _verify_asic_power(devices, platform, profile_id)

            with allure.independent_step(f"Unset active power-capping profile {profile_id}"):
                platform.power_capping.unset_active_profile(apply=True)

            with allure.independent_step("Verify default power-capping profile is active"):
                profile_show_output = platform.power_capping.show()
                output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
                ValidationTool.verify_field_value_in_output(output_dictionary, PowerCappingConsts.ACTIVE_PROFILE, PowerCappingConsts.DEFAULT_PROFILE_ID).verify_result()


@pytest.mark.platform
@pytest.mark.power_capping
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_fae_platform_power_capping_limitation(engines, test_api):
    """
    Test Objective:
    Verify the limitation of creating and activating up to 5 power capping profiles in FAE.

    Test Flow:
    1. Create 5 power capping profiles and activate each one.
    2. Attempt to create a 6th power capping profile and expect failure.
    3. Return to the default power capping profile.
    4. Cleanup by unsetting all newly created profiles.
    """
    TestToolkit.tested_api = test_api
    profiles = [RandomizationTool.get_random_string(8, ascii_letters=string.ascii_letters + string.digits)
                for _ in range(PowerCappingConsts.NUM_PROFILES_LIMIT + 1)]
    limit = PowerCappingConsts.NUM_PROFILES_LIMIT

    with allure.step("Create Fae & Platform object"):
        fae = NvCommand().fae
        platform = NvCommand().platform

    with allure.step(f"Create {limit} power-capping profiles and try to activate"):
        for profile_id in profiles[:limit]:
            set_new_profile(fae, profile_id)
            TestToolkit.GeneralApi[test_api].apply_config(engines.dut, verify_execution=True)
            platform.power_capping.set_active_profile(profile_id, apply=True).verify_result()

    with allure.step(f"Attempt to create a {limit + 1}th power-profile and expect failure"):
        set_new_profile(fae, profile_id)
        output = TestToolkit.GeneralApi[test_api].apply_config(engines.dut)
        assert 'Can not configure active power-profile attributes' in output, "action succeeded while expected to fail"

    with allure.step("Return to default power capping profile"):
        NvueGeneralCli.detach_config(engines.dut)
        platform.power_capping.unset_active_profile(apply=True).verify_result()

    with allure.step("Cleanup - unset all newly created profiles"):
        for profile_id in profiles[:limit]:
            fae.platform.power_capping.profile_id[profile_id].unset().verify_result()

        TestToolkit.GeneralApi[test_api].apply_config(engines.dut, verify_execution=True)


@pytest.mark.platform
@pytest.mark.power_capping
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_fae_platform_power_capping_configurations(engines, test_api):
    """
    Test Objective:
    Verify that updating power capping profile configurations works as expected.

    Test Flow:
    1. Randomly select a non-default profile in FAE.
    2. Set and change every attribute of the profile configurations.
    3. Verify the value has been changed using the show command.
    4. Unset the profile and verify default values are restored.
    """
    TestToolkit.tested_api = test_api
    with allure.step("Create Fae object"):
        fae = NvCommand().fae

    profiles = PowerCappingConsts.PROFILES[:-1]  # Exclude default profile
    random_profile_id = random.choice(profiles)

    # Dictionary to store the attribute values
    attribute_values_dict = {}

    try:
        with allure.step(f"Set and change attributes of profile {random_profile_id}"):
            fae_profile = fae.platform.power_capping.profile_id[random_profile_id]
            attributes_default_output_dict = OutputParsingTool.parse_json_str_to_dictionary(fae_profile.show()).get_returned_value()

            for attribute in PowerCappingConsts.ATTRIBUTES:
                attribute_value = get_random_value(attribute, valid=True)
                attribute_values_dict[attribute] = attribute_value  # Store the value
                fae_profile.set_attribute(attribute, attribute_value)

            TestToolkit.GeneralApi[test_api].apply_config(engines.dut, verify_execution=True)

        with allure.step(f"Verify the values have been changed for profile {random_profile_id}"):
            profile_show_output = fae.platform.power_capping.profile_id[random_profile_id].show()
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()

            for attribute, expected_value in attribute_values_dict.items():
                ValidationTool.verify_field_value_in_output(output_dict, attribute,
                                                            expected_value).verify_result()

    finally:
        with allure.step(f"Unset the {random_profile_id} profile and expect default values"):
            fae.platform.power_capping.unset(random_profile_id, apply=True)
            profile_show_output = fae.platform.power_capping.profile_id[random_profile_id].show()
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
            ValidationTool.compare_dictionaries(attributes_default_output_dict, output_dict).verify_result()


@pytest.mark.platform
@pytest.mark.power_capping
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_power_capping_bad_flow(engines, test_api):
    """
    Test Objective:
    Verify scenarios where invalid operations are performed on power capping profiles.

    Test Flow:
    1. Verify power-capping default profile is active.
    2. Configure attributes for active profile and verify failure during config apply.
    3. Attempt to show a non-existing power capping profile in FAE and verify failure.
    4. Attempt to show a non-existing power capping profile on the platform and verify failure.
    5. Attempt to create a new power capping profile with invalid name and verify failure.
    """

    TestToolkit.tested_api = test_api

    with allure.step("Create Fae and Platform object"):
        fae = NvCommand().fae
        platform = NvCommand().platform

    fae_default_profile = fae.platform.power_capping.profile_id[PowerCappingConsts.DEFAULT_PROFILE_ID]

    with allure.step("Verify power-capping default profile is active"):
        profile_show_output = platform.power_capping.show()
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
        ValidationTool.verify_field_value_in_output(output_dictionary, PowerCappingConsts.ACTIVE_PROFILE, PowerCappingConsts.DEFAULT_PROFILE_ID).verify_result()

    with allure.step(f"Configure attributes for active profile {PowerCappingConsts.DEFAULT_PROFILE_ID}"):
        for attribute in PowerCappingConsts.ATTRIBUTES:
            fae_default_profile.set_attribute(attribute, get_random_value(attribute, valid=True)).verify_result()

        output = TestToolkit.GeneralApi[test_api].apply_config(engines.dut)
        assert 'Can not configure active power-profile attributes' in output, 'operation succeeded while expected to fail'

        NvueGeneralCli.detach_config(engines.dut)

    with allure.step("Show fae platform power-capping for non-existing profile"):
        fae.platform.power_capping.profile_id['non_existing_profile'].show(should_succeed=False)

    with allure.step("Show platform power-capping for non-existing profile"):
        platform.power_capping.profiles.profile_id['non_existing_profile'].show(should_succeed=False)

    with allure.step("Create profile with invalid name"):
        new_name = RandomizationTool.get_random_string(PowerCappingConsts.CHARS_LIMIT + 1, ascii_letters=string.ascii_letters + string.digits)
        fae.platform.power_capping.profile_id[new_name].set_attribute(attribute, 1, apply=True).verify_result(False)


@pytest.mark.platform
@pytest.mark.power_capping
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_power_capping_state_disabled(engines, test_api):
    """
    Test Objective:
    Verify that when power capping state is disabled, the commands are pruned and not accessible.

    Test Flow:
    1. Disable power capping state.
    2. Verify that power capping show command is not accessible.
    3. Verify that power capping profiles show command is not accessible.
    4. Verify that setting active profile command is not accessible.
    5. Re-enable power capping state for cleanup.
    """
    TestToolkit.tested_api = test_api

    with allure.step("Create Platform object"):
        platform = NvCommand().platform

    with allure.step("Disable power capping state and verify pruned commands"):
        platform.power_capping.set(op_param_name=PowerCappingConsts.STATE,
                                   op_param_value=PowerCappingConsts.State.DISABLED.value, apply=True).verify_result()

        with allure.independent_step("Verify power capping profiles show command is pruned when state is disabled"):
            platform.power_capping.profiles.show(should_succeed=False)

        with allure.independent_step("Verify setting active profile command is pruned when state is disabled"):
            platform.power_capping.set_active_profile(PowerCappingConsts.DEFAULT_PROFILE_ID).verify_result(False)

    with allure.step("Re-enable power capping state for cleanup"):
        platform.power_capping.set(op_param_name=PowerCappingConsts.STATE,
                                   op_param_value=PowerCappingConsts.State.ENABLED.value, apply=True).verify_result()


@pytest.mark.platform
@pytest.mark.power_capping
@pytest.mark.skip(reason="Traffic tests are not currently run on mini-oberon")
def test_power_capping(engines):
    """
    Test Objective: Run some stress traffic test on the system and change profile to lower power that the ASIC consumed in the test.

    Test Flow:
    1. Run stress test on the switch in default power-capping profile.
    2. Check ASIC power is as expected and check interface link counters for no degradation.
    3. Change one of the power-capping profiles in FAE to low power limit.
    4. Activate that profile.
    5. Run stress test on the switch with recently configured power-capping profile.
    6. Check ASIC power is as expected and not surpassing the new Power Allocation.
    """
    with allure.step("Create Fae object"):
        fae = NvCommand().fae

    with allure.step("Run stress test on the switch in default power-capping profile"):
        # Code to run stress test
        pass

    with allure.step("Check ASIC power and interface link counters"):
        # Code to check ASIC power and interface link counters
        pass

    with allure.step("Change power-capping profile to low power limit"):
        # Code to change power-capping profile
        pass

    with allure.step("Activate the low power profile"):
        # Code to activate the profile
        pass

    with allure.step("Run stress test on the switch with new power-capping profile"):
        # Code to run stress test
        pass

    with allure.step("Check ASIC power with new power-capping profile"):
        # Code to check ASIC power
        pass


def get_random_value(attribute, valid=True):
    """
    Returns a valid or invalid random value for the given attribute.

    CLI limitations due to https://redmine.mellanox.com/issues/4450070:
    - power-allocation-1/2: [300 - 65535]
    - max-integral-1/2: [0-65535] (uint16)
    - All other attributes: [0-255] (uint8)

    @param attribute: The attribute to get a random value for.
    @param valid: Whether to return a valid or invalid value.
    @return: A random value for the given attribute.
    """
    # Power allocation attributes have range [300 - 65535]
    if attribute in PowerCappingConsts.POWER_ALLOCATION_ATTRIBUTES:
        if valid:
            return random.randint(PowerCappingConsts.POWER_ALLOCATION_MIN, PowerCappingConsts.POWER_ALLOCATION_MAX)
        else:
            # Invalid values: below 300 or above 65535
            return random.choice([random.randint(0, PowerCappingConsts.POWER_ALLOCATION_MIN - 1),
                                  random.randint(PowerCappingConsts.POWER_ALLOCATION_MAX + 1, 100000)])

    # Max integral attributes have range [0-65535] (uint16)
    elif attribute in PowerCappingConsts.MAX_INTEGRAL_ATTRIBUTES:
        if valid:
            return random.randint(PowerCappingConsts.MAX_INTEGRAL_MIN, PowerCappingConsts.MAX_INTEGRAL_MAX)
        else:
            # Invalid values: above 65535
            return random.randint(PowerCappingConsts.MAX_INTEGRAL_MAX + 1, 100000)

    # All other attributes have range [0-255] (uint8)
    else:
        if valid:
            return random.randint(PowerCappingConsts.UINT8_MIN, PowerCappingConsts.UINT8_MAX)
        else:
            # Invalid values: above 255
            return random.randint(PowerCappingConsts.UINT8_MAX + 1, 1000)


def set_new_profile(fae, profile_id, attributes=PowerCappingConsts.ATTRIBUTES):
    fae_profile = fae.platform.power_capping.profile_id[profile_id]
    for attribute in attributes:
        attribute_value = get_random_value(attribute, valid=True)
        fae_profile.set_attribute(attribute, attribute_value)


def _verify_asic_power(devices, platform, profile_id):
    asic_show_output = platform.asic.show()
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(asic_show_output).get_returned_value()
    for asic_name in [f"ASIC{i + 1}" for i in range(devices.dut.asic_amount)]:
        ValidationTool.verify_field_value_in_output(output_dictionary[asic_name], PowerCappingConsts.ACTIVE_PROFILE,
                                                    profile_id).verify_result()

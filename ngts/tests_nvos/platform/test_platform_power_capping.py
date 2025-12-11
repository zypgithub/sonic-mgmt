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
def test_set_fae_platform_power_capping_enum_profiles_activation(engines, random_api):
    """
    Test Objective:
    Verify the creation and activation of enum-based power capping profiles in FAE.

    Test Flow:
    1. Create power capping profiles using enum-based names and activate each one.
    2. Verify each profile is active and present in the profiles list.
    3. Return to the default power capping profile.
    4. Cleanup by unsetting all newly created profiles.
    """
    TestToolkit.tested_api = random_api
    # Use enum-based profile names instead of random strings
    profiles = PowerCappingConsts.ENUM_PROFILES

    with allure.step("Create Fae & Platform object"):
        fae = NvCommand().fae
        platform = NvCommand().platform

    with allure.step(f"Create new power-capping profiles and try to activate"):
        for profile_id in profiles:
            set_new_profile(fae, profile_id)
            TestToolkit.GeneralApi[random_api].apply_config(engines.dut, verify_execution=True)
            platform.power_capping.set_active_profile(profile_id, apply=True).verify_result()

            with allure.independent_step("Verify power-capping profile is active"):
                profile_show_output = platform.power_capping.show()
                output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
                ValidationTool.verify_field_value_in_output(output_dictionary, PowerCappingConsts.ACTIVE_PROFILE, profile_id).verify_result()

            with allure.independent_step("Verify power-capping profile is present in profiles show"):
                profile_show_output = platform.power_capping.profiles.show()
                output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
                ValidationTool.verify_field_value_exist_in_output_dict(output_dictionary, profile_id).verify_result()

    with allure.step("Return to default power capping profile"):
        NvueGeneralCli.detach_config(engines.dut)
        platform.power_capping.unset_active_profile(apply=True).verify_result()

    with allure.step("Cleanup - unset all newly created profiles"):
        for profile_id in profiles:
            fae.platform.power_capping.profile_id[profile_id].unset(apply=True).verify_result()

            with allure.independent_step("Verify power-capping enum profile is returning 'No Data' in show"):
                output = fae.platform.power_capping.profile_id[profile_id].show(should_succeed=False)


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

    # Use enum profiles excluding the default profile
    profiles = [p for p in PowerCappingConsts.PROFILES if p != PowerCappingConsts.DEFAULT_PROFILE_ID]
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
    Validate that invalid operations on power capping profiles are properly rejected and produce expected errors.

    Test Flow:
    1. Confirm the default power-capping profile is active.
    2. Attempt to configure attributes for the active profile and verify that applying the configuration fails as expected.
    3. Attempt to display a non-existent power capping profile in FAE and verify that the operation fails.
    4. Attempt to display a non-existent power capping profile on the platform and verify that the operation fails.
    5. Attempt to create a new power capping profile with an invalid name and verify that the operation fails.
    6. Attempt to apply a profile with incomplete attributes and verify that the operation fails due to missing required properties.
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
        new_name = RandomizationTool.get_random_string(8, ascii_letters=string.ascii_letters + string.digits)
        fae.platform.power_capping.profile_id[new_name].set_attribute(attribute, 1, apply=True).verify_result(False)

    with allure.step("Test incomplete profiles"):
        profile_name = PowerCappingConsts.ENUM_PROFILES[0]
        fae_profile = fae.platform.power_capping.profile_id[profile_name]
        # Pick random attributes (not all required) - between 3-8 attributes
        num_attributes = random.randint(3, 8)
        random_attributes = random.sample(PowerCappingConsts.ATTRIBUTES, num_attributes)
        for attr in random_attributes:
            fae_profile.set_attribute(attr, get_random_value(attr, valid=True))
        output = TestToolkit.GeneralApi[test_api].apply_config(engines.dut, verify_execution=False)
        assert 'is a required property' in output, 'operation succeeded while expected to fail'


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
    Returns a random valid value for the given power capping attribute.

    Uses PowerCappingConsts.ATTRIBUTE_RANGES dictionary for clean lookup.

    SAI firmware constraints based on observed hardware default profiles:
    - Profile 1: power=575/575/475, kp=25, ki=7, kd=0, max_integral=2250, avg=2, pid=2
    - Profile 2: power=450/575/380, kp=50, ki=25, kd=0, max_integral=585, avg=20, pid=4

    @param attribute: The attribute name to generate a value for
    @param valid: If True, returns valid value; if False, returns invalid value (for negative testing)
    @return: Random integer within the attribute's valid range
    """
    if attribute not in PowerCappingConsts.ATTRIBUTE_RANGES:
        logger.warning(f"Attribute '{attribute}' not found in ATTRIBUTE_RANGES, using default uint8 range")
        return random.randint(0, 255) if valid else random.randint(256, 1000)

    range_spec = PowerCappingConsts.ATTRIBUTE_RANGES[attribute]

    if valid:
        return random.randint(range_spec['low'], range_spec['high'])
    else:
        # For invalid values, return either below low or above high
        return random.choice([
            random.randint(0, range_spec['low'] - 1) if range_spec['low'] > 0 else -1,
            random.randint(range_spec['high'] + 1, range_spec['high'] * 2 + 1000)
        ])


def set_new_profile(fae, profile_id, attributes=PowerCappingConsts.ATTRIBUTES):
    """
    Set up a new power capping profile with the given attributes.

    @param fae: FAE object
    @param profile_id: Profile ID (should be a valid enum profile name)
    @param attributes: List of attributes to set
    """
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

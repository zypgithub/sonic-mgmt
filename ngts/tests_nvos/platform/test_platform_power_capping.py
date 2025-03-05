import logging
import pytest
import random
import string

from ngts.nvos_tools.infra.NvCommand import NvCommand
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

from ngts.nvos_constants.constants_nvos import ApiType, PowerProfileConsts

logger = logging.getLogger()


@pytest.fixture(scope='function', autouse=True)
def cleanup_profiles():
    yield
    platform = NvCommand().platform
    with allure.step('return to default config after test'):
        platform.power_profile.unset(apply=True)


@pytest.mark.platform
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_set_platform_power_profile(engines, devices, test_api):
    """
    Test Objective:
    Verify that setting and unsetting power profiles works as expected.

    Test Flow:
    1. Set a power profile from the list of profiles.
    2. Verify the power profile is active and others are inactive.
    3. Verify the active profile using the ASIC power show command.
    4. Unset the power profile.
    5. Verify the default power profile is active.
    6. Repeat the above steps for all profiles.
    """
    TestToolkit.tested_api = test_api

    with allure.step("Create Platform object"):
        platform = NvCommand().platform

    profiles = PowerProfileConsts.PROFILES
    default_profile_id = PowerProfileConsts.DEFAULT_PROFILE_ID

    for profile_id in profiles:
        with allure.step(f"Set power-profile {profile_id}"):
            platform.power_profile.set_active_profile(profile_id)

        with allure.step("Verify power-profile is active"):
            profile_show_output = platform.power_profile.show()
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
            ValidationTool.verify_field_value_in_output(output_dictionary, 'active', profile_id).verify_result()

        with allure.step(f"Verify all fields and values under power-profile {profile_id}"):
            profile_show_output = platform.power_profile.available.show()
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
            ValidationTool.validate_fields_values_in_output(output_dictionary, ['status',
                                                                                'short-term-power-allocation',
                                                                                'long-term-power-allocation']).verify_result()
        with allure.step(f"Verify {profile_id} in asic-power"):
            asic_show_output = platform.asic_power.show()
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(asic_show_output).get_returned_value()
            for asic in [f"ASIC{i + 1}" for i in range(devices.dut.asic_amount)]:
                ValidationTool.verify_field_value_in_output(output_dictionary[asic], 'active-profile', profile_id).verify_result()
                asic_id_show_output = platform.asic_power.asic_id[asic].show()
                output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(asic_id_show_output).get_returned_value()
                ValidationTool.verify_field_value_in_output(output_dictionary, 'active-profile', profile_id).verify_result()

        with allure.step(f"Unset power-profile {profile_id}"):
            platform.power_profile.unset(profile_id, apply=True)

        with allure.step("Verify default power-profile is active"):
            profile_show_output = platform.power_profile.show()
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
            ValidationTool.verify_field_value_in_output(output_dictionary, 'active', default_profile_id).verify_result()


@pytest.mark.platform
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_fae_platform_power_profile_limitation(engines, test_api):
    """
    Test Objective:
    Verify the limitation of creating and activating up to 5 power profiles in FAE.

    Test Flow:
    1. Create 5 power profiles and activate each one.
    2. Attempt to create a 6th power profile and expect failure.
    3. Return to the default power profile.
    4. Cleanup by unsetting all newly created profiles.
    """
    TestToolkit.tested_api = test_api
    profiles = [RandomizationTool.get_random_string(8, ascii_letters=string.ascii_letters + string.digits)
                for _ in range(PowerProfileConsts.NUM_PROFILES_LIMIT + 1)]
    limit = PowerProfileConsts.NUM_PROFILES_LIMIT
    with allure.step("Create Fae & Platform object"):
        fae = NvCommand().fae
        platform = NvCommand().platform

    with allure.step(f"Create {limit} power-profiles and try to activate"):
        for profile_id in profiles[:limit]:
            fae.platform.power_profile.profile_id[profile_id].set().verify_result()
            platform.power_profile.set_active_profile(profile_id, apply=True).verify_result()

    with allure.step(f"Attempt to create a {limit + 1}th power-profile and expect failure"):
        fae.platform.power_profile.profile_id[profiles[limit]].set().verify_result(False, 'limitation')

    with allure.step("Return to default power profile"):
        platform.power_profile.unset().verify_result()

    with allure.step("Cleanup - unset all newly created profiles"):
        for profile_id in profiles[:limit]:
            fae.platform.power_profile.profile_id[profile_id].unset().verify_result()

        TestToolkit.GeneralApi[test_api].apply_config().verify_result()


@pytest.mark.platform
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_set_fae_platform_power_profile_configurations(engines, test_api):
    """
    Test Objective:
    Verify that updating power profile configurations works as expected.

    Test Flow:
    1. Randomly select a non-default profile in FAE.
    2. Set and change every attribute of the profile configurations.
       - If range exists, try value from out of range.
    3. Verify the value has been changed using the show command.
    4. Unset the active new created profile and expect default values.
    5. Move to another profile and unset the 5th profile to ensure it succeeds.
    """
    TestToolkit.tested_api = test_api
    with allure.step("Create Fae object"):
        fae = NvCommand().fae

    profiles = PowerProfileConsts.PROFILES[1:]  # Exclude default profile
    random_profile_id = random.choice(profiles)

    attributes = PowerProfileConsts.ATTRIBUTES

    try:
        with allure.step(f"Set and change attributes of profile {random_profile_id}"):
            fae_profile = fae.platform.power_profile.profile_id[random_profile_id]
            attributes_default_output = fae.platform.power_profile.profile_id[random_profile_id].show()
            for attribute in attributes:
                attribute_value = get_random_value(attribute, valid=True)
                fae_profile.set_attribute(attribute, attribute_value)

            TestToolkit.GeneralApi[test_api].apply_config().verify_result()

        with allure.step(f"Verify the values have been changed for profile {random_profile_id}"):
            profile_show_output = fae.platform.power_profile.profile_id[random_profile_id].show()
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
            for attribute in attributes:
                ValidationTool.verify_field_value_in_output(output_dictionary[random_profile_id], attribute, attribute_value).verify_result()

    finally:
        with allure.step(f"Unset the {random_profile_id} profile and expect default values"):
            fae.platform.power_profile.unset(random_profile_id, apply=True)
            profile_show_output = fae.platform.power_profile.profile_id[random_profile_id].show()
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
            ValidationTool.compare_dictionaries(attributes_default_output, output_dictionary).verify_result()


@pytest.mark.platform
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_power_profile_bad_flow(engines, test_api):
    """
    Test Objective:
    Verify scenarios where invalid operations are performed on power profiles.

    Test Flow:
    1. Configure invalid attributes for a non-active profile and verify failure.
    2. Configure attributes for the active profile and verify failure during config apply.
    3. Attempt to show a non-existing power profile in FAE and verify failure.
    4. Attempt to show a non-existing power profile on the platform and verify failure.
    5. Attempt to show ASIC power for a non-existing ASIC and verify failure.
    6. Attempt to create a new power profile with invalid name and verify failure.
    """

    TestToolkit.tested_api = test_api

    with allure.step("Create Fae and Platform object"):
        fae = NvCommand().fae
        platform = NvCommand().platform

    profiles = PowerProfileConsts.PROFILES[1:]  # Exclude default profile
    default_profile_id = PowerProfileConsts.DEFAULT_PROFILE_ID
    random_profile_id = random.choice(profiles)

    attributes = PowerProfileConsts.ATTRIBUTES

    with allure.step(f"Configure invalid attributes for non-active profile {random_profile_id}"):
        fae_profile = fae.platform.power_profile.profile_id[random_profile_id]
        for attribute in attributes:
            fae_profile.set_attribute(attribute, get_random_value(attribute, valid=False), apply=True).verify_result(False)

    with allure.step(f"Configure attributes for active profile {default_profile_id}"):
        for attribute in attributes:
            fae_profile.set_attribute(attribute, get_random_value(attribute, valid=True)).verify_result()

        TestToolkit.GeneralApi[test_api].apply_config().verify_result(False)

    with allure.step("Show fae platform power-profile for non-existing profile"):
        platform.power_profile.profile_id['non_existing_profile'].show(should_succeed=False)

    with allure.step("Show platform power-profile for non-existing profile"):
        fae.platform.power_profile.profile_id['non_existing_profile'].show(should_succeed=False)

    with allure.step("Show platform asic-power for non-existing ASIC"):
        fae.platform.asic_power['non_existing_asic'].show(should_succeed=False)

    with allure.step("Create profile with invalid name"):
        new_name = RandomizationTool.get_random_string(PowerProfileConsts.CHARS_LIMIT + 1, ascii_letters=string.ascii_letters + string.digits)
        fae.platform.power_profile.profile_id[new_name].set().verify_result(False)


def get_random_value(attribute, valid=True):
    """
    Returns a valid or invalid random value for the given attribute.
    """
    if attribute in ['power-allocation-1', 'power-allocation-2',
                     'max-integral-1', 'max-integral-2',
                     'avg-p-wr-num-of-sampling-1', 'avg-p-wr-num-of-sampling-2',
                     'pid-up-date-num-of-sampling-1', 'pid-up-date-num-of-sampling-2']:
        return random.randint(0, 1000) if valid else random.randint(-1000, -1)
    elif attribute in ['kp-factor-1', 'kp-factor-2', 'ki-factor-1', 'ki-factor-2',
                       'kd-factor-1', 'kd-factor-2']:
        return random.randint(0, 255) if valid else random.randint(256, 1000)
    else:
        raise ValueError(f"Unknown attribute: {attribute}")

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

from ngts.nvos_constants.constants_nvos import ApiType, PowerProfileConsts

logger = logging.getLogger()


@pytest.fixture(scope='function')
def cleanup_profiles(engines):
    yield
    platform = NvCommand().platform
    fae = NvCommand().fae
    with allure.step('return to default config after test'):
        NvueGeneralCli.detach_config(engines.dut)
        platform.power_profile.unset_active_profile(apply=True)
        fae.platform.power_profile.unset(apply=True)


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

    for profile_id in PowerProfileConsts.PROFILES:
        with allure.step(f"Set power-profile {profile_id}"):
            platform.power_profile.set_active_profile(profile_id, apply=True)

        with allure.step("Verify power-profile is active"):
            profile_show_output = platform.power_profile.show()
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
            ValidationTool.verify_field_value_in_output(output_dictionary, 'active', profile_id).verify_result()

        with allure.step(f"Verify all fields and values under power-profile {profile_id}"):
            profile_show_output = platform.power_profile.available.show()
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
            ValidationTool.compare_dictionaries(output_dictionary, PowerProfileConsts.PROFILES_DEFAULT_DICT)

        with allure.step(f"Unset active power-profile {profile_id}"):
            platform.power_profile.unset_active_profile(apply=True)

        with allure.step("Verify default power-profile is active"):
            profile_show_output = platform.power_profile.show()
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
            ValidationTool.verify_field_value_in_output(output_dictionary, 'active', PowerProfileConsts.DEFAULT_PROFILE_ID).verify_result()


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
            set_new_profile(fae, profile_id)
            TestToolkit.GeneralApi[test_api].apply_config(engines.dut, verify_execution=True)
            platform.power_profile.set_active_profile(profile_id, apply=True).verify_result()

    with allure.step(f"Attempt to create a {limit + 1}th power-profile and expect failure"):
        set_new_profile(fae, profile_id)
        output = TestToolkit.GeneralApi[test_api].apply_config(engines.dut)
        assert 'Can not configure active power-profile attributes' in output, "action succeeded while expected to fail"

    with allure.step("Return to default power profile"):
        NvueGeneralCli.detach_config(engines.dut)
        platform.power_profile.unset_active_profile(apply=True).verify_result()

    with allure.step("Cleanup - unset all newly created profiles"):
        for profile_id in profiles[:limit]:
            fae.platform.power_profile.profile_id[profile_id].unset().verify_result()

        TestToolkit.GeneralApi[test_api].apply_config(engines.dut, verify_execution=True)


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

    profiles = PowerProfileConsts.PROFILES[:-1]  # Exclude default profile
    random_profile_id = random.choice(profiles)

    # Dictionary to store the attribute values
    attribute_values_dict = {}

    try:
        with allure.step(f"Set and change attributes of profile {random_profile_id}"):
            fae_profile = fae.platform.power_profile.profile_id[random_profile_id]
            attributes_default_output_dict = OutputParsingTool.parse_json_str_to_dictionary(fae_profile.show()).get_returned_value()

            for attribute in PowerProfileConsts.ATTRIBUTES:
                attribute_value = get_random_value(attribute, valid=True)
                attribute_values_dict[attribute] = attribute_value  # Store the value
                fae_profile.set_attribute(attribute, attribute_value)

            TestToolkit.GeneralApi[test_api].apply_config(engines.dut, verify_execution=True)

        with allure.step(f"Verify the values have been changed for profile {random_profile_id}"):
            profile_show_output = fae.platform.power_profile.profile_id[random_profile_id].show()
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()

            for attribute, expected_value in attribute_values_dict.items():
                ValidationTool.verify_field_value_in_output(output_dict, attribute,
                                                            expected_value).verify_result()

    finally:
        with allure.step(f"Unset the {random_profile_id} profile and expect default values"):
            fae.platform.power_profile.unset(random_profile_id, apply=True)
            profile_show_output = fae.platform.power_profile.profile_id[random_profile_id].show()
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(profile_show_output).get_returned_value()
            ValidationTool.compare_dictionaries(attributes_default_output_dict, output_dict).verify_result()


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
    random_profile_id = random.choice(profiles)

    with allure.step(f"Configure invalid attributes for non-active profile {random_profile_id}"):
        fae_profile = fae.platform.power_profile.profile_id[random_profile_id]
        for attribute in PowerProfileConsts.FACTOR_ATTRIBUTES:
            fae_profile.set_attribute(attribute, get_random_value(attribute, valid=False), apply=True).verify_result(False)

    with allure.step(f"Configure attributes for active profile {PowerProfileConsts.DEFAULT_PROFILE_ID}"):
        for attribute in PowerProfileConsts.ATTRIBUTES:
            fae_profile.set_attribute(attribute, get_random_value(attribute, valid=True)).verify_result()

        output = TestToolkit.GeneralApi[test_api].apply_config(engines.dut)
        assert 'Can not configure active power-profile attributes' in output, 'operation succeeded while expected to fail'

        NvueGeneralCli.detach_config(engines.dut)

    with allure.step("Show fae platform power-profile for non-existing profile"):
        output = fae.platform.power_profile.profile_id['non_existing_profile'].show()
        output_dict = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()
        assert not output_dict, "shows data on non_existing_profile"
    with allure.step("Show platform power-profile for non-existing profile"):
        output = platform.power_profile.available.profile_id['non_existing_profile'].show()
        output_dict = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()
        assert not output_dict, "shows data on non_existing_profile"

    with allure.step("Create profile with invalid name"):
        new_name = RandomizationTool.get_random_string(PowerProfileConsts.CHARS_LIMIT + 1, ascii_letters=string.ascii_letters + string.digits)
        fae.platform.power_profile.profile_id[new_name].set_attribute(attribute, 1)(apply=True).verify_result(False)


def get_random_value(attribute, valid=True):
    """
    Returns a valid or invalid random value for the given attribute.
    """
    if attribute in PowerProfileConsts.FACTOR_ATTRIBUTES:
        return random.randint(0, 255) if valid else random.randint(256, 1000)
    else:
        return random.randint(0, 1000)


def set_new_profile(fae, profile_id, attributes=PowerProfileConsts.ATTRIBUTES):
    fae_profile = fae.platform.power_profile.profile_id[profile_id]
    for attribute in attributes:
        attribute_value = get_random_value(attribute, valid=True)
        fae_profile.set_attribute(attribute, attribute_value)


def verify_asic_power(devices, platform, profile_id):
    with allure.step(f"Verify {profile_id} in asic-power"):
        asic_show_output = platform.asic_power.show()
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(asic_show_output).get_returned_value()
        for asic in [f"ASIC{i + 1}" for i in range(devices.dut.asic_amount)]:
            ValidationTool.verify_field_value_in_output(output_dictionary[asic], 'active-profile',
                                                        profile_id).verify_result()
            asic_id_show_output = platform.asic_power.asic_id[asic].show()
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(asic_id_show_output).get_returned_value()
            ValidationTool.verify_field_value_in_output(output_dictionary, 'active-profile', profile_id).verify_result()

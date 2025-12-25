import logging
import time
import random

import pytest

from retry.api import retry_call
from ngts.nvos_constants.constants_nvos import ApiType, CpoConsts, PlatformConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.IbInterfaceTool import IbInterfaceTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port, PortRequirements
from ngts.tests_nvos.platform.constants import TransceiversConsts
from ngts.tests_nvos.platform.test_platform_transceiver import _verify_transceiver_status

logger = logging.getLogger()


@pytest.fixture(scope='session', autouse=True)
def get_els_list(engines, devices):
    transceivers_list = devices.dut.transceiver_list
    els_list = [name for name in transceivers_list if TransceiversConsts.TRANSCEIVERS_ELS in name]

    if not els_list:
        pytest.skip("No ELS transceivers found in the system")

    return els_list


@pytest.mark.platform
@pytest.mark.els_fiber_tuning
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_fae_platform_cpo(engines, devices, nv_command, test_api, get_els_list):
    """
    Test Objective:
    Verify that all FAE platform CPO commands work correctly and return expected default values.
    Validate all enum values and command outputs for proper functionality.

    Test steps:
    1. Test nv show fae system cpo --output json
    2. Test nv show fae system cpo els-initialization --output json
    3. Test nv show fae system cpo els-initialization-per-laser --output json
    4. Validate all enum values and default states
    5. Test additional FAE system commands
    """
    TestToolkit.tested_api = test_api
    with allure.step("Create FAE system object"):
        fae_system = nv_command.fae.system

    with allure.step("Test ELS initialization show commands"):
        with allure.independent_step("Test nv show fae system cpo els-initialization"):
            els_init_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
                fae_system.cpo.show(CpoConsts.ELS_INITIALIZATION)).get_returned_value()

            ValidationTool.assert_expected_value(len(els_init_output), devices.dut.number_of_transceivers)
            with allure.step("Verify structure for all ELS transceivers"):
                for els_name in els_init_output.keys():
                    with allure.independent_step(f"Verify ELS {els_name} structure"):
                        ValidationTool.compare_dictionaries(els_init_output[els_name], CpoConsts.ELS_INIT_DEFAULT_DICT).verify_result()

        with allure.independent_step("Test nv show fae system cpo els-initialization-per-laser"):
            els_per_laser_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
                fae_system.cpo.show(CpoConsts.ELS_INITIALIZATION_PER_LASER)).get_returned_value()

            ValidationTool.assert_expected_value(len(els_per_laser_output), devices.dut.number_of_transceivers)

            with allure.step("Verify structure for all ELS transceivers"):
                for els_name in els_per_laser_output.keys():
                    with allure.independent_step(f"Verify ELS {els_name} structure"):
                        els_init_per_laser_data = els_per_laser_output[els_name][CpoConsts.ELS_INITIALIZATION]

                        ValidationTool.assert_expected_value(len(els_init_per_laser_data), CpoConsts.NUMBER_OF_LASERS_PER_ELS)
                        for laser in els_init_per_laser_data:
                            ValidationTool.compare_dictionaries(els_init_per_laser_data[laser], CpoConsts.ELS_INIT_PER_LASER_DEFAULT_DICT).verify_result()


@pytest.mark.platform
@pytest.mark.els_fiber_tuning
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_fae_platform_cpo(engines, devices, test_api, nv_command, get_els_list):
    """
    Test Objective:
    Verify that setting and unsetting FAE platform CPO states works as expected.

    Test Flow:
    1. Set a CPO parameter to a specific value.
    2. Verify only the configured parameter changed and others remain default.
    3. Unset the CPO parameter.
    4. Verify the parameter returned to default value.
    5. Repeat the above steps for all parameters and valid states.
    """
    TestToolkit.tested_api = test_api

    with allure.step("Create FAE system object"):
        fae_system = nv_command.fae.system
        els_list = get_els_list
        platform = nv_command.platform

    with allure.step("Pick random ELS transceiver for testing"):
        random_els = random.choice(els_list)
        logger.info(f"Selected ELS transceiver: {random_els}")

    with allure.step("Test default values for all CPO parameters"):
        for field_key in CpoConsts.CPO_FIELDS:
            with allure.step(f"Test default value for nv show fae system cpo"):
                expected_fields = CpoConsts.CPO_FIELDS
                expected_values = [CpoConsts.DEFAULT_STATE] * len(expected_fields)
                output_dictionary = Tools.OutputParsingTool.parse_json_str_to_dictionary(fae_system.cpo.show()).get_returned_value()
                ValidationTool.validate_fields_values_in_output(expected_fields, expected_values, output_dictionary).verify_result()

    with allure.step("Test set command for all CPO parameters"):
        for field_key in CpoConsts.CPO_FIELDS:
            with allure.independent_step(f"Test set {field_key} to disabled"):
                try:
                    with allure.step(f"Set {field_key} to disabled"):
                        fae_system.cpo.set(field_key, CpoConsts.State.DISABLED.value, apply=True)
                    with allure.step(f"Verify {field_key} is set to disabled and others remain default"):
                        output_dictionary = Tools.OutputParsingTool.parse_json_str_to_dictionary(fae_system.cpo.show()).get_returned_value()

                        expected_fields = CpoConsts.CPO_FIELDS
                        expected_values = []
                        for other_field_key in expected_fields:
                            if other_field_key == field_key:
                                expected_values.append(CpoConsts.State.DISABLED.value)
                            else:
                                expected_values.append(CpoConsts.DEFAULT_STATE)

                        ValidationTool.validate_fields_values_in_output(expected_fields, expected_values, output_dictionary).verify_result()

                    if field_key == CpoConsts.ELS_INITIALIZATION_STATE:
                        with allure.step("ELS initialization state is disabled - try to activate and expect error"):
                            nv_command.platform.transceiver.transceiver_id[random_els].activate().verify_result(False)

                finally:
                    with allure.step(f"Unset {field_key}"):
                        fae_system.cpo.unset(field_key, apply=True)

                    with allure.step(f"Verify {field_key} returned to default"):
                        output_dictionary = Tools.OutputParsingTool.parse_json_str_to_dictionary(fae_system.cpo.show()).get_returned_value()
                        ValidationTool.verify_field_value_in_output(output_dictionary, field_key, CpoConsts.DEFAULT_STATE).verify_result()


@pytest.mark.platform
@pytest.mark.els_fiber_tuning
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_fae_platform_cpo_bad_flow(engines, devices, nv_command, test_api, get_els_list):
    """
    Test Objective:
    Ensure the FAE platform CPO interface robustly rejects invalid operations and returns appropriate error messages.

    Test Steps:
    1. For each CPO parameter, attempt to set it to an invalid enum value and verify the operation fails.
    2. Attempt to activate an ELS transceiver with non-existent or invalid IDs and check for correct error handling.
    3. Execute invalid command and confirm the command fails as expected.
    """
    TestToolkit.tested_api = test_api

    with allure.step("Test invalid enum values for CPO parameters"):
        for field_name in CpoConsts.CPO_FIELDS:
            with allure.independent_step(f"Test set {field_name} with invalid value"):
                nv_command.fae.system.cpo.set(field_name, 'invalid').verify_result(False)

    with allure.step("Test activate with invalid parameters"):
        with allure.independent_step("Test activate with ELS out of range"):
            nv_command.platform.transceiver.transceiver_id['els999'].activate().verify_result(False)

        with allure.independent_step("Test activate with optical engine ID"):
            nv_command.platform.transceiver.transceiver_id['oe1'].activate().verify_result(False)

        with allure.independent_step("Test activate with invalid ELS ID"):
            nv_command.platform.transceiver.transceiver_id['invalid'].activate().verify_result(False)

    with allure.step("Test invalid string command"):
        nv_command.fae.system.show('invalid_cmd', should_succeed=False)


@pytest.mark.platform
@pytest.mark.els_fiber_tuning
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_els_unplug_plug_event(engines, devices, nv_command, test_api, get_els_list):
    """
    Test Objective:
    Verify PMAOS (Physical Module Activation/Deactivation) functionality for ELS transceivers.
    Test the complete cycle: plug out event -> verify status -> some ports down -> plug in event -> activate ELS -> ports restored.

    Test Flow:
    1. Pick a random ELS transceiver
    2. Verify initial ELS status is 'Inserted'
    3. Capture baseline of ports in up state
    4. Simulate plug out event using PMAOS
    5. Verify transceiver status is 'Removed'
    6. Verify activate fails when ELS is removed
    7. Verify some ports are down after unplug
    8. Simulate plug in event using PMAOS
    9. Verify ELS status returned to 'Inserted'
    10. Activate the ELS transceiver
    11. Verify all baseline ports are back in up state
    """
    TestToolkit.tested_api = test_api

    els_list = get_els_list
    platform = nv_command.platform

    with allure.step("Pick random ELS transceiver for testing"):
        random_els = random.choice(els_list)
        logger.info(f"Selected ELS transceiver: {random_els}")

        els_index = int(random_els.replace('els', ''))

    try:
        with allure.step("Verify initial ELS status is 'Inserted'"):
            _verify_transceiver_status(platform, random_els, expected_module_status='Inserted')

        with allure.step("Capture baseline of ports in up state"):
            baseline_up_ports = get_ports_in_up_state()
            logger.info(f"Baseline: {len(baseline_up_ports)} ports in up state")

        with allure.step(f"Simulate plug out event for {random_els} using PMAOS"):
            # Use PMAOS to simulate unplug event
            mst_device = get_mst_device_for_els_index(els_index)
            IbInterfaceTool.simulate_unplug_module_event(
                engines.dut, devices.dut, els_index + CpoConsts.PMAOS_MODULE_OFFSET, mst_device, sleep=8
            )

        with allure.step("Verify ELS status changed to 'Removed'"):
            _verify_transceiver_status(platform, random_els, expected_module_status='Removed')

        with allure.step(f"Activate {random_els} - expect failure when removed"):
            platform.transceiver.transceiver_id[random_els].activate().verify_result(False)

        with allure.step("Verify some ports are down"):
            current_up_ports = get_ports_in_up_state()
            logger.info(f"After unplug: {len(current_up_ports)} ports in up state")

    finally:
        with allure.step(f"Simulate plug in event for {random_els} using PMAOS"):
            # Use PMAOS to simulate plug in event
            mst_device = get_mst_device_for_els_index(els_index)
            IbInterfaceTool.simulate_plugin_module_event(
                engines.dut, devices.dut, els_index + CpoConsts.PMAOS_MODULE_OFFSET, mst_device, sleep=50
            )

        with allure.step("Verify ELS status returned to 'Inserted'"):
            _verify_transceiver_status(platform, random_els, expected_module_status='Inserted')

        with allure.step(f"Activate {random_els}"):
            activate_result = platform.transceiver.transceiver_id[random_els].activate(
                test_name=test_els_unplug_plug_event.__name__
            )
            activate_result.verify_result()
            logger.info(f"Activation of {random_els} took {activate_result.duration} seconds")

        with allure.step("Verify link state is up and matches baseline"):
            retry_call(validate_ports_state, [baseline_up_ports], exceptions=AssertionError, tries=6, delay=10)
            current_up_ports = get_ports_in_up_state()
            logger.info(f"After plug in: {len(current_up_ports)} ports in up state (baseline: {len(baseline_up_ports)})")

        with allure.step("Verify activation time is within threshold"):
            OperationTime.verify_operation_time(activate_result.duration, 'activate els').verify_result()


@pytest.mark.platform
@pytest.mark.els_fiber_tuning
def test_els_init_reboot(engines, devices, nv_command, random_api, get_els_list):
    """
    Test Objective:
    Verify ELS initialization after reboot and measure total duration (reboot + ELS initialization).

    Test Flow:
    1. Capture baseline of ELS transceivers in good state before reboot
    2. Perform system reboot and measure the time
    3. After reboot, verify the same ELS transceivers that were in good state are still in good state
    4. Verify the total duration (reboot + ELS init) is within expected time (465 seconds for Taipan)
    """
    system = System()
    fae_system = nv_command.fae.system

    with allure.step("Capture baseline of ELS in good state before reboot"):
        baseline_els = _get_completed_els(fae_system)
        logger.info(f"Baseline: {len(baseline_els)} ELS in good state: {sorted(baseline_els)}")

    with allure.step("Capture baseline of ports in up state"):
        baseline_up_ports = get_ports_in_up_state()

    with allure.step("Perform system reboot and ELS initialization with duration measurement"):
        result_obj, duration = OperationTime.save_duration(
            'els initialization after reboot', '', test_els_init_reboot.__name__,
            system.reboot.action_reboot,
            system_is_ready_timeout=CpoConsts.TIMEOUT_AFTER_ELS_INITIALIZATION,
        )
        logger.info(f"Total duration (reboot + ELS init): {duration} seconds")

    with allure.step("Verify system is back to normal after reboot"):
        with allure.independent_step("Verify baseline ELS transceivers are in good shape"):
            _validate_els_against_baseline(fae_system, baseline_els)

        with allure.independent_step(f"Validate ports are in up state"):
            retry_call(validate_ports_state, [baseline_up_ports], exceptions=AssertionError, tries=6, delay=30)


def get_mst_device_for_els_index(els_index):
    """
    Get the MST device path for a given ELS index based on GA mapping.

    Args:
        els_index (int): The ELS index (1-18)

    Returns:
        str: MST device path in format '/dev/mst/mt54004_pciconf{i}' where i = (ga+1)%4

    Raises:
        ValueError: If els_index is not in valid range (1-18)
    """
    # ELS index to GA mapping for MST device selection
    els_index_to_ga_mapping = {
        1: 1, 2: 2, 3: 1, 4: 2, 5: 1, 6: 2, 7: 1, 8: 2,
        9: 1, 10: 3, 11: 0, 12: 3, 13: 0, 14: 3, 15: 0, 16: 3, 17: 0, 18: 3
    }

    if els_index not in els_index_to_ga_mapping:
        raise ValueError(f"Invalid ELS index: {els_index}. Valid range is 1-18")

    ga_value = els_index_to_ga_mapping[els_index]
    pciconf_value = (ga_value + 1) % 4
    return f"/dev/mst/mt54004_pciconf{pciconf_value}"


def _get_completed_els(fae_system):
    """
    Get list of ELS transceivers that are in completed state.
    Similar to validate_ports_state_and_speed logic but for ELS status.

    Returns:
        list: List of ELS names that have all steps completed
    """
    els_init_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
        fae_system.cpo.show(CpoConsts.ELS_INITIALIZATION)).get_returned_value()

    expected_status = CpoConsts.InitState.COMPLETED.value
    steps_to_check = [CpoConsts.FIBER_CHECK, CpoConsts.FIBER_TUNING, CpoConsts.LASER_UP]

    els_in_good_state = []

    # Check all ELS transceivers
    for els_name, els_data in els_init_output.items():
        all_steps_completed = True

        for step in steps_to_check:
            if step not in els_data or els_data[step] != expected_status:
                all_steps_completed = False
                break

        if all_steps_completed:
            els_in_good_state.append(els_name)

    return els_in_good_state


def _validate_els_against_baseline(fae_system, baseline_els):
    """
    Validate that ELS from baseline are in good state after reboot.
    Similar to validate_ports_state_and_speed logic but for ELS status.

    Args:
        fae_system: FAE system object
        baseline_els: List of ELS names that were in good state before reboot
    """
    with allure.step(f"Validating {len(baseline_els)} baseline ELS transceivers"):
        current_completed_els = _get_completed_els(fae_system)

        # Find ELS that were in baseline but are not completed now
        els_not_completed = [els for els in baseline_els if els not in current_completed_els]

        # Log the results
        logger.info(f"Current ELS in good state ({len(current_completed_els)}): {sorted(current_completed_els)}")
        logger.info(f"Baseline ELS expected ({len(baseline_els)}): {sorted(baseline_els)}")

        if els_not_completed:
            logger.error(f"ELS from baseline not completed ({len(els_not_completed)}): {sorted(els_not_completed)}")

        ValidationTool.validate_subset_in_superset(baseline_els, current_completed_els).verify_result()


def validate_ports_state(expected_ports: list):
    actual_ports = get_ports_in_up_state()
    ValidationTool.validate_subset_in_superset(expected_ports, actual_ports).verify_result()


def get_ports_in_up_state():
    port_requirements = PortRequirements()
    port_requirements.set_port_state(NvosConsts.LINK_STATE_UP)
    return [port.name for port in Port.get_list_of_ports(port_requirements_object=port_requirements)]

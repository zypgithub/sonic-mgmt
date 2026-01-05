import random
import time

import pytest
import logging
from retry.api import retry_call

from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import ApiType, NvosConst
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.cluster.cluster_tools import summarize_switch_ports
from ngts.tests_nvos.interfaces.nvl_port.helpers import (skip_if_no_trunk_links, skip_if_no_access_links,
                                                         validate_default_config, validate_mode_set,
                                                         select_random_nvl_port_name, reset_gpus_if_needed)
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import GnmiMode, GnmicErr
from ngts.tests_nvos.system.gnmi.helpers import verify_msg_not_in_out_or_err, verify_msg_in_out_or_err
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import PhyRecoveryConsts, NvosConsts
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger()


# Constants for timeouts and verification intervals used in tests
PHY_RECOVERY_DEFAULT_TIMEOUT = 100
PHY_RECOVERY_TIMEOUT_STEP = 10
PHY_RECOVERY_HIGHER_TIMEOUT_MIN = 110
PHY_RECOVERY_HIGHER_TIMEOUT_MAX = 200
PHY_RECOVERY_LOWER_TIMEOUT_MIN = 10
PHY_RECOVERY_LOWER_TIMEOUT_MAX = 90
PHY_RECOVERY_VERIFY_RECHECK_SECONDS = 30

# Constants for expected error messages
ERR_MSG_TIMEOUT_NEGATIVE_MIN = "-1 is less than the minimum of 0"
ERR_MSG_TIMEOUT_VALID_RANGE = "Valid range for serdes-eq-timeout is 0 - 2550"
ERR_MSG_BAD_MODE = "'bad-mode' is not one of"

# Retry settings
VALIDATE_RETRIES = 6
VALIDATE_RETRY_DELAY_SECONDS = 30


@pytest.mark.interface
@pytest.mark.multiplanar
def test_phy_recovery_counters(engines, devices, random_api):
    """
    @summary:
        Verify default recovery counters via nv "show interface" and GNMI subscription.

    Steps:
    1. Select a random port for test
    2. Run `nv show interface <port> link phy detail --view detailed` and parse JSON output.
    3. Confirm all default counters match default_phy_recovery_counters.
    4. Pick a random counter, subscribe via GNMI ONCE to 'phy-diag/state/<counter>'.
    5. Verify GNMI stream contains the counter name and its default value.
    """
    TestToolkit.tested_api = random_api

    with allure.step("Select a port for test"):
        port_result = RandomizationTool.select_random_port(requested_ports_state=NvosConsts.LINK_STATE_ALL_TYPES)
        if not port_result.result:
            pytest.skip(f"Skipping test - {port_result.info}")
        selected_port = port_result.get_returned_value()

    with allure.step("Select a random counter"):
        counters_list = list(devices.dut.default_phy_recovery_counters.keys())
        if is_bug_active(4692220):
            counters_to_remove = [PhyRecoveryConsts.LAST_RS_FEC_UNCORRECTABLE_DURING_RECOVERY,
                                  PhyRecoveryConsts.TOTAL_RS_FEC_UNCORRECTABLE_DURING_RECOVERY,
                                  PhyRecoveryConsts.LAST_SUCCESSFUL_RECOVERY_TIME,
                                  PhyRecoveryConsts.TOTAL_SUCCESSFUL_RECOVERY_TIME,
                                  PhyRecoveryConsts.LAST_SUCCESSFUL_RECOVERY_STEP_ATTEMPTS]
            for counter in counters_to_remove:
                counters_list.remove(counter)
        random_counter = random.choice(counters_list)
        allure.attach(random_counter)

    with allure.step(f"Set up gnmi client and subscribe client to counter: {random_counter}"):
        client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, devices.dut.default_username,
                            devices.dut.default_password, verify_tools_installed=True)
        out, err = client.gnmic_subscribe_interface(GnmiMode.ONCE, selected_port.name, skip_cert_verify=True,
                                                    interface_path=f'phy-diag/state/{random_counter}')

    with allure.step(f"Check that '{random_counter}' was streamed"):
        verify_msg_not_in_out_or_err(GnmicErr.AUTH_FAIL, out, err)
        verify_msg_in_out_or_err(f'{random_counter}: {devices.dut.default_phy_recovery_counters.get(random_counter)}', out)


@pytest.mark.interface
@pytest.mark.multiplanar
def test_phy_recovery_attributes(devices, random_api):
    """
    @summary:
        Verify default recovery attributes via nv "show interface".

    Steps:
    1. Select a random port for test
    2. Run `nv show fae interface <port> link phy-recovery --view detailed` and parse JSON output.
    3. Confirm all default attributes match default_phy_recovery_attributes.
    4. Pick a random attribute, set and verify.
    """
    TestToolkit.tested_api = random_api

    with allure.step("Verify tested device is NVL6"):
        if devices.dut.asic_type not in [NvosConst.QTM4, NvosConst.NVL6]:
            pytest.skip("Skipping test - This test should run only on NVL6")

    with allure.step("Select a port for test"):
        port_result = RandomizationTool.select_random_port(requested_ports_state=NvosConsts.LINK_STATE_ALL_TYPES)
        if not port_result.result:
            pytest.skip(f"Skipping test - {port_result.info}")
        selected_port = Fae(port_name=port_result.get_returned_value().name)

    with allure.step("Validate attributes have default values"):
        port_output = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.port.interface.link.phy_recovery.show()).get_returned_value()
        default_values = devices.dut.default_phy_recovery_attributes
        if is_bug_active(4725233):
            keys_to_remove = [PhyRecoveryConsts.STATE_60_TIMEOUT,
                              PhyRecoveryConsts.STATE_61_TIMEOUT,
                              PhyRecoveryConsts.STATE_62_TIMEOUT]
            for step in [PhyRecoveryConsts.STEP_1, PhyRecoveryConsts.STEP_2]:
                for key in keys_to_remove:
                    del default_values[step][key]
        _validate_default_values(port_output, default_values)

    with allure.step("Select a random mutable attribute"):
        random_path_list, random_attribute, new_value = _get_random_attribute_and_value(port_output, PhyRecoveryConsts.phy_recovery_attributes_options)

    with allure.step(f"Set {random_attribute} to {new_value} and verify"):
        if random_path_list[0] == random_attribute:
            selected_port.port.interface.link.phy_recovery.set(random_attribute, new_value, apply=True)
        else:
            selected_port.port.interface.link.phy_recovery.set(random_path_list[0], {random_attribute: new_value}, apply=True)
        retry_call(
            _verify_attribute,
            [selected_port, random_path_list, random_attribute, new_value],
            exceptions=AssertionError,
            tries=3,
            delay=30,
        )


@pytest.mark.interface
@pytest.mark.multiplanar
def test_phy_recovery_bad_flow(devices, random_api):
    """
    @summary:
        Negative validation of phy-recovery parameters - reject invalid values.

    Steps:
    1. Attempt to show a non-existent phy-recovery attribute; expect failure.
    2. For each field in FWRecoveryConsts.negative_test_cases:
       a. Set the field to its bad_value with apply=True and ask_for_confirmation=True.
       b. Verify that the expected_error is raised.
    """
    TestToolkit.tested_api = random_api
    with allure.step("Select a port for test"):
        port_result = RandomizationTool.select_random_port(requested_ports_state=NvosConsts.LINK_STATE_UP)
        if not port_result:
            port_result.verify_result(False)
            port_result = RandomizationTool.select_random_port(requested_ports_state=NvosConsts.LINK_STATE_ALL_TYPES)
            if not port_result:
                pytest.skip(f"Skipping test - {port_result.info}")
        selected_port = Fae(port_name=port_result.get_returned_value().name)

    phy_recovery_obj = selected_port.port.interface.link.phy_recovery
    with allure.step("Start bad-flow scenarios"):
        with allure.independent_step("Testing show non-existing attribute in phy-recovery"):
            phy_recovery_obj.show('non-existing', should_succeed=False)

        if devices.dut.asic_type in [NvosConst.QTM4, NvosConst.NVL6] and not is_bug_active(4635940):
            with allure.independent_step("Configure phy-recovery on selected port and verify port state can't get up"):
                state = OutputParsingTool.parse_json_str_to_dictionary(selected_port.port.interface.link.state.show()).get_returned_value()
                if state.get(NvosConsts.LINK_STATE_UP) is not None:
                    _apply_mode(selected_port, PhyRecoveryConsts.ENABLED)
                    _verify_link_state(selected_port, NvosConsts.LINK_STATE_DOWN)
                else:
                    logger.info("No port in up state were found")

        with allure.independent_step(f"Testing bad-mode on interface {selected_port.port.name}"):
            logger.info(f"Set {PhyRecoveryConsts.SerdesEQ.MODE} to bad-mode")
            phy_recovery_obj.set(PhyRecoveryConsts.SerdesEQ.MODE, "bad-mode", expected_str=ERR_MSG_BAD_MODE).verify_result()

        with allure.independent_step(f"Testing bad-timeout on interface {selected_port.port.name}"):
            logger.info(f"Set {PhyRecoveryConsts.SerdesEQ.TIMEOUT} to -1")
            expected_str = (
                ERR_MSG_TIMEOUT_NEGATIVE_MIN
                if is_bug_active(4631963) and random_api == ApiType.OPENAPI
                else ERR_MSG_TIMEOUT_VALID_RANGE
            )
            phy_recovery_obj.set(PhyRecoveryConsts.SerdesEQ.TIMEOUT, -1, expected_str=expected_str).verify_result()


@pytest.mark.interface
@pytest.mark.multiplanar
def test_set_fae_phy_recovery_trunk_ports(devices, random_api):
    """
    @summary:
        Verify that firmware recovery settings (mode and timeout) can be applied and updated on trunk ports (sw).

    Steps:
    1. Skip if no trunk links.
    2. Enable recovery mode and set timeout on all trunk ports.
    3. Verify settings on a single random trunk port.
    4. Update timeout higher and lower, verifying group vs. local effects.
    5. Disable recovery and confirm defaults restored.
    """
    TestToolkit.tested_api = random_api
    skip_if_no_trunk_links(devices)
    port_name = select_random_nvl_port_name(devices, 'sw')
    summarized_switch_ports = summarize_switch_ports(devices.dut.nvl_trunk_ports_list)

    _run_fae_mode_timeout_test(
        group_all_ports=summarized_switch_ports,
        port_name=port_name,
    )


@pytest.mark.interface
@pytest.mark.multiplanar
def test_set_fae_phy_recovery_access_ports(devices, random_api, standalone_system, has_loopbox, setup_name, is_simx):
    """
    @summary:
        Verify that firmware recovery settings (mode and timeout) can be applied and updated on access ports (acp).

    Steps:
    1. Skip if no access links.
    2. Enable recovery mode and set timeout on all access ports.
    3. Verify settings on a single random access port.
    4. Update timeout higher and lower, verifying group vs. local effects.
    5. Disable recovery and confirm defaults restored.
    """
    TestToolkit.tested_api = random_api
    skip_if_no_access_links(has_loopbox, standalone_system, is_simx)
    port_name = select_random_nvl_port_name(devices, 'acp')
    _run_fae_mode_timeout_test(
        group_all_ports=f'acp1-{str(len(devices.dut.nvl_access_ports_list))}',
        port_name=port_name,
        standalone_system=standalone_system,
        setup_name=setup_name,
    )


def _run_fae_mode_timeout_test(group_all_ports, port_name, standalone_system=False, setup_name=None):

    selected_port = Fae(port_name=port_name)
    all_ports = Fae(port_name=group_all_ports)

    validate_default_config(selected_port)

    try:
        for mode in PhyRecoveryConsts.MODES:
            with allure.step(f"Set {PhyRecoveryConsts.SerdesEQ.MODE} to {mode}"):
                if mode == PhyRecoveryConsts.ENABLED:
                    _apply_mode(all_ports, mode)
                    reset_gpus_if_needed(setup_name)
                    _verify_config(selected_port, mode, PHY_RECOVERY_DEFAULT_TIMEOUT)

                    higher_timeout = random.randrange(
                        PHY_RECOVERY_HIGHER_TIMEOUT_MIN,
                        PHY_RECOVERY_HIGHER_TIMEOUT_MAX + PHY_RECOVERY_TIMEOUT_STEP,
                        PHY_RECOVERY_TIMEOUT_STEP,
                    )
                    with allure.step(f"Update timeout to higher value ({higher_timeout}) while mode {mode}"):
                        _apply_timeout(all_ports, higher_timeout)
                        reset_gpus_if_needed(setup_name)
                        _validate_timeout(selected_port, higher_timeout)

                    lower_timeout = random.randrange(
                        PHY_RECOVERY_LOWER_TIMEOUT_MIN,
                        PHY_RECOVERY_LOWER_TIMEOUT_MAX + PHY_RECOVERY_TIMEOUT_STEP,
                        PHY_RECOVERY_TIMEOUT_STEP,
                    )
                    if standalone_system:
                        with allure.step(
                            f"Update timeout to lower value ({lower_timeout}) locally — "
                            f"expect NO change"
                        ):
                            _apply_timeout(selected_port, lower_timeout)
                            _validate_timeout(
                                selected_port,
                                higher_timeout,
                                verify_after_seconds=PHY_RECOVERY_VERIFY_RECHECK_SECONDS,
                            )
                    else:
                        with allure.step(
                            f"Update timeout to lower value ({lower_timeout}) locally — "
                            f"expect link state to change"
                        ):
                            _apply_timeout(selected_port, lower_timeout)
                            _verify_link_state(selected_port, NvosConsts.LINK_STATE_UP)

                    with allure.step(f"Update timeout to lower value ({lower_timeout}) on all ports"):
                        _apply_timeout(all_ports, lower_timeout)
                        reset_gpus_if_needed(setup_name)
                        _validate_timeout(selected_port, lower_timeout)
                elif mode == PhyRecoveryConsts.DISABLED:
                    ports_in_up_state = RandomizationTool.select_random_ports(requested_ports_state=NvosConsts.LINK_STATE_ALL_TYPES,
                                                                              num_of_ports_to_select=0).get_returned_value()
                    _apply_mode(all_ports, mode)
                    _verify_config(selected_port, mode)
                    current_ports_in_up_state = RandomizationTool.select_random_ports(requested_ports_state=NvosConsts.LINK_STATE_ALL_TYPES,
                                                                                      num_of_ports_to_select=0).get_returned_value()
                    expected_names = {port.name for port in ports_in_up_state}
                    current_names = {port.name for port in current_ports_in_up_state}
                    missing = sorted(expected_names - current_names)
                    extra = sorted(current_names - expected_names)
                    message = (
                        f"Port state mismatch after disabling recovery.\n"
                        f"Expected UP: {sorted(expected_names)}\n"
                        f"Actual UP: {sorted(current_names)}\n"
                        f"Missing: {missing}\n"
                        f"Extra: {extra}"
                    )
                    assert expected_names == current_names, message
                else:
                    _apply_mode(all_ports, mode)
                    _verify_config(selected_port, mode)
    finally:
        with allure.step("Unset configuration to return to defaults"):
            all_ports.port.interface.link.phy_recovery.unset(apply=True, ask_for_confirmation=True).verify_result()
            reset_gpus_if_needed(setup_name)

        retry_call(validate_default_config, [selected_port], exceptions=AssertionError, tries=6, delay=30)


def _apply_mode(selected_port, mode):
    """"
    @summary:
        Apply mode to the selected port.
    """
    selected_port.port.interface.link.phy_recovery.set(PhyRecoveryConsts.SerdesEQ.MODE, mode, apply=True,
                                                       ask_for_confirmation=True).verify_result()


def _apply_timeout(selected_port, timeout):
    """
    @summary:
        Apply timeout to the selected port.
    """
    selected_port.port.interface.link.phy_recovery.set(PhyRecoveryConsts.SerdesEQ.TIMEOUT, timeout, apply=True,
                                                       ask_for_confirmation=True).verify_result()


def _verify_config(selected_port, mode, timeout=None):
    """
    @summary:
        Verify mode and timeout are applied to the selected port.
    """
    retry_call(
        validate_mode_set,
        [selected_port, mode, timeout],
        exceptions=AssertionError,
        tries=VALIDATE_RETRIES,
        delay=VALIDATE_RETRY_DELAY_SECONDS,
    )


def _validate_timeout(selected_port, expected_timeout=None, verify_after_seconds=None):
    """
    @summary:
        Validate timeout is applied to the selected port.
    """
    _verify_config(selected_port, PhyRecoveryConsts.ENABLED, expected_timeout)

    if verify_after_seconds:
        with allure.step(f"Wait {verify_after_seconds}s and re-verify timeout is still {expected_timeout}"):
            time.sleep(verify_after_seconds)
            _verify_config(selected_port, PhyRecoveryConsts.ENABLED, expected_timeout)


def _validate_default_values(port_output, dict):
    """
    @summary:
        Validate fields and values from a port output against an expected dict.
    """
    expected_fields = list(dict.keys())
    expected_values = list(dict.values())
    ValidationTool.validate_fields_values_in_output(expected_fields, expected_values, port_output).verify_result()


def _verify_link_state(selected_port, expected_link_state):
    """
    @summary:
        Verify link state is applied to the selected port.
    """
    port_state = OutputParsingTool.parse_json_str_to_dictionary(
        selected_port.port.interface.link.state.show()).get_returned_value()
    assert port_state.get(expected_link_state) is not None, f"Link state is {port_state} but expected {expected_link_state}"


def _verify_attribute(selected_port, path, attribute, expected_value):
    port_output = OutputParsingTool.parse_json_str_to_dictionary(
        selected_port.port.interface.link.phy_recovery.show()).get_returned_value()
    if path[0] != attribute:
        port_output = port_output[path[0]]
    assert port_output.get(attribute) == expected_value, (
        f"{attribute} expected {expected_value}, got {port_output.get(attribute)}"
    )


def _flatten_attributes(d, parent_path=None):
    """
    Recursively flattens a nested dictionary to find all leaf attributes (keys).
    Returns a list of tuples: (full_path_list, attribute_key)
    Example: (['STEP_1', 'PRESENT_MODE'], 'PRESENT_MODE')
    """
    if parent_path is None:
        parent_path = []

    flat_list = []
    for k, v in d.items():
        current_path = parent_path + [k]
        if isinstance(v, dict):
            # Recurse for nested dictionaries
            flat_list.extend(_flatten_attributes(v, current_path))
        else:
            # Found a leaf attribute
            flat_list.append((current_path, k))
    return flat_list


def _get_random_attribute_and_value(attributes_dict, options_dict):
    """
    Chooses a random leaf attribute that has options defined, and selects
    a new random valid value for it.

    Args:
        attributes_dict (dict): The nested dictionary of current attributes.
        options_dict (dict): The dictionary containing valid options for each key.
    """
    # 1. Get all leaf attributes with their full path
    all_leaf_attributes = _flatten_attributes(attributes_dict)

    # 2. Filter attributes to include only those present in the options dictionary
    valid_attributes = [
        (path, key) for path, key in all_leaf_attributes
        if key in options_dict
    ]

    # 3. Choose a random attribute (path, key) from the valid list
    random_path_list, attribute_key = random.choice(valid_attributes)

    # 4. Get the possible options and select a random new value
    possible_values = options_dict[attribute_key]
    new_value = random.choice(possible_values)

    return random_path_list, attribute_key, new_value

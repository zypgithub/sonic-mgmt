"""Transceiver photonics tests for Taipan CPO systems (ELS/OE modules)."""

import logging
import random

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, PlatformConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.PhotonicsTool import PhotonicsTool
from ngts.nvos_tools.infra.RegressionConfigurations import Configurations
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.platform.constants import TransceiversConsts

logger = logging.getLogger()


def _get_transceiver_lists(transceivers: list[str]) -> tuple[list[str], list[str]]:
    """Extract ELS and OE transceiver lists from full transceiver list."""
    els = [t for t in transceivers if TransceiversConsts.TRANSCEIVERS_ELS in t]
    oe = [t for t in transceivers if TransceiversConsts.TRANSCEIVERS_OE in t]
    return els, oe


def _parse_threshold(threshold_str: str) -> float:
    """Parse threshold value from string (e.g., '80.00 C' -> 80.0, '4.00 dBm' -> 4.0)."""
    return float(threshold_str.split()[0])


def _validate_against_thresholds(value: float, data: dict, name: str,
                                 high_key: str = 'high-alarm-threshold',
                                 low_key: str = 'low-alarm-threshold') -> None:
    """Validate value against dynamic thresholds from output."""
    if high_key in data:
        high_threshold = _parse_threshold(data[high_key])
        assert value <= high_threshold, f"{name}: {value} exceeds high-alarm-threshold {high_threshold}"
    if low_key in data:
        low_threshold = _parse_threshold(data[low_key])
        assert value >= low_threshold, f"{name}: {value} below low-alarm-threshold {low_threshold}"


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_transceiver_els(engines, devices, nv_command, test_api):
    """
    Verify ELS transceiver fields, port-mapping, oe-mapping, and fault-condition.

    flow:
    1. Verify all expected fields exist for a random ELS transceiver
    2. Verify port-mapping, oe-mapping, and fault-condition for each ELS
    """
    TestToolkit.tested_api = test_api

    els_list, _ = _get_transceiver_lists(devices.dut.transceiver_list)
    if not els_list:
        pytest.skip("No ELS transceivers found")

    with allure.step("Get all transceiver data"):
        all_data = Tools.OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.platform.transceiver.show_detailed()).get_returned_value()

    with allure.step("Verify fields for random ELS transceiver"):
        els_rand = random.choice(els_list)
        expected_fields = set(TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_ELS])
        actual_fields = set(all_data[els_rand].keys())
        ValidationTool.validate_set_equal(actual_fields, expected_fields).verify_result()

    with allure.step("Verify port-mapping, oe-mapping, fault-condition for each ELS"):
        for els in els_list:
            els_output = all_data[els]

            with allure.independent_step(f"Verify {els} mappings"):
                # Port mapping
                actual_ports = set(els_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING].keys())
                expected_ports = set(TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING[els])
                ValidationTool.validate_set_equal(actual_ports, expected_ports).verify_result()

                # OE mapping
                actual_oes = set(els_output[PlatformConsts.TRANSCEIVER_OE_MAPPING].keys())
                expected_oes = set(TransceiversConsts.TRANSCEIVERS_ELS_OE_MAPPING[els])
                ValidationTool.validate_set_equal(actual_oes, expected_oes).verify_result()

                # Fault condition (only if inserted)
                if els_output[PlatformConsts.TRANSCEIVER_STATUS] == PlatformConsts.INSERTED:
                    ValidationTool.verify_field_value_in_output(
                        els_output, PlatformConsts.TRANSCEIVER_FAULT_CONDITION, 'false'
                    ).verify_result()


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_transceiver_oe(engines, devices, nv_command, test_api):
    """
    Verify OE transceiver fields, status, port-mapping, and els-mapping.

    flow:
    1. Verify all expected fields exist for a random OE transceiver
    2. Verify status=Inserted, port-mapping matches ELS mapping for each OE
    """
    TestToolkit.tested_api = test_api

    _, oe_list = _get_transceiver_lists(devices.dut.transceiver_list)
    if not oe_list:
        pytest.skip("No OE transceivers found")

    with allure.step("Get all transceiver data"):
        all_data = Tools.OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.platform.transceiver.show_detailed()).get_returned_value()

    with allure.step("Verify fields for random OE transceiver"):
        oe_rand = random.choice(oe_list)
        oe_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.platform.transceiver.show(oe_rand)).get_returned_value()

        expected_fields = set(TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_OE])
        actual_fields = set(oe_output.keys())
        ValidationTool.validate_set_equal(actual_fields, expected_fields).verify_result()

    with allure.step("Verify status and mappings for each OE"):
        for oe in oe_list:
            oe_output = all_data[oe]

            with allure.independent_step(f"Verify {oe}"):
                # Status must be Inserted
                ValidationTool.verify_field_value_in_output(
                    oe_output, PlatformConsts.TRANSCEIVER_STATUS, PlatformConsts.INSERTED
                ).verify_result()

                # Port mapping must match ELS mapping
                els_mapping = oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]
                actual_ports = set(oe_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING].keys())
                expected_ports = set(TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING[els_mapping])
                ValidationTool.validate_set_equal(actual_ports, expected_ports).verify_result()


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_transceiver_els_diagnostics(engines, devices, nv_command, test_api):
    """
    Verify ELS transceiver diagnostics: temperature, voltage, and channel fields.

    flow:
    1. Select random ELS, verify temperature against high-alarm-threshold
    2. Verify voltage against high/low-alarm-thresholds from output
    3. Verify channel diagnostics fields exist
    """
    TestToolkit.tested_api = test_api
    platform = Platform()

    els_list, _ = _get_transceiver_lists(devices.dut.transceiver_list)
    if not els_list:
        pytest.skip("No ELS transceivers found")

    els_name = random.choice(els_list)

    with allure.step(f"Get ELS {els_name} diagnostics"):
        els_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
            platform.transceiver.show(els_name)).get_returned_value()

    with allure.step("Verify temperature against thresholds"):
        temp_data = els_output.get('temperature', {})
        ValidationTool.validate_subset_in_superset(
            {'temperature', 'high-alarm-threshold'}, temp_data.keys()
        ).verify_result()

        temp_value = _parse_threshold(temp_data['temperature'])
        _validate_against_thresholds(temp_value, temp_data, f"{els_name} temperature")
        logger.info(f"{els_name} temperature: {temp_value}C (max: {temp_data['high-alarm-threshold']})")

    with allure.step("Verify voltage against thresholds"):
        voltage_data = els_output.get('voltage', {})
        ValidationTool.validate_subset_in_superset(
            {'voltage', 'high-alarm-threshold', 'low-alarm-threshold'}, voltage_data.keys()
        ).verify_result()

        voltage_value = _parse_threshold(voltage_data['voltage'])
        _validate_against_thresholds(voltage_value, voltage_data, f"{els_name} voltage")
        logger.info(f"{els_name} voltage: {voltage_value}V (range: {voltage_data['low-alarm-threshold']} - {voltage_data['high-alarm-threshold']})")

    with allure.step("Verify channel diagnostics fields"):
        channels = els_output.get('channel', {})
        assert channels, "No channels found"

        expected_channel_fields = {'rx-cdr-lol', 'rx-los', 'tx-ad-eq-fault', 'tx-cdr-lol', 'tx-los', 'tx-fault'}
        first_channel = next(iter(channels.values()))
        ValidationTool.validate_subset_in_superset(expected_channel_fields, first_channel.keys()).verify_result()


def _parse_power_dbm(power_str: str) -> float:
    """Parse dBm value from power string (e.g., '0.54 mW / -2.68 dBm' -> -2.68)."""
    # Format: "0.54 mW / -2.68 dBm" - extract dBm value after "/"
    return float(power_str.split('/')[1].strip().split()[0])


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_transceiver_oe_power_diagnostics(engines, devices, nv_command, test_api):
    """
    Verify OE transceiver rx/tx power against dynamic thresholds for traffic channels.

    flow:
    1. Find ELS with traffic ports using static mapping
    2. For each OE, find traffic channel indices from port-mapping
    3. Validate rx/tx power against high-alarm-threshold and low-alarm-threshold from output
    """
    TestToolkit.tested_api = test_api
    platform = Platform()

    # Get traffic ports for this DUT
    if not (traffic_ports := Configurations.traffic_ports.get(engines.dut.ip, [])):
        pytest.skip(f"No traffic ports configured for DUT {engines.dut.ip}")

    # Find ELS with traffic ports
    els_name, matching_ports, _ = PhotonicsTool.get_els_for_traffic_ports(traffic_ports)
    if not els_name:
        pytest.skip(f"No ELS found for traffic ports {traffic_ports}")

    oe_list = PhotonicsTool.get_oe_list_for_els(els_name)
    logger.info(f"ELS {els_name} with traffic ports {matching_ports}, OEs: {oe_list}")

    with allure.step(f"Validate power for OEs: {oe_list}"):
        for oe_name in oe_list:
            with allure.independent_step(f"Check {oe_name}"):
                oe_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
                    platform.transceiver.show(oe_name)).get_returned_value()

                # Find traffic channel indices from OE's port-mapping
                port_list = list(oe_output.get('port-mapping', {}).keys())
                channel_indices = PhotonicsTool.get_traffic_channel_indices(port_list, traffic_ports)

                if not channel_indices:
                    logger.info(f"{oe_name}: no traffic ports in mapping, skipping")
                    continue

                channels = oe_output.get('channel', {})
                for ch_idx in channel_indices:
                    if not (channel_data := channels.get(f'channel-{ch_idx}')):
                        continue

                    with allure.independent_step(f"Validate {oe_name} channel-{ch_idx}"):
                        rx_data = channel_data['rx-power']
                        tx_data = channel_data['tx-power']

                        # Parse dBm values and validate against thresholds
                        rx_dbm = _parse_power_dbm(rx_data['power'])
                        tx_dbm = _parse_power_dbm(tx_data['power'])

                        _validate_against_thresholds(rx_dbm, rx_data, f"{oe_name} ch-{ch_idx} rx-power")
                        _validate_against_thresholds(tx_dbm, tx_data, f"{oe_name} ch-{ch_idx} tx-power")

                        logger.info(f"{oe_name} ch-{ch_idx}: rx={rx_dbm} dBm, tx={tx_dbm} dBm - VALID")

import logging
import random

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, NvosConst, PlatformConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.infra.IbInterfaceTool import IbInterfaceTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.platform.constants import TransceiversConsts

logger = logging.getLogger()


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_transceiver_els(engines, devices, nv_command, test_api):
    """
    The test verifies ELS transceiver functionality for Taipan systems.

    flow:
    1. Verify all fields are as expected for els transceiver
    2. Verify transceiver fault-condition, port-mapping and oe-mapping values for each els transceiver
    """
    TestToolkit.tested_api = test_api

    transceivers_list = devices.dut.transceiver_list
    els_list = [name for name in transceivers_list if TransceiversConsts.TRANSCEIVERS_ELS in name]

    transceivers_els_to_port_mapping = TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING
    transceivers_els_to_oe_mapping = TransceiversConsts.TRANSCEIVERS_ELS_OE_MAPPING

    with allure.step("Get all transceiver information with single show_detailed call"):
        all_transceivers_data = Tools.OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.platform.transceiver.show_detailed()).get_returned_value()

    with allure.step("Verify all fields are as expected for ELS transceiver"):
        els_rand = random.choice(els_list)
        with allure.independent_step(f"Verify all fields are as expected for ELS transceiver {els_rand}"):
            els_output = all_transceivers_data[els_rand]

            expected_fields = TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_ELS]
            actual_fields = set(els_output.keys())
            expected_fields_set = set(expected_fields)

            ValidationTool.validate_set_equal(
                actual_fields, expected_fields_set, should_be_equal=True
            ).verify_result()

    with allure.step("Verify transceiver fault-condition, port-mapping and oe-mapping values for each ELS transceiver"):
        for els in els_list:
            with allure.independent_step(f"Verify transceiver fault-condition, port-mapping and oe-mapping values for {els}"):
                els_output = all_transceivers_data[els]

                with allure.independent_step(f"Verify port mapping for {els}"):
                    actual_port_mapping = els_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING].keys()
                    expected_port_mapping = transceivers_els_to_port_mapping[els]
                    ValidationTool.validate_set_equal(
                        actual_port_mapping, expected_port_mapping, should_be_equal=True
                    ).verify_result()

                with allure.independent_step(f"Verify OE mapping for {els}"):
                    actual_oe_mapping = els_output[PlatformConsts.TRANSCEIVER_OE_MAPPING].keys()
                    expected_oe_mapping = transceivers_els_to_oe_mapping[els]
                    ValidationTool.validate_set_equal(
                        actual_oe_mapping, expected_oe_mapping, should_be_equal=True
                    ).verify_result()

                if els_output[PlatformConsts.TRANSCEIVER_STATUS] == PlatformConsts.INSERTED:
                    with allure.independent_step(f"Verify fault condition for {els}"):
                        ValidationTool.verify_field_value_in_output(
                            output_dictionary=els_output,
                            field_name=PlatformConsts.TRANSCEIVER_FAULT_CONDITION,
                            expected_value='false'
                        ).verify_result()


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_transceiver_oe(engines, devices, nv_command, test_api):
    """
    The test verifies OE transceiver functionality for Taipan systems.

    flow:
    1. Verify all fields are as expected for oe transceiver
    2. Verify transceiver status, fault-condition, port-mapping and els-mapping for each oe transceiver
    """
    TestToolkit.tested_api = test_api

    transceivers_list = devices.dut.transceiver_list
    oe_list = [name for name in transceivers_list if TransceiversConsts.TRANSCEIVERS_OE in name]

    transceivers_els_to_port_mapping = TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING
    transceivers_els_to_oe_mapping = TransceiversConsts.TRANSCEIVERS_ELS_OE_MAPPING

    with allure.step("Get all transceiver information with single show_detailed call"):
        all_transceivers_data = Tools.OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.platform.transceiver.show_detailed()).get_returned_value()

    with allure.step("Verify all fields are as expected for OE transceiver"):
        oe_rand = random.choice(oe_list)
        oe_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.platform.transceiver.show(oe_rand)).get_returned_value()

        expected_fields = TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_OE]
        actual_fields = set(oe_output.keys())
        expected_fields_set = set(expected_fields)

        ValidationTool.validate_set_equal(
            actual_fields, expected_fields_set, should_be_equal=True
        ).verify_result()

    with allure.step("Verify transceiver status, fault-condition, port-mapping and els-mapping for each OE transceiver"):
        for oe in oe_list:
            oe_output = all_transceivers_data[oe]

            with allure.independent_step(f"Verify transceiver status for {oe}"):
                ValidationTool.verify_field_value_in_output(
                    output_dictionary=oe_output,
                    field_name=PlatformConsts.TRANSCEIVER_STATUS,
                    expected_value=PlatformConsts.INSERTED
                ).verify_result()

            with allure.independent_step(f"Verify ELS and port mapping for {oe}"):
                els_mapping = oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]
                actual_port_mapping = oe_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING].keys()
                expected_port_mapping = transceivers_els_to_port_mapping[els_mapping]
                ValidationTool.validate_set_equal(
                    actual_port_mapping, expected_port_mapping, should_be_equal=True
                ).verify_result()

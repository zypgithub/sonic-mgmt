import logging
import random

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, NvosConst, PlatformConsts
from ngts.nvos_tools.infra.IbInterfaceTool import IbInterfaceTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Tools import Tools
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

    with allure.step(f"Verify all fields are as expected for els transceiver"):
        els_rand = random.choice(els_list)
        els_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.platform.transceiver.show(els_rand)).get_returned_value()
        assert els_output.keys() == TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_ELS], \
            (f"els transceiver fields is: {els_output.keys()}, while the expected fields are: "
             f"{TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_ELS]}")

    with allure.step(f"Verify transceiver fault-condition, "
                     f"port-mapping and oe-mapping values for each els transceiver"):
        for els in els_list:
            els_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
                nv_command.platform.transceiver.show(els)).get_returned_value()
            assert els_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING].split() == \
                transceivers_els_to_port_mapping[els], \
                (f"Transceiver {els} port-mapping is {els_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING]}, "
                 f"instead of {transceivers_els_to_port_mapping[els]}")
            assert els_output[PlatformConsts.TRANSCEIVER_OE_MAPPING].split() == \
                transceivers_els_to_oe_mapping[els], \
                (f"Transceiver {els} oe-mapping is {els_output[PlatformConsts.TRANSCEIVER_OE_MAPPING]}, "
                 f"instead of {transceivers_els_to_oe_mapping[els]}")
            if els_output[PlatformConsts.TRANSCEIVER_STATUS] == PlatformConsts.INSERTED:
                assert els_output[PlatformConsts.TRANSCEIVER_FAULT_CONDITION] == 'false', \
                    (f"Transceiver {els} fault-condition is "
                     f"{els_output[PlatformConsts.TRANSCEIVER_FAULT_CONDITION]}, instead of false")


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

    with allure.step(f"Verify all fields are as expected for oe transceiver"):
        oe_rand = random.choice(oe_list)
        oe_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
            nv_command.platform.transceiver.show(oe_rand)).get_returned_value()
        assert oe_output.keys() == TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_OE], \
            (f"oe transceiver fields is: {oe_output.keys()}, while the expected fields are: "
             f"{TransceiversConsts.TRANSCEIVERS_FIELDS[TransceiversConsts.TRANSCEIVERS_OE]}")

    with allure.step(f"Verify transceiver status, fault-condition, "
                     f"port-mapping and els-mapping for each oe transceiver"):
        for oe in oe_list:
            oe_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
                nv_command.platform.transceiver.show(oe)).get_returned_value()
            assert oe_output[PlatformConsts.TRANSCEIVER_STATUS] == PlatformConsts.INSERTED, \
                (f"Transceiver {oe} status is {oe_output[PlatformConsts.TRANSCEIVER_STATUS]}, "
                 f"instead of {PlatformConsts.INSERTED}")
            assert oe_output[PlatformConsts.TRANSCEIVER_FAULT_CONDITION] == 'false', \
                (f"Transceiver {oe} fault-condition is {oe_output[PlatformConsts.TRANSCEIVER_FAULT_CONDITION]}, "
                 f"instead of false")
            assert oe_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING].split() == \
                transceivers_els_to_port_mapping[oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]], \
                (f"Transceiver {oe} port-mapping is {oe_output[PlatformConsts.TRANSCEIVER_PORT_MAPPING]}, "
                 f"instead of {transceivers_els_to_port_mapping[oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]]}")
            assert oe in transceivers_els_to_oe_mapping[oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]], \
                (f"Transceiver {oe} does not exist in {oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]} oe-mapping: "
                 f"{transceivers_els_to_oe_mapping[oe_output[PlatformConsts.TRANSCEIVER_ELS_MAPPING]]}")

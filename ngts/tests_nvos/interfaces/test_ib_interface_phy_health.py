import logging
from typing import Dict

import pytest

from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, PhyHealthConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.ib_interfaces
def test_show_phy_health(engines, test_api):
    """Checks that `nv show interface <port> link phy health` returns non-empty output in a valid format with expected fields."""
    selected_port = RandomizationTool.select_random_port(requested_ports_state=None).get_returned_value()
    output = selected_port.interface.link.phy.health.show()
    d = OutputParsingTool.parse_show_output_to_dict(output).get_returned_value()

    with allure.step("Verify output structure and field presence"):
        ValidationTool.verify_field_exist_in_json_output(d, PhyHealthConsts.EXPECTED_FIELDS).verify_result()

        lane_data = d["lane"]
        for lane_key in lane_data:
            ValidationTool.verify_field_value_in_output(lane_data[lane_key], PhyHealthConsts.LANE_RAW_BER, PhyHealthConsts.EXPECTED_BER_FORMAT).verify_result()


@pytest.mark.ib_interfaces
def test_show_phy_health_histogram(engines, test_api):
    """Checks that `nv show interface <port> link phy health histogram` returns non-empty output with 16 bins (0-15)."""
    selected_port = RandomizationTool.select_random_port(requested_ports_state=None).get_returned_value()
    output = selected_port.interface.link.phy.health.show('histogram')
    d = OutputParsingTool.parse_show_output_to_dict(output).get_returned_value()

    expected_bin_count = PhyHealthConsts.EXPECTED_BIN_COUNT
    expected_bin_keys = [str(bin_num) for bin_num in range(expected_bin_count)]

    with allure.step("Verify histogram structure and data types"):
        ValidationTool.verify_field_exist_in_json_output(d, [PhyHealthConsts.RS_FEC_CORRECTED_ERRORS]).verify_result()

        histogram_data = d[PhyHealthConsts.RS_FEC_CORRECTED_ERRORS]
        ValidationTool.verify_field_exist_in_json_output(histogram_data, expected_bin_keys).verify_result()


def get_phy_health(port: Port) -> Dict:
    """Gets the phy health output for a port."""
    return OutputParsingTool.parse_show_output_to_dict(
        port.interface.link.phy.health.show()
    ).get_returned_value()


def get_phy_health_histogram(port: Port) -> Dict:
    """Gets the phy health histogram output for a port."""
    return OutputParsingTool.parse_show_output_to_dict(
        port.interface.link.phy.health.show('histogram')
    ).get_returned_value()

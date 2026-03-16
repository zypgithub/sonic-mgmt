import logging

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.fae
@pytest.mark.bmc
@pytest.mark.platform
def test_show_eeprom_bmc(devices, random_api, output_format):
    fae = Fae()

    with allure.step("Consider skipping test (if device has no BMC)"):
        device = devices.dut
        if not device.platform_inventory_items_dict.get("bmc"):
            pytest.skip(f"Skipping test because DUT has no BMC")

    with allure.step("Verify fields and values for fae platform eeprom BMC"):
        output = OutputParsingTool.parse_show_output_to_dict(
            fae.platform.eeprom.show("BMC", output_format=output_format),
            output_format=output_format, field_name_dict={}).get_returned_value()

        output = {key: value["value"] for key, value in output.items()}
        expected = device.fae_eeprom_values['BMC']
        ValidationTool.validate_output_of_show(output, expected, allow_extra_fields=True).verify_result()

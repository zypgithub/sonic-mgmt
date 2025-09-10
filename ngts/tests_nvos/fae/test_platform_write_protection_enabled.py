import logging
import pytest
import random

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.Fae import Fae
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


@pytest.mark.fae
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_platform_write_protection_enabled(engines, test_api):
    """
        1. Check fae platform write protection enabled by default
    """
    TestToolkit.tested_api = test_api
    fae = Fae()
    with allure.step("Run show write protection and check default values"):
        output_dictionary = OutputParsingTool.parse_show_output_to_dict(
            fae.platform.write_protection.show().get_returned_value())

        ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                    field_name='wire-protection',
                                                    expected_value='enabled').verify_result()

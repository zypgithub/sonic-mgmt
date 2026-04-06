import re

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, OutputFormat
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.fae
@pytest.mark.platform
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_fae_platform_bkv_show(devices, test_api):
    """
    Validate ``nv show fae platform bkv --output json`` (flat object with ``version``, e.g. ``{"version": "0.6"}``).
    """
    if 'bkv' not in devices.dut.constants.dump_files:
        pytest.skip('BKV is not expected on this platform')
    TestToolkit.tested_api = test_api
    fae = Fae()
    with allure.step('Parse nv show fae platform bkv --output json'):
        bkv_show = OutputParsingTool.parse_json_str_to_dictionary(
            fae.platform.bkv.show(output_format=OutputFormat.json)).get_returned_value()
    with allure.step('Validate BKV version'):
        version = bkv_show.get('version')
        assert version is not None and str(version).strip(), f"Missing version in BKV output: {bkv_show!r}"
        assert re.fullmatch(r'[\w][\w.-]*', str(version)), f"Unexpected BKV version format: {version!r}"

import pytest

from ngts.ngts_types.devices_T import DevicesT
from ngts.ngts_types.engines_T import EnginesT
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RegisterTool import RegisterTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.platform
@pytest.mark.nvos_ci
def test_show_platform_asic_revision_id(engines: EnginesT, devices: DevicesT):
    """
    Verify nv show platform reports correct asic-revision-id.
    Cross-validates NVUE asic-revision against MGIR hw_revision register.

    Test Steps:
        1. Read hw_revision from MGIR register via mlxreg
        2. Read asic-revision from nv show platform
        3. Assert both values match
    """
    if not hasattr(devices.dut, 'mst_dev_name') or not devices.dut.mst_dev_name:
        pytest.skip("No MST device names configured for this device")

    with allure.step("Read hw_revision from MGIR register"):
        mst_dev_name = devices.dut.mst_dev_name
        if not isinstance(mst_dev_name, str):
            mst_dev_name = mst_dev_name[0]
        mgir_output: str = RegisterTool.get_mst_register_value(
            engines.dut, mst_dev_name, "MGIR", grep_pattern="hw_revision")
        hw_revision: str = mgir_output.split()[-1].strip()

    with allure.step("Read asic-revision from nv show platform"):
        platform: Platform = Platform()
        platform_output: dict[str, str] = OutputParsingTool.parse_show_output_to_dict(
            platform.show()).get_returned_value()
        asic_revision: str = platform_output[PlatformConsts.ASIC_REVISION]

    with allure.step("Verify ASIC revision matches MGIR hw_revision"):
        assert int(hw_revision, 16) == int(asic_revision, 16), \
            f"ASIC revision mismatch: MGIR hw_revision={hw_revision}, platform asic-revision={asic_revision}"

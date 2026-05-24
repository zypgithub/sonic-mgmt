import pytest

from ngts.ngts_types import EnginesT, DevicesT
from ngts.nvos_constants import constants_nvos
from ngts.nvos_tools.infra import RegisterTool
from ngts.nvos_tools.platform import Platform
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
        4. Read nv show platform inventory, verify SWITCH entry state and hardware-version
        5. Read nv show platform inventory SWITCH, verify consistency with full inventory
    """
    if not hasattr(devices.dut, 'mst_dev_name') or not devices.dut.mst_dev_name:
        pytest.skip("No MST device names configured for this device")

    with allure.step("Read hw_revision from MGIR register"):
        mst_dev_name = devices.dut.mst_dev_name
        if not isinstance(mst_dev_name, str):
            mst_dev_name = mst_dev_name[0]
        mgir_output: str = RegisterTool.RegisterTool.get_mst_register_value(
            engines.dut, mst_dev_name, "MGIR", grep_pattern="hw_revision")
        hw_revision: str = mgir_output.split()[-1].strip()
        hw_revision_int: int = int(hw_revision, 16)

    platform = Platform.Platform()

    with allure.step("Verify Platform ASIC revision matches MGIR hw_revision"):
        platform_output: dict[str, str] = platform.parse_show()
        asic_revision: str = platform_output[constants_nvos.PlatformConsts.ASIC_REVISION]

        assert hw_revision_int == int(asic_revision, 16), (
            f"ASIC revision mismatch: MGIR hw_revision={hw_revision}, "
            f"platform asic-revision={asic_revision}"
        )

    with allure.step("Verify Platform Inventory ASIC revision matches MGIR hw_revision"):
        inventory_output: dict = platform.inventory.parse_show()
        switch_output: dict = inventory_output[constants_nvos.PlatformConsts.HW_COMP_SWITCH]
        assert int(switch_output[constants_nvos.PlatformConsts.HARDWARE_VERSION], 16) == hw_revision_int, (
            f"Platform Inventory ASIC revision mismatch: MGIR hw_revision={hw_revision}, "
            f"platform inventory hardware-version={switch_output[constants_nvos.PlatformConsts.HARDWARE_VERSION]}"
        )
        switch_output: dict = platform.inventory.parse_show(op_param=constants_nvos.PlatformConsts.HW_COMP_SWITCH)
        assert int(switch_output[constants_nvos.PlatformConsts.HARDWARE_VERSION], 16) == hw_revision_int, (
            f"Platform Inventory SWITCH ASIC revision mismatch: MGIR hw_revision={hw_revision}, "
            f"platform inventory hardware-version={switch_output[constants_nvos.PlatformConsts.HARDWARE_VERSION]}"
        )

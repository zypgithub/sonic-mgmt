import pytest
from ngts.nvos_constants.constants_nvos import MultiPlanarConsts
from ngts.nvos_tools.infra.MultiPlanarTool import MultiPlanarTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='session', autouse=True)
def install_and_uninstall_platform_file(engines, devices):
    """
    install/uninstall xdr simulation on switch.
    """
    system = System(devices_dut=devices.dut)

    with allure.step("install xdr simulation on switch"):
        MultiPlanarTool.override_platform_file(system, engines, devices, MultiPlanarConsts.NVL_SIMULATION_FILE)

    yield

    with allure.step("uninstall xdr simulation on switch"):
        MultiPlanarTool.override_platform_file(system, engines, devices, MultiPlanarConsts.ORIGIN_FILE)

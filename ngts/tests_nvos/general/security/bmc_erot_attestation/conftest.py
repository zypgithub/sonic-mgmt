import pytest

from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot


@pytest.fixture(scope='session')
def available_spdm_components(devices, setup_name):
    dut_device: BaseDevice = devices.dut
    return dut_device.get_available_erot_names(setup_name)


@pytest.fixture(scope='session', autouse=True)
def verify_available_components_on_dut(available_spdm_components):
    pass  # TODO: complete


@pytest.fixture()
def clear_measurements(topology_obj, engines):
    with allure.step('do power cycle (remote reboot) do the system to clear components expect_measurements'):
        recover_dut_with_remote_reboot(topology_obj, engines, False)

import logging
import time

import pytest

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.Spdm import SpdmComponentFields
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.bmc.bmc_erot_attestation.constants import SpdmConsts, NA
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot


@pytest.fixture(scope='session')
def available_spdm_components(devices, setup_name):
    """
    Get expected SPDM components (ERoTs, MCU, etc.) from device definition.
    Single source of truth - device model defines what should exist.
    """
    # Use device definition as authoritative source (consistent with cluster refactoring)
    available_components = devices.dut.get_spdm_components(setup_name)

    for component in available_components:
        logging.info(f'SPDM component "{component}" expected on this device')

    return available_components


already_remote_rebooted = False


@pytest.fixture()
def clear_measurements(topology_obj, engines):
    global already_remote_rebooted
    if not already_remote_rebooted:
        with allure.step('do power cycle (remote reboot) do the system to clear components expect_measurements'):
            time.sleep(5)
            recover_dut_with_remote_reboot(topology_obj, engines, 150)
            already_remote_rebooted = True
    else:
        logging.info('remote reboot was performed already in the 1st flavor of this test')

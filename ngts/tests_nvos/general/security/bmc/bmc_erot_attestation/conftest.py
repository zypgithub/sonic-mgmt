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
    out = OutputParsingTool.parse_json_str_to_dictionary(System().security.spdm.show()).get_returned_value()
    available_components_names = []
    for component_name in SpdmConsts.components:
        certificates_out = out[component_name][SpdmComponentFields.CERTIFICATES]
        component_is_available = SpdmConsts.Component.Certificates.CERT_STRING in certificates_out and certificates_out[
            SpdmConsts.Component.Certificates.ID] != NA
        if component_is_available:
            available_components_names.append(component_name)
        logging.info(f'component "{component_name}" is {"" if component_is_available else "not "}available!')
    return available_components_names

    # dut_device: BaseDevice = devices.dut
    # return dut_device.get_available_erot_names(setup_name)


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

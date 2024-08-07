import logging
import pytest
import re

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


@pytest.mark.bmc
@pytest.mark.platform
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_platform_firmware_bmc_component(engines, devices, test_api):
    """Tests nv show platform firmware bmc component"""
    TestToolkit.tested_api = test_api

    fae = Fae()
    platform = Platform()
    dut_engine: LinuxSshEngine = TestToolkit.engines.dut

    with allure.step("Test output of nv show platform firmware and nv show fae platform firmware"):
        firmware_output = OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).get_returned_value()
        fae_firmware_output = OutputParsingTool.parse_json_str_to_dictionary(fae.platform.firmware.show()) \
            .get_returned_value()

    with allure.step('get nvos password to bmc from tpm'):
        tpm = TpmTool(dut_engine)
        bmc_password = tpm.get_bmc_admin_password_from_tpm()

    with allure.step("Grep all components from BMC redfish command"):
        client = CurlTool(server_host=PlatformConsts.BMC_INTERNAL_IP, username=PlatformConsts.BMC_LOGIN, password=bmc_password)
        bmc_components_output = client.run_redfish_command(rest_op='GET', path=PlatformConsts.BMC_FIRMWARE_INVENTORY_LINK)
        bmc_firmware_inventory = re.findall(PlatformConsts.BMC_INVENTORY_PATTERN, bmc_components_output)

    with allure.step("Grep version per each component and compare version with regular and fae output"):
        for component in bmc_firmware_inventory:
            path = PlatformConsts.BMC_FIRMWARE_INVENTORY_LINK + '/' + component
            component_output = client.run_redfish_command(rest_op='GET', path=path)
            bmc_component_version = re.search(PlatformConsts.BMC_COMPONENT_VERSION_PATTERN, component_output)
            _check_version_in_regular_fae_output(bmc_component_version, firmware_output, fae_firmware_output, component)

    with allure.step("Grep version per BMC component and verify it in regular and fae command"):
        path = PlatformConsts.BMC_FIRMWARE_INVENTORY_LINK + '/' + PlatformConsts.BMC_FIRMWARE_BMC_LINK
        component_output = client.run_redfish_command(rest_op='GET', path=path)
        bmc_component_version = re.search(PlatformConsts.BMC_COMPONENT_VERSION_PATTERN, component_output)
        firmware_component_output = OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show('BMC')) \
            .get_returned_value()
        fae_firmware_component_output = OutputParsingTool.parse_json_str_to_dictionary(fae.platform.firmware.
                                                                                       show('BMC')).get_returned_value()
        _check_version_in_regular_fae_output(bmc_component_version, firmware_component_output,
                                             fae_firmware_component_output)


def _run_redfish_command(engines, bmc_password, link, component=''):
    return engines.dut.run_cmd('sudo curl -k -u {0}:{1} -X GET {2}/{3}'.format(
        PlatformConsts.BMC_LOGIN, bmc_password, link, component))


def _check_version_in_regular_fae_output(bmc_component_version, firmware_output, fae_firmware_output, component=''):
    assert bmc_component_version.group(1) not in firmware_output, \
        'Version of {} not exist in nv show command'.format(component)
    assert bmc_component_version.group(1) not in fae_firmware_output, \
        'Version of {} not exist in nv show fae command'.format(component)

import logging
import pytest

from infra.tools.linux_tools.linux_tools import scp_file
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.platform.Platform import Platform
from ngts.scripts.bios_config import configure_bios
from ngts.tests_nvos.conftest import ProxySshEngine


logger = logging.getLogger()


@pytest.fixture(scope='module', autouse=True)
def restore_bios(topology_obj):
    yield
    configure_bios(topology_obj)


@pytest.mark.bios
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_bios_upgrade(engines: ProxySshEngine, devices, test_api):
    """
    Test flow:
        1. fetch current and previous BIOS versions
        2. install the previous BIOS version using nv action install fae platform firmware bios files <abs-path-to-file>
        3. wait for machine to boot up
        4. validate BIOS version was changed in nv show platform firmware
        5. install the current latest BIOS version (the one the machine begun the test with)
        6. validate BIOS version was changed in nv show platform firmware
    """

    TestToolkit.tested_api = test_api

    with allure.step('Create System object'):
        platform = Platform()
        fae = Fae()
    try:
        with allure.step('Fetch previous Bios image from: {}'.format(devices.dut.previous_bios_version_path)):
            fae.platform.firmware.bios.action_fetch(devices.dut.previous_bios_version_path).verify_result()

        with allure.step('installing Bios image {}'.format(devices.dut.previous_bios_version_name)):
            bios_name = devices.dut.previous_bios_version_path.split('/')[-1]
            fae.platform.firmware.install_bios_firmware(bios_image_path=bios_name, device=devices.dut)

        with allure.step('making sure BIOS is now on version {}'.format(devices.dut.previous_bios_version_name)):
            fw_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).verify_result()
            new_bios_version = fw_output["BIOS"]["actual-firmware"]
            logger.info("Found BIOS version: {}".format(new_bios_version))

            assert new_bios_version == devices.dut.previous_bios_version_name, \
                "BIOS firmware is {}, expected {} after the install".format(new_bios_version,
                                                                            devices.dut.previous_bios_version_name)
    except Exception as e:
        logger.info("Received Exception during BIOS firmware change: {}".format(e))
        raise e
    finally:
        TestToolkit.tested_api = ApiType.OPENAPI
        with allure.step(
                'restoring original Bios version as cleanup from {}'.format(devices.dut.current_bios_version_path)):
            fae.platform.firmware.bios.action_fetch(devices.dut.current_bios_version_path).verify_result()

        with allure.step('installing Bios image {}'.format(devices.dut.current_bios_version_name)):
            bios_name = devices.dut.current_bios_version_name.split('/')[-1]
            fae.platform.firmware.install_bios_firmware(bios_image_path=bios_name, device=devices.dut)

        with allure.step('making sure BIOS is now on version {}'.format(devices.dut.current_bios_version_name)):
            fw_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).verify_result()
            new_bios_version = fw_output["BIOS"]["actual-firmware"]
            logger.info("Found BIOS version: {}".format(new_bios_version))

            assert new_bios_version == devices.dut.current_bios_version_name, \
                "BIOS firmware is {}, expected {} after the install".format(new_bios_version,
                                                                            devices.dut.current_bios_version_name)

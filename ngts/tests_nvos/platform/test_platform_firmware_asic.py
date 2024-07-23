import logging
import string
from typing import Tuple

import pytest

from ngts.nvos_constants.constants_nvos import ImageConsts, NvosConst
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tests_nvos.platform.test_install_platform_firmware import get_asic_dict
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.checklist
@pytest.mark.fae
def test_show_fae_firmware(devices):
    """
    Show fae firmware test

    Test flow:
    1. Run show fae platform firmware
    2. Make sure that all required fields exist for all ASICs
    """
    fae = Fae()

    with allure.step("Run show fae firmware asic"):
        output_dictionary = get_asic_dict(fae)

    with allure.step("Validate asic amount"):
        expected_asic_amount = len(devices.dut.device_list) - 1
        assert len(output_dictionary) == expected_asic_amount, \
            "Unexpected num of ASIC\n Expected : {}\n but got {}".format(
                expected_asic_amount, len(output_dictionary))

    with allure.step("Validate asic fields"):
        verify_asic_fields(output_dictionary)


@pytest.mark.checklist
@pytest.mark.platform
def test_set_unset_platform_firmware_auto_update():
    """
    set/unset platform firmware auto update test

    Test flow:
    1. Disable firmware auto-update and make sure the configuration applied successfully
    2. Enable firmware auto-update and make sure the configuration applied successfully
    3. Disable firmware auto-update and make sure the configuration applied successfully
    4. Unset firmware auto-update and make sure the configuration is updated to default (enable)
    """
    with allure.step("Create Platform object"):
        platform = Platform()

    _set_and_verify(platform, PlatformConsts.FW_AUTO_UPDATE, "disabled")
    _set_and_verify(platform, PlatformConsts.FW_AUTO_UPDATE, "enabled")
    _set_and_verify(platform, PlatformConsts.FW_AUTO_UPDATE, "disabled")
    _set_and_verify(platform, PlatformConsts.FW_AUTO_UPDATE, "enabled", unset=True)


@pytest.mark.checklist
@pytest.mark.platform
def test_set_unset_platform_firmware_default(engines):
    """
    set/unset platform firmware default test

    Test flow:
    1. Set firmware default to 'user' and make sure the configuration applied successfully
    2. Set firmware default to 'image' and make sure the configuration applied successfully
    4. Set firmware default to 'user' and make sure the configuration applied successfully
    3. Unset firmware default and make sure the configuration is updated to default (image)
    """
    with allure.step("Create Platform object"):
        platform = Platform()

    _set_and_verify(platform, PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_CUSTOM)
    _set_and_verify(platform, PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_DEFAULT)
    _set_and_verify(platform, PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_CUSTOM)
    _set_and_verify(platform, PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_DEFAULT, unset=True)


@pytest.mark.checklist
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.platform
def test_platform_firmware_image_rename(engines, devices, topology_obj):
    """
    Check the image rename cmd.
    Validate that install and delete commands will success with the new name
    and will fail with the old name.
    1. Fetch random image, fetch image
    2. Rename image without mfa ending
    3. Install original image name , should fail
    4. Install original image new name , should success
    5. Delete the original image name , should fail
    6. Install new image name , success
    7. Uninstall image
    8. Delete the new image name , success
    """
    platform = Platform()
    dut = devices.dut
    _, fetched_image_name, _ = get_image_data_and_fetch_random_image_files(platform, dut, topology_obj)
    fetched_image_file = platform.firmware.asic.files.file_name[fetched_image_name]
    with allure.step("Rename image without mfa ending"):
        if dut.asic_type == NvosConst.QTM3 or dut.asic_type == NvosConst.NVL5:
            platform.firmware.asic.action_fetch(f"{PlatformConsts.XDR_FW_PATH}/{fetched_image_name}").verify_result()
        else:
            platform.firmware.asic.action_fetch(f"{PlatformConsts.FW_PATH}/{fetched_image_name}").verify_result()

    with allure.step("Rename image and verify"):
        new_name = RandomizationTool.get_random_string(20, ascii_letters=string.ascii_letters + string.digits)
        fetched_image_file.action_rename(new_name, expected_str="", rewrite_file_name=False)

    with allure.step("Rename already exist image and verify"):
        fetched_image_file.action_rename(new_name, expected_str="already exists")

    with allure.step("Install original image name, should fail"):
        logging.info("Install original image name: {}, should fail".format(fetched_image_name))
        platform.firmware.asic.files.file_name[fetched_image_name].action_file_install(
            force=False).verify_result(should_succeed=False)

    with allure.step("Delete original image name, should fail"):
        logging.info("Delete original image name, should fail")
        platform.firmware.asic.files.file_name[fetched_image_name].action_delete(should_succeed=False)

    try:
        with allure.step("Install new image name"):
            logging.info("Install new image name: {}".format(new_name))
            fetched_image_file.action_file_install(force=False).verify_result(should_succeed=True)

    finally:
        set_firmware_property(platform, PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_DEFAULT)


@pytest.mark.checklist
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.platform
def test_platform_firmware_image_upload(engines, devices, topology_obj):
    """
    Uploading image file to player and validate.
    1. Fetch random image
    2. Upload image to player
    3. Validate image uploaded to player
    4. Delete image file from player
    5. Delete image file from dut
    """
    platform = Platform()
    dut = devices.dut
    _, fetched_image, _ = get_image_data_and_fetch_random_image_files(platform, dut, topology_obj)
    upload_protocols = ['scp', 'sftp']
    player = engines['sonic_mgmt']
    image_file = platform.firmware.asic.files.file_name[fetched_image]

    with allure.step("Upload image to player {} with the next protocols : {}".format(player.ip, upload_protocols)):
        for protocol in upload_protocols:
            with allure.step("Upload image to player with {} protocol".format(protocol)):
                upload_path = '{}://{}:{}@{}/tmp/{}'.format(protocol, player.username, player.password, player.ip,
                                                            fetched_image)
                image_file.action_upload(upload_path, expected_str='File upload successfully')

            with allure.step("Validate file was uploaded to player and delete it"):
                assert player.run_cmd(
                    cmd='ls /tmp/ | grep {}'.format(fetched_image)), "Did not find the file with ls cmd"
                player.run_cmd(cmd='rm -f /tmp/{}'.format(fetched_image))

    with allure.step("Delete file from player"):
        logging.info("Delete file from player")
        platform.firmware.asic.files.delete_files([fetched_image])
        platform.firmware.asic.files.verify_show_files_output(unexpected_files=[fetched_image])


def _set_and_verify(platform: Platform, property: str, value: str, unset=False):
    if unset:
        with allure.step(f"Unset {property}"):
            unset_firmware_property(platform, property)
    else:
        with allure.step(f"Set {property} to '{value}'"):
            set_firmware_property(platform, property, value)

    with allure.step(f"Verify the configuration applied successfully - {property} is '{value}'"):
        verify_firmware_value(platform, property, value)


def set_firmware_property(platform, property, value):
    logging.info(f"Set firmware {property} to {value}")
    platform.firmware.asic.set(property, value, apply=True)


def unset_firmware_property(platform, property):
    logging.info(f"Unset firmware {property}")
    platform.firmware.asic.unset(property, apply=True)


def verify_firmware_value(platform, field_name, expected_value):
    logging.info("Verify the configuration applied successfully")
    show_output = platform.firmware.asic.show()
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(show_output).get_returned_value()
    ValidationTool.verify_field_value_in_output(output_dictionary, field_name, expected_value).verify_result()


def unset_auto_update(platform):
    logging.info('unset firmware auto-update')
    platform.firmware.asic.unset("auto-update")
    TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config(TestToolkit.engines.dut, True)


def set_auto_update(platform, value):
    logging.info('{} firmware asic auto-update'.format(value))
    platform.firmware.asic.set("auto-update", value, apply=True)


def verify_asic_fields(asic_dictionary):
    with allure.step("Verify all expected asic fields are presented in the output"):
        asic_fields = ["actual-firmware", "installed-firmware", "part-number", "auto-update", "fw-source"]
        for asic_name, asic_prop in asic_dictionary.items():
            ValidationTool.verify_field_exist_in_json_output(asic_prop, asic_fields).verify_result()


def compare_asic_names(first_dictionary, second_dictionary):
    logging.info("Compare asic names")
    assert set(first_dictionary.keys()) == set(second_dictionary.keys()), "asic lists are not equal"


def compare_asic_fields(first_dictionary, second_dictionary):
    logging.info("Compare asic fields")
    ValidationTool.compare_dictionaries(first_dictionary, second_dictionary).verify_result()


def get_image_data_and_fetch_random_image_files(platform, dut, topology_obj, images_amount_to_fetch=1
                                                ) -> Tuple[str, str, str]:
    original_image, default_firmware = get_image_data(platform, dut)

    with ((allure.step("Get {} available image files".format(images_amount_to_fetch)))):
        asic_type = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific'][
            'chip_type']
        if "QTM3" in default_firmware:
            image_to_fetch = '{}fw-{}-'.format(PlatformConsts.XDR_FW_PATH, asic_type) + \
                ImageConsts.XDR_FW_STABLE_VERSION
            image_name = 'fw-{}-'.format(asic_type) + ImageConsts.XDR_FW_STABLE_VERSION
        else:
            image_to_fetch = '{}fw-{}-'.format(PlatformConsts.FW_PATH, asic_type) + ImageConsts.FW_STABLE_VERSION
            image_name = 'fw-{}-'.format(asic_type) + ImageConsts.FW_STABLE_VERSION
        platform.firmware.asic.action_fetch(image_to_fetch).verify_result()
    return original_image, image_name, default_firmware


def get_image_data(platform, dut) -> Tuple[str, str]:
    with allure.step("Save original installed image name"):
        original_images = OutputParsingTool.parse_json_str_to_dictionary(
            platform.firmware.show("ASIC")).get_returned_value()
        original_image = original_images[PlatformConsts.FW_ACTUAL]
        if dut.asic_type == NvosConst.QTM2:
            default_firmware = 'fw-QTM2.mfa'
        elif dut.asic_type in [NvosConst.QTM3, NvosConst.NVL5]:
            default_firmware = 'fw-QTM3.mfa'
        else:
            raise Exception(f"Unsupported ASIC: {dut.asic_type}")
        logging.info("Actual firmware: {}".format(original_image))
        return original_image, default_firmware

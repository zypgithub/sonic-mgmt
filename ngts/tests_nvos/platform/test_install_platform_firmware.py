import logging
from typing import Tuple

import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import NvosConst, PlatformConsts, HealthConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.checklist
@pytest.mark.platform
def test_install_platform_firmware(engines, devices, test_name):
    """
    Install platform firmware test

    Test flow:
    1. Install platform firmware
    2. Make sure the installed firmware exist in 'installed-firmware'
    3. Reboot the system
    4. Verify the firmware is updated successfully
    5. Install the original firmware
    """
    system = System()
    platform = Platform()
    fae = Fae()
    fw_has_changed = False
    new_fw_name, fw_file_name = get_version_and_file_name(devices.dut.asic_type)
    fw_file = f"/auto/sw_system_project/NVOS_INFRA/verification_files/{fw_file_name}"
    logging.info(f"using {fw_file} fw file")

    with allure.step("Check actual firmware value"):
        asic_dictionary = get_asic_dict(fae)
        first_asic_name = list(asic_dictionary.keys())[0]
        actual_firmware = asic_dictionary[first_asic_name]["actual-firmware"]
        logging.info("Original actual firmware - " + actual_firmware)
        installed_firmware = asic_dictionary[first_asic_name]["installed-firmware"]
        logging.info("Original actual installed firmware - " + installed_firmware)
        validate_all_asics_have_same_info()
        system.validate_health_status(HealthConsts.OK)

    try:
        with allure.step("Install system firmware file - " + fw_file):
            with allure.step("fetch firmware file to switch"):
                player_engine = engines['sonic_mgmt']
                scp_path = 'scp://{}:{}@{}'.format(player_engine.username, player_engine.password, player_engine.ip)
                platform.firmware.asic.action_fetch(fw_file, base_url=scp_path).verify_result()

            with allure.step("Install firmware and verify"):
                res_obj, duration = OperationTime.save_duration('install user FW', 'include reboot', test_name,
                                                                install_new_user_fw, system, platform, fw_file_name, fae,
                                                                new_fw_name, actual_firmware, engines, test_name)
                OperationTime.verify_operation_time(duration, 'install user FW').verify_result()

            with allure.step('Verify the firmware installed successfully'):
                verify_firmware_with_platform_and_fae_cmd(platform, fae, new_fw_name, new_fw_name)
                validate_all_asics_have_same_info()
                system.validate_health_status(HealthConsts.OK)
                fw_has_changed = True

    finally:
        with allure.step("cleanup steps"):
            OperationTime.save_duration('install default fw', 'include reboot', test_name, install_image_fw,
                                        system, platform, engines, test_name, fw_has_changed)

        with allure.step('Verify the firmware installed successfully'):
            verify_firmware_with_platform_and_fae_cmd(platform, fae, actual_firmware, actual_firmware)
            validate_all_asics_have_same_info()
            system.validate_health_status(HealthConsts.OK)


def get_version_and_file_name(asic_type: str) -> Tuple[str, str]:
    firmware_versions = {NvosConst.QTM2: ("31_2014_0902-024", "fw-QTM2-rel-31_2014_0902-024.mfa"),
                         NvosConst.QTM3: ("35_2014_0902-024", "fw-QTM3-rel-35_2014_0902-024.mfa"),
                         NvosConst.NVL5: ("35_2014_0402", "fw-QTM3-rel-35_2014_0402.mfa")}
    if asic_type in firmware_info:
        return firmware_versions[asic_type]
    else:
        raise NotImplementedError()


def get_asic_dict(fae):
    show_output = OutputParsingTool.parse_json_str_to_dictionary(fae.platform.firmware.show()).get_returned_value()
    asic_dictionary = {k: v for k, v in show_output.items() if PlatformConsts.FW_ASIC in k}
    assert asic_dictionary and len(asic_dictionary.keys()) > 0, "asic list is empty"
    return asic_dictionary


def install_image_fw(system, platform, engines, test_name, fw_has_changed):
    with allure.step("Install original system firmware file"):
        platform.firmware.asic.set(PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_DEFAULT, apply=True)
        NvueGeneralCli.save_config(engines.dut)

    with allure.step('Rebooting the dut after image installation'):
        logging.info("Rebooting dut")
        if fw_has_changed:
            res_obj, duration = OperationTime.save_duration('reboot with default FW installation', '', test_name,
                                                            system.reboot.action_reboot)
            res = res_obj
            OperationTime.verify_operation_time(duration, 'reboot with default FW installation').verify_result()
        else:
            res = system.reboot.action_reboot()

        return res


def install_new_user_fw(system, platform, new_fw_to_install, fae, new_fw_name, actual_firmware, engines, test_name):
    platform.firmware.asic.files.file_name[new_fw_to_install].action_file_install(force=False).verify_result(
        should_succeed=True)
    platform.firmware.asic.set(PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_CUSTOM, apply=True)

    with allure.step("Verify installed file can be found in show output"):
        verify_firmware_with_platform_and_fae_cmd(platform, fae, new_fw_name, actual_firmware)
        validate_all_asics_have_same_info()
        NvueGeneralCli.save_config(engines.dut)

    with allure.step('Rebooting the dut after image installation'):
        logging.info("Rebooting dut")
        res, duration = OperationTime.save_duration('reboot with new user FW', '',
                                                    test_name, system.reboot.action_reboot)
        OperationTime.verify_operation_time(duration, 'reboot with new user FW').verify_result()

    return res


def get_original_fw_path(engines, original_fw):
    fw_dir = "/auto/sw_system_project/MLNX_OS_INFRA/mlnx_os2/sx_mlnx_fw/"
    orig_fw_file = engines[NvosConst.SONIC_MGMT].run_cmd("ls {}| grep {}".format(fw_dir, original_fw))
    fw_path = fw_dir + orig_fw_file
    logger.info(" original fw path is: {}".format(fw_path))
    return fw_path


def verify_field_value_in_output_for_each_asic(output_dictionary, field, value):
    ValidationTool.verify_field_value_in_output(output_dictionary, field, value).verify_result()


def validate_all_asics_have_same_info():
    show_output = get_asic_dict(Fae())
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(show_output).get_returned_value()
    assert output_dictionary and len(output_dictionary.keys()) > 0, "asic list is empty"

    if len(output_dictionary.keys()) > 1:
        with allure.step("Validate all the ASICs have the same info"):
            logging.info("Validate all the ASICs have the same info")
            asic_info = list(output_dictionary.values())[0]
            for asic in output_dictionary.keys():
                assert asic_info == output_dictionary[asic], "ASICs are different"


def verify_firmware_with_platform_and_fae_cmd(platform, fae, installed_fw, actual_fw):
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.asic.show()).get_returned_value()
    verify_field_value_in_output_for_each_asic(output_dictionary, "actual-firmware", actual_fw)
    asic_dictionary = get_asic_dict(fae)
    for asic in asic_dictionary:
        verify_field_value_in_output_for_each_asic(asic_dictionary[asic], "installed-firmware", installed_fw)
        verify_field_value_in_output_for_each_asic(asic_dictionary[asic], "actual-firmware", actual_fw)

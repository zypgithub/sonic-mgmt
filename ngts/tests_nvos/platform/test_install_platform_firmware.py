import logging
import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import NvosConst, PlatformConsts, HealthConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_constants.constants_nvos import OperationTimeConsts
from ngts.tests_nvos.helpers import redmine_helpers
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.Devices.IbDevice import NvLinkSwitch
from typing import Tuple

logger = logging.getLogger()


# XXX: remove after the bug is closed: https://redmine.mellanox.com/issues/4221742
@pytest.fixture(scope='module', autouse=True)
def _update_install_threshold(devices):
    if isinstance(devices.dut, NvLinkSwitch) and redmine_helpers.is_bug_active(4221742):
        OperationTimeConsts.THRESHOLDS['reboot with default FW installation'] *= 2
        OperationTimeConsts.THRESHOLDS['reboot with new user FW'] *= 2


@pytest.mark.checklist
@pytest.mark.platform
@pytest.mark.timeout(30 * MINUTE, func_only=True)
def test_install_platform_firmware(engines, devices, test_name, topology_obj, nv_command, clear_asic_files):
    """
    Install platform firmware test

    Test flow:
    1. Install platform firmware and reboot
    2. Verify the firmware is updated successfully to new version
    3. Change fw-source to default and reboot
    4. Verify the firmware is updated successfully to embedded version
    """
    component_name = 'asic'
    test_image_name = "test_fw_asic.mfa"
    fw_has_changed = False
    fw_file, filename, version_name = BmcTool.get_fw_component_version_latest(component_name)

    with allure.step("Check actual firmware value"):
        asic_dictionary = get_asic_dict(nv_command.platform)
        first_asic_name = list(asic_dictionary.keys())[0]
        actual_firmware = asic_dictionary[first_asic_name]["actual-firmware"]
        logging.info("Original actual firmware - " + actual_firmware)
        nv_command.system.validate_health_status(HealthConsts.OK)

    try:
        with allure.step("Install system firmware file - " + fw_file):
            with allure.step("fetch firmware file to switch"):
                player_engine = engines['sonic_mgmt']
                scp_path = 'scp://{}:{}@{}'.format(player_engine.username, player_engine.password, player_engine.ip)
                nv_command.platform.firmware.asic.action_fetch(fw_file, base_url=scp_path).verify_result()
                fetched_image_file = nv_command.platform.firmware.asic.files.file_name[filename]
                fetched_image_file.action_rename(test_image_name, rewrite_file_name=False).verify_result()

            with allure.step("Install firmware and verify"):
                nv_command.platform.firmware.asic.set(PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_CUSTOM, apply=True)
                NvueGeneralCli.save_config(engines.dut)
                install_new_image_fw(nv_command.platform, test_name, test_image_name)
            with allure.step('Verify the firmware installed successfully'):
                verify_firmware_with_platform_cmd(nv_command.platform, version_name)
                nv_command.system.validate_health_status(HealthConsts.OK)
                fw_has_changed = True
    finally:
        with allure.step("cleanup steps"):
            with allure.step("Install original system firmware file"):
                nv_command.platform.firmware.asic.set(PlatformConsts.FW_SOURCE, PlatformConsts.FW_SOURCE_DEFAULT, apply=True)
                NvueGeneralCli.save_config(engines.dut)

            install_default_image_fw(nv_command.system, test_name, fw_has_changed)

        with allure.step('Verify the firmware installed successfully'):
            verify_firmware_with_platform_cmd(nv_command.platform, actual_firmware)
            validate_all_asics_have_same_info(nv_command.platform)
            nv_command.system.validate_health_status(HealthConsts.OK)


def get_version_and_file_name(device) -> Tuple[str, str]:
    return getattr(device.asic_version, 'version'), getattr(device.asic_version, 'filename')


def get_asic_dict(platform):
    show_output = OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.show()).get_returned_value()
    asic_dictionary = {k: v for k, v in show_output.items() if PlatformConsts.FW_ASIC in k and 'EROT' not in k}
    assert asic_dictionary and len(asic_dictionary.keys()) > 0, "asic list is empty"
    return asic_dictionary


def install_new_image_fw(platform, test_name, fw_file_name):
    with allure.step('new fw image installation'):
        res_obj, duration = OperationTime.save_duration('reboot with new user FW', '', test_name,
                                                        platform.firmware.asic.files.file_name[fw_file_name].action_file_install_with_reboot)
    with allure.step('Verify operation time'):
        OperationTime.verify_operation_time(duration, 'install user FW').verify_result()

    return res_obj


def install_default_image_fw(system, test_name, fw_has_changed):
    with allure.step('Rebooting the dut after image installation'):
        logging.info("Rebooting dut")
        if fw_has_changed:
            res_obj, duration = OperationTime.save_duration('reboot with default FW installation', '', test_name,
                                                            system.reboot.action_reboot, system_is_ready_timeout=PlatformConsts.TIMEOUT_AFTER_FW_INSTALL)
            res = res_obj
            with allure.step('Verify operation time'):
                OperationTime.verify_operation_time(duration, 'reboot with default FW installation').verify_result()
        else:
            res = system.reboot.action_reboot()

        return res


def get_original_fw_path(engines, original_fw):
    fw_dir = "/auto/sw_system_project/MLNX_OS_INFRA/mlnx_os2/sx_mlnx_fw/"
    orig_fw_file = engines[NvosConst.SONIC_MGMT].run_cmd("ls {}| grep {}".format(fw_dir, original_fw))
    fw_path = fw_dir + orig_fw_file
    logger.info(" original fw path is: {}".format(fw_path))
    return fw_path


def verify_field_value_in_output_for_each_asic(output_dictionary, field, value):
    ValidationTool.verify_field_value_in_output(output_dictionary, field, value).verify_result()


def validate_all_asics_have_same_info(platform):
    show_output = get_asic_dict(platform)
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(show_output).get_returned_value()
    assert output_dictionary and len(output_dictionary.keys()) > 0, "asic list is empty"

    if len(output_dictionary.keys()) > 1:
        with allure.step("Validate all the ASICs have the same info"):
            logging.info("Validate all the ASICs have the same info")
            asic_info = list(output_dictionary.values())[0]
            for asic in output_dictionary.keys():
                assert asic_info == output_dictionary[asic], "ASICs are different"


def verify_firmware_with_platform_cmd(platform, actual_fw):
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(platform.firmware.asic.show()).get_returned_value()
    verify_field_value_in_output_for_each_asic(output_dictionary, "actual-firmware", actual_fw)
    asic_dictionary = get_asic_dict(platform)
    for asic in asic_dictionary:
        verify_field_value_in_output_for_each_asic(asic_dictionary[asic], "actual-firmware", actual_fw)

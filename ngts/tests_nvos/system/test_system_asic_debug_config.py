import pytest
import logging
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ActionConsts, HealthConsts


logger = logging.getLogger(__name__)


@pytest.mark.asic_debug_config
@pytest.mark.system
def test_asic_debug_config_positive(engines, devices, nv_command):
    """
    Test flow:
        1. Check default values for asic-debug-config output
        2. Download positive asic-debug-config and verify output
        3. Set next asic-debug-config yaml and verify output
        4. Perform reboot and verify asic-debug-config applied
        5. Unset asic-debug-config, reboot system, check config not applied
        6. Cleanup
    """
    system = nv_command.system

    with allure.step("Check default values for asic-debug-config output"):
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.asic_debug_config.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.CURRENT_ASIC_DEBUG_CONFIG, SystemConsts.NA).verify_result()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NEXT_ASIC_DEBUG_CONFIG, SystemConsts.NA).verify_result()

    with allure.step('Download positive asic-debug-config and verify output'):
        _download_asic_debug_config(system, SystemConsts.PASS_ASIC_DEBUG_CONFIG)
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.asic_debug_config.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.CURRENT_ASIC_DEBUG_CONFIG, SystemConsts.NA).verify_result()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NEXT_ASIC_DEBUG_CONFIG, SystemConsts.NA).verify_result()
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.asic_debug_config.show('files')).get_returned_value()
        ValidationTool.verify_expected_output(output_dictionary, SystemConsts.PASS_ASIC_DEBUG_CONFIG).verify_result()

    with allure.step("Set next asic-debug-config yaml and verify output"):
        system.asic_debug_config.set(SystemConsts.NEXT_ASIC_DEBUG_CONFIG, SystemConsts.PASS_ASIC_DEBUG_CONFIG)
        NvueGeneralCli.apply_config(engines.dut, ask_for_confirmation=True)
        NvueGeneralCli.save_config(engines.dut)

        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.asic_debug_config.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.CURRENT_ASIC_DEBUG_CONFIG, SystemConsts.NA).verify_result()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NEXT_ASIC_DEBUG_CONFIG, SystemConsts.PASS_ASIC_DEBUG_CONFIG).verify_result()

    with allure.step("Try to delete config file, when it already set"):
        system.asic_debug_config.action(ActionConsts.DELETE,
                                        additional_params={'files': f'{SystemConsts.PASS_ASIC_DEBUG_CONFIG}'}).verify_result(should_succeed=False)

    with allure.step("Perform reboot and verify asic-debug-config applied"):
        with allure.step("Perform system reboot"):
            system.reboot.action_reboot(params='force').verify_result()

        with allure.step("Verify asic-debug-config success after reboot"):
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.asic_debug_config.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.STATUS_ASIC_DEBUG_CONFIG, SystemConsts.SUCCESS_STATUS_ASIC_DEBUG_CONFIG).verify_result()
            ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.CURRENT_ASIC_DEBUG_CONFIG, SystemConsts.PASS_ASIC_DEBUG_CONFIG).verify_result()
            ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NEXT_ASIC_DEBUG_CONFIG, SystemConsts.PASS_ASIC_DEBUG_CONFIG).verify_result()

        with allure.step("Check system logs"):
            show_output = system.log.file.show_log(param="| grep asic-debug-config")
            ValidationTool.verify_expected_output(show_output, 'asic-debug-config').verify_result()

        with allure.step("Validate asic-debug-config log file"):
            _validate_log_file(engines, string_to_validate='asic_debug_config_init')

    with allure.step("Unset asic-debug-config, reboot system, check config not applied"):
        with allure.step("Unset asic debug config"):
            system.asic_debug_config.unset()
            NvueGeneralCli.apply_config(engines.dut, ask_for_confirmation=True)
            NvueGeneralCli.save_config(engines.dut)

        with allure.step("Perform system reboot"):
            system.reboot.action_reboot(params='force').verify_result()

        with allure.step("Check config not applied after reboot"):
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.asic_debug_config.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.CURRENT_ASIC_DEBUG_CONFIG, SystemConsts.NA).verify_result()
            ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NEXT_ASIC_DEBUG_CONFIG, SystemConsts.NA).verify_result()

    with allure.step("Cleanup for asic debug config"):
        system.asic_debug_config.action(ActionConsts.DELETE,
                                        additional_params={'files': f'{SystemConsts.PASS_ASIC_DEBUG_CONFIG}'})

        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
            system.asic_debug_config.show('files')).get_returned_value()
        assert SystemConsts.PASS_ASIC_DEBUG_CONFIG not in output_dictionary, 'config file not deleted'


@pytest.mark.asic_debug_config
@pytest.mark.system
def test_asic_debug_config_positive_fae(engines, devices, nv_command):
    """
    Test flow:
        1. Check default values
        2. Download and fae run passing config file
        3. Check values after action run fae command
        4. Cleanup
    """
    system = nv_command.system
    fae_system = nv_command.fae.system

    with allure.step("Check default values"):
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
            system.asic_debug_config.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.CURRENT_ASIC_DEBUG_CONFIG, SystemConsts.NA).verify_result()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.NEXT_ASIC_DEBUG_CONFIG, SystemConsts.NA).verify_result()

    with allure.step("Download config file"):
        _download_asic_debug_config(system, SystemConsts.PASS_ASIC_DEBUG_CONFIG)

    with allure.step("Run nv action run fae asic-debug config"):
        fae_system.asic_debug_config.action(ActionConsts.RUN, additional_params={'files': f'{SystemConsts.PASS_ASIC_DEBUG_CONFIG}'})

    with allure.step("Check values after action run fae command"):
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
            system.asic_debug_config.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.STATUS_ASIC_DEBUG_CONFIG,
                                                    SystemConsts.SUCCESS_STATUS_ASIC_DEBUG_CONFIG).verify_result()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.CURRENT_ASIC_DEBUG_CONFIG,
                                                    SystemConsts.PASS_ASIC_DEBUG_CONFIG).verify_result()

    with allure.step("Cleanup for asic debug config"):
        system.asic_debug_config.action(ActionConsts.DELETE,
                                        additional_params={'files': f'{SystemConsts.PASS_ASIC_DEBUG_CONFIG}'})

        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
            system.asic_debug_config.show('files')).get_returned_value()
        assert SystemConsts.PASS_ASIC_DEBUG_CONFIG not in output_dictionary, 'config file not deleted'


@pytest.mark.asic_debug_config
@pytest.mark.system
def test_asic_debug_config_negative(engines, devices, nv_command):
    """
    Test flow:
        1. Download not yaml config, should fail
        2. Download yaml config, without values inside
        3. Download yaml config with wrong register
        4. Download yaml config with wrong version
        5. Check logs
        6. Check health status is OK
    """
    system = nv_command.system
    fae_system = nv_command.fae.system

    with allure.step("Download negative not a yaml config file"):
        _download_asic_debug_config(system, SystemConsts.NOT_YAML_ASIC_DEBUG_CONFIG,
                                    expected_output='no asic-debug-config section found in script', should_succeed=False)

    with allure.step("Download yaml config file without any fields, values inside"):
        _download_asic_debug_config(system, SystemConsts.YAML_WITHOUT_FIELDS,
                                    expected_output='no asic-debug-config section found in script', should_succeed=False)

    with allure.step("Download yaml config file with wrong register"):
        _download_asic_debug_config(system, SystemConsts.FAIL_ASIC_DEBUG_CONFIG_WRONG_REGISTER)

    with allure.step("Run asic-debug-config with wrong register"):
        fae_system.asic_debug_config.action(ActionConsts.RUN,
                                            additional_params={'files': f'{SystemConsts.FAIL_ASIC_DEBUG_CONFIG_WRONG_REGISTER}'})

    with allure.step("Verify asic-debug-config failed"):
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
            system.asic_debug_config.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(output_dictionary, SystemConsts.STATUS_ASIC_DEBUG_CONFIG,
                                                    SystemConsts.FAILED_STATUS_ASIC_DEBUG_CONFIG).verify_result()

    with allure.step("Cleanup for asic debug config"):
        system.asic_debug_config.action(ActionConsts.DELETE,
                                        additional_params={'files': f'{SystemConsts.FAIL_ASIC_DEBUG_CONFIG_WRONG_REGISTER}'})

        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
            system.asic_debug_config.show('files')).get_returned_value()
        assert SystemConsts.FAIL_ASIC_DEBUG_CONFIG_WRONG_REGISTER not in output_dictionary, 'config file not deleted'

    with allure.step("Download yaml config file without any fields, values inside"):
        _download_asic_debug_config(system, SystemConsts.FAIL_ASIC_DEBUG_CONFIG_WRONG_VERSION,
                                    expected_output='is not compatible with script version', should_succeed=False)

    with allure.step("Check logs"):
        show_output = system.log.file.show_log(param="| grep asic-debug-config")
        ValidationTool.verify_expected_output(show_output, SystemConsts.ASIC_DEBUG_CONFIG_ERROR).verify_result()

    with allure.step("Check system status is OK"):
        system.validate_health_status(HealthConsts.OK)


def _download_asic_debug_config(system, yaml='', expected_output='', should_succeed=True):
    path = f'{SystemConsts.VERIFICATION_ASIC_DEBUG_PATH}/{yaml}'
    system.asic_debug_config.action_fetch(path).verify_result(should_succeed=should_succeed, expected_value=expected_output)


def _validate_log_file(engines, string_to_validate=''):
    output = engines.dut.run_cmd(f'cat {SystemConsts.ASIC_DEBUG_CONFIG_LOG_FILE} | grep "{string_to_validate}"')
    assert string_to_validate in output, 'String not in asic-debug-config log'

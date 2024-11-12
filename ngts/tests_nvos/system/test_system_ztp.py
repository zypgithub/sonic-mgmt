import pytest
import logging
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from retry import retry
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


@pytest.mark.ztp
@pytest.mark.system
def test_show_ztp_command(engines, devices, serial_engine):
    """
    Test flow:
        1. Check default ztp values
        2. Validate ztp logs with nv show system log command and with serial connection
        3. Check ztp log file exist, ztp logs inside
        4. Config save and check ztp go to inactive
        5. Config save enabled, verify changes
        6. Ztp unset and verify values
    """
    system = System(None)
    try:
        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES)

        with allure.step("Run nv show system log command and check ztp logs inside"):
            show_output = system.log.show_log(param="| grep ztp")
            ValidationTool.verify_expected_output(show_output, 'ztp').verify_result()

        with allure.step("Run nv show system log command and check ztp logs inside"):
            serial_engine.serial_engine.expect("ztp", timeout=30)

        with allure.step("Check ztp log file exist"):
            wc_output = engines.dut.run_cmd(f'wc -c {SystemConsts.ZTP_DEFAULT_LOG_FILE}')
            assert SystemConsts.ZTP_DEFAULT_LOG_FILE in wc_output, 'ZTP log file not exist'

        with allure.step("Save configuration"):
            NvueGeneralCli.save_config(engines.dut)

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS,
                                              SystemConsts.ZTP_AFTER_CONFIG_SAVE_VALUES)

        with allure.step("Run nv set system ztp config-save enabled"):
            system.ztp.set('config-save', 'enabled').verify_result(True)
            NvueGeneralCli.apply_config(engines.dut)

        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp()

        with allure.step("Run show ztp after save and verify values"):
            system_ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()

            with allure.step("Verify config save value"):
                ValidationTool.verify_field_value_in_output(system_ztp_output, 'config-save', 'enabled').verify_result()

        with allure.step("Run nv unset system ztp"):
            system.ztp.unset().verify_result(True)
            NvueGeneralCli.apply_config(engines.dut)

        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES)

    except Exception as e:
        logger.info("Received Exception during test_show_ztp_command: {}".format(e))
        raise e
    finally:
        system.ztp.action_abort_ztp()
        engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')


@pytest.mark.ztp
@pytest.mark.system
def test_ztp_json(engines, devices):
    """
    Test flow:
        1. Check default ztp values
        2. Download bad format json and check error in the log
        3. Run positive json file and check status changed
        4. Run negative ping and check ztp failed
        5. Run json with halt-on-failure param
        6. Run json with restart-on-failure param
    """
    system = System(None)

    try:
        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES)

        with allure.step("Download dummy json file"):
            _download_ztp_json_config(engines, SystemConsts.DUMMY_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

            with allure.step("Validate ztp error in ztp log file"):
                _validate_ztp_log_file(
                    engines, string_to_validate='occurred while processing ZTP JSON file /host/ztp/ztp_data_local.json')

        with allure.step("Download positive json file"):
            _download_ztp_json_config(engines, SystemConsts.POSITIVE_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Download negative ping json file"):
            _download_ztp_json_config(engines, SystemConsts.NEGATIVE_PING_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_FAILED)

        with allure.step("Download json file with halt on failure parameter"):
            _download_ztp_json_config(engines, SystemConsts.NEGATIVE_HALT_ON_FAILURE_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                _wait_until_ztp_step_status(system, '01-connectivity-check', SystemConsts.ZTP_STATUS_FAILED)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_FAILED)

        with allure.step("Download json file with restart on failure parameter"):
            _download_ztp_json_config(engines, SystemConsts.NEGATIVE_RESTART_ON_FAILURE_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_FAILED)

            with allure.step("Run nv show system log command and check ztp logs inside"):
                show_output = system.log.show_log(param="| grep ztp")
                ValidationTool.verify_expected_output(show_output,
                                                      'Waiting for 300 seconds before restarting ZTP').verify_result()

        with allure.step("Run nv abort run system ztp and delete json file"):
            system.ztp.action_abort_ztp()
            engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')

    except Exception as e:
        logger.info("Received Exception during test_ztp_json: {}".format(e))
        raise e
    finally:
        system.ztp.action_abort_ztp()
        engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')


@pytest.mark.ztp
@pytest.mark.system
def test_ztp_image(engines, devices):
    """
    Test flow:
        1. Check default ztp values
        2. Apply image json file
        3. Verify image installed
        4. Verify image uninstalled
    """
    system = System(None)

    try:
        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES)

        with allure.step("Download image json file"):
            _download_ztp_json_config(engines, SystemConsts.IMAGE_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

            with allure.step("Check ztp status for image test"):
                with allure.step("Check ztp status for download and install image"):
                    _wait_until_ztp_step_status(system, '01-image', SystemConsts.ZTP_STATUS_SUCCESS, tries=100, delay=5)
                    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
                        system.image.show()).get_returned_value()
                    assert output_dictionary['current'] == output_dictionary['next'], 'Image not installed'

                with allure.step("Check ztp status for uninstall image"):
                    _wait_until_ztp_step_status(system, '02-image', SystemConsts.ZTP_STATUS_SUCCESS)
                    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
                        system.image.show()).get_returned_value()
                    assert output_dictionary['current'] == output_dictionary['next'], 'Image not uninstalled'

    except Exception as e:
        logger.info("Received Exception during test_ztp_image: {}".format(e))
        raise e
    finally:
        system.ztp.action_abort_ztp()
        engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')


@pytest.mark.ztp
@pytest.mark.system
def test_ztp_startup_file_commands_list(engines, devices):
    """
    Test flow:
        1. Check default ztp values
        2. Download json file with dummy ip inside
        3. Set description to random interface
        4. Apply json file with clear config false and check interface description exist
        5. Apply json file with config save true
        6. Apply json file with clear config true and check interface description empty
    """
    system = System(None)
    empty_description = ""
    abcd_description = "abcd"
    selected_port = Tools.RandomizationTool.select_random_port().get_returned_value()
    selected_port.update_output_dictionary()
    TestToolkit.update_tested_ports([selected_port])

    try:
        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES)

        with allure.step("Download json file with wrong ip"):
            _download_ztp_json_config(engines, SystemConsts.STARTUP_FILE_WRONG_IP)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-startup-file', SystemConsts.ZTP_STATUS_FAILED)

        with allure.step('Run show command on selected port and verify that description field is set'):
            selected_port.interface.set(NvosConst.DESCRIPTION, abcd_description, apply=True).verify_result()
            selected_port.update_output_dictionary()
            _validate_interface_description_field(selected_port, abcd_description, True)

        with allure.step("Download clear config false json file"):
            _download_ztp_json_config(engines, SystemConsts.STARTUP_FILE_CLEAR_CONFIG_FALSE)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-startup-file', SystemConsts.ZTP_STATUS_SUCCESS)

                with allure.step('Check interface description exist'):
                    selected_port.update_output_dictionary()
                    _validate_interface_description_field(selected_port, abcd_description, True)

        with allure.step("Download config save true startup json file"):
            _download_ztp_json_config(engines, SystemConsts.STARTUP_FILE_CLEAR_CONFIG_TRUE)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-startup-file', SystemConsts.ZTP_STATUS_SUCCESS)

                with allure.step('Check interface description exist'):
                    selected_port.update_output_dictionary()
                    _validate_interface_description_field(selected_port, empty_description, False)

        with allure.step("Download clear config true startup json file"):
            _download_ztp_json_config(engines, SystemConsts.STARTUP_FILE_SAVE_CONFIG_TRUE)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-startup-file', SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Download clear config true startup json file"):
            _download_ztp_json_config(engines, SystemConsts.STARTUP_FILE_INTERACTIVE_COMMANDS)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-startup-file', SystemConsts.ZTP_STATUS_FAILED)

        with allure.step("Run nv abort run system ztp and delete json file"):
            system.ztp.action_abort_ztp()
            engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')
            system.ztp.action_run_ztp()

    except Exception as e:
        logger.info("Received Exception during test_ztp_startup_file_commands_list: {}".format(e))
        raise e
    finally:
        system.ztp.action_abort_ztp()
        engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')


@pytest.mark.ztp
@pytest.mark.system
def test_ztp_connectivity_check(engines, devices):
    """
    Test flow:
        1. Check default values for ztp
        2. Apply json file with ipv4 and ipv6
        3. Apply json file with dummy ipv4, ipv6
    """
    system = System(None)

    try:
        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES)

        with allure.step("Download ping ipv4 and ipv6 json file"):
            _download_ztp_json_config(engines, SystemConsts.CONNECTIVITY_IPV4_IPV6)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)
                    _wait_until_ztp_step_status(system, '01-connectivity-check', SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Download negative ip json file"):
            _download_ztp_json_config(engines, SystemConsts.NEGATIVE_CONNECTIVITY)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-connectivity-check', SystemConsts.ZTP_STATUS_FAILED)
                    _wait_until_ztp_step_status(system, '02-commands-list', SystemConsts.ZTP_STATUS_SUCCESS)
                    _wait_until_ztp_step_status(system, '03-connectivity-check', SystemConsts.ZTP_STATUS_FAILED)
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_FAILED)

    except Exception as e:
        logger.info("Received Exception during test_ztp_connectivity_check: {}".format(e))
        raise e
    finally:
        system.ztp.action_abort_ztp()
        engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')


@pytest.mark.ztp
@pytest.mark.system
def test_ztp_json_complex(engines, devices):
    """
    Test flow:
        1. Check default values for ztp
        2. Apply complex json file
        3. Validate all ztp stages
    """
    system = System(None)

    try:
        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES)

        with allure.step("Download complex json file"):
            _download_ztp_json_config(engines, SystemConsts.COMPLEX)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-image', SystemConsts.ZTP_STATUS_SUCCESS, tries=90)
                    _wait_until_ztp_step_status(system, '02-image', SystemConsts.ZTP_STATUS_SUCCESS)
                    _wait_until_ztp_step_status(system, '03-connectivity-check', SystemConsts.ZTP_STATUS_SUCCESS)
                    _wait_until_ztp_step_status(system, '04-connectivity-check', SystemConsts.ZTP_STATUS_FAILED)
                    _wait_until_ztp_step_status(system, '05-startup-file', SystemConsts.ZTP_STATUS_FAILED)
                    _wait_until_ztp_step_status(system, '06-connectivity-check', SystemConsts.ZTP_STATUS_SUCCESS)
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_FAILED)

    except Exception as e:
        logger.info("Received Exception during test_ztp_json_complex: {}".format(e))
        raise e
    finally:
        system.ztp.action_abort_ztp()
        engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')
        system.ztp.action_run_ztp()


def _download_ztp_json_config(engines, json=''):
    engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')
    return engines.dut.run_cmd(
        f'sudo curl {SystemConsts.HTTP_SERVER}{SystemConsts.VERIFICATION_ZTP_PATH}{json} '
        f'-o /host/ztp/ztp_data_local.json')


def _validate_ztp_log_file(engines, string_to_validate=''):
    output = engines.dut.run_cmd(f'cat /var/log/ztp.log | grep "{string_to_validate}"')
    assert string_to_validate in output, 'String not in ztp log'


@retry(Exception, tries=30, delay=2)
def _wait_until_ztp_status(system, ztp_status=''):
    with allure.step("Waiting for ztp status changed to status {}".format(ztp_status)):
        ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()
        assert ztp_output['status'] == ztp_status, f'ztp status not changed to {ztp_status}'


def _wait_until_ztp_step_status(system, ztp_step='', ztp_status='', tries=30, delay=2):
    @retry(Exception, tries=tries, delay=delay)
    def _retry_decorator(system_obj, ztp_step_name='', ztp_status_name=''):
        with allure.step("Waiting for ztp status changed to status {}".format(ztp_status_name)):
            ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system_obj.ztp.show()).get_returned_value()
            assert ztp_output['stage'][ztp_step_name]['status'] == ztp_status_name, \
                f'ztp status not changed to {ztp_status_name}'
    _retry_decorator(system, ztp_step, ztp_status)


def _validate_interface_description_field(selected_port, description_value, should_be_equal=True):
    with allure.step('Check that interface description field matches the expected value'):
        output_dictionary = selected_port.show_output_dictionary
        if NvosConst.DESCRIPTION in output_dictionary.keys():
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary, NvosConst.DESCRIPTION,
                                                              description_value).verify_result(should_be_equal)


@retry(Exception, tries=30, delay=3)
def _wait_until_ztp_values_fields_changed(system, ztp_output_fields, ztp_output_values):
    with allure.step("Run show ztp and verify default values"):
        system_ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()

    with allure.step("Verify default values and fields"):
        ValidationTool.validate_fields_values_in_output(ztp_output_fields, ztp_output_values,
                                                        system_ztp_output).verify_result()

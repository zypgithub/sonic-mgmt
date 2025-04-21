import pytest
import logging
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.nvos_constants.constants_nvos import OutputFormat, ClusterAppsLogLevels
from retry import retry
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SecureBootTool import SecureBootTool

logger = logging.getLogger()

NMX_CONTROLLER = 'nmx-controller'
NMX_TELEMETRY = 'nmx-telemetry'


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
            system.ztp.action_run_ztp().verify_result()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES, tries=5, delay=2)

        with allure.step("Run nv show system log command and check ztp logs inside"):
            show_output = system.log.file.show_log(param="| grep ztp")
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
            system.ztp.action_run_ztp().verify_result()

        with allure.step("Run show ztp after save and verify values"):
            system_ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()

            with allure.step("Verify config save value"):
                ValidationTool.verify_field_value_in_output(system_ztp_output, 'config-save', 'enabled').verify_result()

        with allure.step("Run nv unset system ztp"):
            system.ztp.unset().verify_result(True)
            NvueGeneralCli.apply_config(engines.dut)

        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp().verify_result()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES)

    except Exception as e:
        logger.info("Received Exception during test_show_ztp_command: {}".format(e))
        raise e
    finally:
        _ztp_cleanup(engines, system)


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
            system.ztp.action_run_ztp().verify_result()
            _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES, tries=5, delay=2)

        with allure.step("Download dummy json file"):
            _download_ztp_json_config(engines, SystemConsts.DUMMY_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

            with allure.step("Validate ztp error in ztp log file"):
                _validate_ztp_log_file(
                    engines, string_to_validate='occurred while processing ZTP JSON file /host/ztp/ztp_data_local.json')

        with allure.step("Download positive json file"):
            _download_ztp_json_config(engines, SystemConsts.POSITIVE_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Download negative ping json file"):
            _download_ztp_json_config(engines, SystemConsts.NEGATIVE_PING_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_FAILED)

        with allure.step("Download json file with halt on failure parameter"):
            _download_ztp_json_config(engines, SystemConsts.NEGATIVE_HALT_ON_FAILURE_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                _wait_until_ztp_step_status(system, '01-connectivity-check', SystemConsts.ZTP_STATUS_FAILED)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_FAILED)

        with allure.step("Download json file with restart on failure parameter"):
            _download_ztp_json_config(engines, SystemConsts.NEGATIVE_RESTART_ON_FAILURE_JSON)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_FAILED)

            with allure.step("Run nv show system log command and check ztp logs inside"):
                show_output = system.log.file.show_log(param="| grep ztp")
                ValidationTool.verify_expected_output(show_output,
                                                      'Waiting for 300 seconds before restarting ZTP').verify_result()

        with allure.step("Run nv abort run system ztp and delete json file"):
            system.ztp.action_abort_ztp().verify_result()
            engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')

    except Exception as e:
        logger.info("Received Exception during test_ztp_json: {}".format(e))
        raise e
    finally:
        _ztp_cleanup(engines, system)


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
            system.ztp.action_run_ztp().verify_result()
            _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES, tries=5, delay=2)

        with allure.step("Download image json file"):
            image_json = devices.dut.ztp_dev_json if SecureBootTool.is_dev_system(
                TestToolkit.engines.dut) else devices.dut.ztp_prod_json
            _download_ztp_json_config(engines, image_json)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

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
        _ztp_cleanup(engines, system)


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
            system.ztp.action_run_ztp().verify_result()
            _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES, tries=5, delay=2)

        with allure.step("Download json file with wrong ip"):
            _download_ztp_json_config(engines, SystemConsts.STARTUP_FILE_WRONG_IP)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

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
                system.ztp.action_run_ztp().verify_result()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-startup-file', SystemConsts.ZTP_STATUS_SUCCESS)

                with allure.step('Check interface description exist'):
                    selected_port.update_output_dictionary()
                    _validate_interface_description_field(selected_port, abcd_description, True)

        with allure.step("Download config save true startup json file"):
            _download_ztp_json_config(engines, SystemConsts.STARTUP_FILE_CLEAR_CONFIG_TRUE)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-startup-file', SystemConsts.ZTP_STATUS_SUCCESS)

                with allure.step('Check interface description exist'):
                    selected_port.update_output_dictionary()
                    _validate_interface_description_field(selected_port, empty_description, False)

        with allure.step("Download clear config true startup json file"):
            _download_ztp_json_config(engines, SystemConsts.STARTUP_FILE_SAVE_CONFIG_TRUE)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-startup-file', SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Download clear config true startup json file"):
            _download_ztp_json_config(engines, SystemConsts.STARTUP_FILE_INTERACTIVE_COMMANDS)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_RUNNING)
                    _wait_until_ztp_step_status(system, '01-startup-file', SystemConsts.ZTP_STATUS_FAILED)

        with allure.step("Run nv abort run system ztp and delete json file"):
            system.ztp.action_abort_ztp().verify_result()
            engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')
            system.ztp.action_run_ztp().verify_result()

    except Exception as e:
        logger.info("Received Exception during test_ztp_startup_file_commands_list: {}".format(e))
        raise e
    finally:
        _ztp_cleanup(engines, system)


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
            system.ztp.action_run_ztp().verify_result()
            _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES, tries=5, delay=2)

        with allure.step("Download ping ipv4 and ipv6 json file"):
            _download_ztp_json_config(engines, SystemConsts.CONNECTIVITY_IPV4_IPV6)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

                with allure.step("Check ztp status"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)
                    _wait_until_ztp_step_status(system, '01-connectivity-check', SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Download negative ip json file"):
            _download_ztp_json_config(engines, SystemConsts.NEGATIVE_CONNECTIVITY)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

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
        _ztp_cleanup(engines, system)


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
            system.ztp.action_run_ztp().verify_result()
            _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES, tries=5, delay=2)

        with allure.step("Download complex json file"):
            image_json = devices.dut.ztp_complex_dev_json if SecureBootTool.is_dev_system(
                TestToolkit.engines.dut) else devices.dut.ztp_complex_prod_json
            _download_ztp_json_config(engines, image_json)

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp().verify_result()

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
        _ztp_cleanup(engines, system)


@pytest.mark.ztp
@pytest.mark.system
def test_ztp_nmx_negative(engines, devices, setup_name, has_loopbox, standalone_system):
    """
    Test flow:
        1. Check default values for ztp
        2. Download and run ztp positive json, when cluster is disabled
        3. Download and run ztp json with no exist file, when cluster is disabled
        4. Start cluster
        5. Download and run ztp json with incorrect commands
        6. Stop nmx-controller
        7. Download and run ztp positive json
        8. Stop nmx-telemetry
        9. Download and run positive ztp json
        10. Cleanup
    """
    system = System(None)
    cluster = Cluster()

    try:
        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp().verify_result()
            _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS,
                                                  SystemConsts.ZTP_DEFAULT_VALUES, tries=5, delay=2)

        with allure.step("Download ztp nmx positive command list, cluster disabled"):
            _download_file_and_run_ztp(engines, system, SystemConsts.NMX_POSITIVE_JSON, '1-nmx-commands-list',
                                       SystemConsts.ZTP_STATUS_FAILED, SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Download ztp nmx not exist file"):
            _download_file_and_run_ztp(engines, system, SystemConsts.NMX_NOT_EXIST_FILE_JSON, '1-nmx-commands-list',
                                       SystemConsts.ZTP_STATUS_FAILED, SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Start cluster"):
            ClusterTools.start_cluster(cluster, setup_name)

            with allure.step("Verify cluster enabled"):
                ClusterTools.validate_cluster_enabled(cluster)

        with allure.step("Download ztp nmx json, with incorrect commands inside"):
            _download_file_and_run_ztp(engines, system, SystemConsts.NMX_BAD_COMMANDS, '1-nmx-commands-list',
                                       SystemConsts.ZTP_STATUS_FAILED, SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Disable nmx controller and run positive ztp"):
            ClusterTools.stop_app(cluster, ClusterConsts.NMX_CONTROLLER)

            with allure.step("Download ztp nmx positive, when nmx controller disabled"):
                _download_file_and_run_ztp(engines, system, SystemConsts.NMX_POSITIVE_JSON, '1-nmx-commands-list',
                                           SystemConsts.ZTP_STATUS_FAILED, SystemConsts.ZTP_STATUS_SUCCESS)

            with allure.step("Enable nmx controller"):
                ClusterTools.start_app(cluster, ClusterConsts.NMX_CONTROLLER, has_loopbox, standalone_system)

        with allure.step("Disable nmx telemetry and run positive ztp"):
            ClusterTools.stop_app(cluster, ClusterConsts.NMX_TELEMETRY)

            with allure.step("Download ztp nmx positive, when nmx controller disabled"):
                _download_file_and_run_ztp(engines, system, SystemConsts.NMX_POSITIVE_JSON, '1-nmx-commands-list',
                                           SystemConsts.ZTP_STATUS_FAILED, SystemConsts.ZTP_STATUS_SUCCESS)

    except Exception as e:
        logger.info("Received Exception during test_ztp_json_complex: {}".format(e))
        raise e
    finally:
        ClusterTools.stop_cluster(cluster)
        _ztp_cleanup(engines, system)


@pytest.mark.ztp
@pytest.mark.system
def test_ztp_nmx_positive(engines, devices, setup_name):
    """
    Test flow:
        1. Check default values for ztp
        2. Start cluster
        3. Download and run positive ztp json
        4. Verify changes
        5. Cleanup
    """
    output_format = OutputFormat.json
    system = System(None)
    cluster = Cluster()

    try:
        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp().verify_result()
            _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS,
                                                  SystemConsts.ZTP_DEFAULT_VALUES, tries=5, delay=2)

        with allure.step("Start cluster"):
            ClusterTools.start_cluster(cluster, setup_name)

        with allure.step("Download ztp nmx positive command list, cluster enabled"):
            _download_file_and_run_ztp(engines, system, SystemConsts.NMX_POSITIVE_JSON, '1-nmx-commands-list',
                                       SystemConsts.ZTP_STATUS_SUCCESS, SystemConsts.ZTP_STATUS_SUCCESS)

            with allure.step("Verify log level of apps changed"):
                ClusterTools.verify_log_level(ClusterAppsLogLevels.INFO, ClusterConsts.NMX_CONTROLLER,
                                              output_format, cluster)
                ClusterTools.verify_log_level(ClusterAppsLogLevels.INFO, ClusterConsts.NMX_TELEMETRY,
                                              output_format, cluster)

    except Exception as e:
        logger.info("Received Exception during test_ztp_json_complex: {}".format(e))
        raise e
    finally:
        ClusterTools.stop_cluster(cluster)
        _ztp_cleanup(engines, system)


@pytest.mark.ztp
@pytest.mark.system
@pytest.mark.timeout(6 * MINUTE, func_only=True)
def test_ztp_provisioning_script_negative(engines, devices):
    """
    Test flow:
        1. Check default values for ztp
        2. Apply json file with script with interactive commands
        3. Apply json file with negative provisioning script
        4. Apply json file with script bad extension
        5. Apply json file with loop and timeout
    """
    system = System(None)

    try:
        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp().verify_result()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES)

        with allure.step("Download provisioning script with interactive commands"):
            _download_file_and_run_ztp(engines, system, SystemConsts.SCRIPT_INTERACTIVE,
                                       '01-provisioning-script', SystemConsts.ZTP_STATUS_FAILED)

        with allure.step("Download negative provisioning script"):
            _download_file_and_run_ztp(engines, system, SystemConsts.SCRIPT_NEGATIVE,
                                       '01-provisioning-script', SystemConsts.ZTP_STATUS_FAILED)

        with allure.step("Download provisioning with bad extension"):
            _download_file_and_run_ztp(engines, system, SystemConsts.SCRIPT_BAD_FILE,
                                       '01-provisioning-script', SystemConsts.ZTP_STATUS_FAILED)

        with allure.step("Download provisioning script with loop and timeout"):
            _download_file_and_run_ztp(engines, system, SystemConsts.SCRIPT_LOOP_TIMEOUT,
                                       '01-provisioning-script', SystemConsts.ZTP_STATUS_FAILED)

    except Exception as e:
        logger.info("Received Exception during test_ztp_connectivity_check: {}".format(e))
        raise e
    finally:
        system.ztp.action_abort_ztp().verify_result()
        engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')
        system.ztp.action_run_ztp().verify_result()


def _ztp_cleanup(engines, system):
    system.ztp.action_abort_ztp().verify_result()
    engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')
    system.ztp.action_run_ztp().verify_result()


@pytest.mark.ztp
@pytest.mark.system
def test_ztp_provisioning_script_positive(engines, devices):
    """
    Test flow:
        1. Check default values for ztp
        2. Apply json file with positive script
        3. Apply json file with python script
    """
    system = System(None)

    try:
        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp().verify_result()

        _wait_until_ztp_values_fields_changed(system, SystemConsts.ZTP_OUTPUT_FIELDS, SystemConsts.ZTP_DEFAULT_VALUES)

        with allure.step("Running positive ztp provisioning script"):
            _download_file_and_run_ztp(engines, system, SystemConsts.SCRIPT_POSITIVE,
                                       '01-provisioning-script', SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Download provisioning python script"):
            _download_file_and_run_ztp(engines, system, SystemConsts.SCRIPT_POSITIVE_PYTHON,
                                       '01-provisioning-script', SystemConsts.ZTP_STATUS_SUCCESS)

    except Exception as e:
        logger.info("Received Exception during test_ztp_connectivity_check: {}".format(e))
        raise e
    finally:
        _ztp_cleanup(engines, system)


def _download_ztp_json_config(engines, json=''):
    engines.dut.run_cmd('sudo rm -f /host/ztp/ztp_data_local.json')
    return engines.dut.run_cmd(
        f'sudo curl {SystemConsts.HTTP_SERVER}{SystemConsts.VERIFICATION_ZTP_PATH}{json} '
        f'-o /host/ztp/ztp_data_local.json')


def _download_file_and_run_ztp(engines, system, file='', step='', step_status_code=SystemConsts.ZTP_STATUS_SUCCESS,
                               ztp_status_code=SystemConsts.ZTP_STATUS_SUCCESS):
    with allure.step("Download json file"):
        _download_ztp_json_config(engines, file)

    with allure.step("Run nv action run system ztp"):
        system.ztp.action_run_ztp().verify_result()

        with allure.step("Check ztp status"):
            _wait_until_ztp_step_status(system, step, step_status_code)
            _wait_until_ztp_status(system, ztp_status_code)


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


def _wait_until_ztp_values_fields_changed(system, ztp_output_fields, ztp_output_values, tries=30, delay=3):
    @retry(Exception, tries=tries, delay=delay)
    def _retry_decorator(system_obj, ztp_step_name='', ztp_status_name=''):
        with allure.step("Run show ztp and verify default values"):
            system_ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()

        with allure.step("Verify default values and fields"):
            ValidationTool.validate_fields_values_in_output(ztp_output_fields, ztp_output_values,
                                                            system_ztp_output).verify_result()

    _retry_decorator(system, ztp_output_fields, ztp_output_values)

import logging
import time
import re
from collections import namedtuple

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import PlatformConsts, IbConsts, ApiType, OutputFormat, SystemConsts, ClusterAppsLogLevels, ClusterConsts, NvosConst
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, NvosConsts

logger = logging.getLogger()

NMX_CONTROLLER = 'nmx-controller'
NMX_TELEMETRY = 'nmx-telemetry'
TELEMETRY_SERVICES = ['nmx-connector', 'ib-telemetry']
CONTROLLER_SERVICES = ['nmxc-sdn', 'nmxc-fib', 'redis']
INITIAL_EXPECTED_APPS = [NMX_CONTROLLER, NMX_TELEMETRY]
NMX_CONTROLLER_CONFIG_FILE_TYPES = ['fm_config', 'sm_config']  # TODO, add 'rdm_config' once bug is fixed  #3982375
NMX_CONTROLLER_STATE_FILE_TYPES = ['conn_info']  # TODO add sm_dump and topology once bug is fixed #3985684
ClusterAppsLogLevelsList = [ClusterAppsLogLevels.DEBUG, ClusterAppsLogLevels.INFO, ClusterAppsLogLevels.NOTICE, ClusterAppsLogLevels.WARNING, ClusterAppsLogLevels.ERROR, ClusterAppsLogLevels.CRITICAL]
NMX_LOG_MESSAGES_TAGS = ['nmxc-sm', 'nmxc-fm', 'nmxc-fib', 'nmxc-gw_api', 'nmxc-rest', 'nmxc-config_daemon']
WAIT_FOR_APPS_RUNNING = 35  # Should be reduced to ~7 once bug is fixed [NVOS - Design] Bug SW #4010133: [Non-Functional ] [NMX] | No immediate NVOS reflection for showing running apps after being started/stopped | Assignee: Chris Yang | Status: Assigned
NMXC_CONN = 'nmxc-conn'
NMXC_CONN_STATE_PER_CLUSTER_STATE = {NvosConst.ENABLED: 'up', NvosConst.DISABLED: 'down'}


class ClusterTools:

    @staticmethod
    def stop_start_app(cluster, engines, devices):
        with allure.step("Stop/Start apps"):
            for app in INITIAL_EXPECTED_APPS:
                with allure.step(f"Validate app {app} is up"):
                    ClusterTools.verify_app_is_up(engines, app)
                    if app == NMX_CONTROLLER:
                        ClusterTools.verify_lid_value(devices)
                        ClusterTools.verify_interface_up(devices)
                with allure.step("Running 'nv show cluster apps running' command and verifying output"):
                    output = OutputParsingTool.parse_show_output_to_dict(
                        cluster.apps.running.show(output_format=OutputFormat.json),
                        output_format=OutputFormat.json).get_returned_value()
                    app_status = output[app]['status']
                    assert app_status == 'ok', f"App {app} status is {app_status} instead of 'ok"
                with allure.step(f"Stop app {app} and validate its down"):
                    cluster.apps.apps_name[app].action_stop_cluster_apps()
                    logger.info("Sleeping for 10 seconds to make sure all services are down")
                    time.sleep(10)
                    # TBD -- once "running" is working, use it to verify app is not running
                    ClusterTools.verify_app_is_down(engines)

                with allure.step(f"Start app again {app} and validate its up"):
                    output = cluster.apps.apps_name[app].action_start_cluster_apps()
                    ClusterTools.wait_for_apps_to_be_in_wanted_state()
                ClusterTools.verify_app_is_up(engines, app)
                if app == NMX_CONTROLLER:
                    ClusterTools.verify_lid_value(devices)
                    ClusterTools.verify_interface_up(devices)
                with allure.step("Running 'nv show cluster apps running' command and verifying output"):
                    output = OutputParsingTool.parse_show_output_to_dict(
                        cluster.apps.running.show(output_format=OutputFormat.json),
                        output_format=OutputFormat.json).get_returned_value()
                    app_status = output[app]['status']
                    assert app_status == 'ok', f"App {app} status is {app_status} instead of 'ok"

            return ResultObj(result=True)

    @staticmethod
    def start_cluster(cluster, output_format):
        with allure.step("Start cluster"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()

            if output[SystemConsts.STATE] == 'disabled':
                cluster.set(op_param_name="state", op_param_value='enabled', apply=True)
                ClusterTools.wait_for_apps_to_be_in_wanted_state()
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=output_format),
                    output_format=output_format).get_returned_value()

            with allure.step("Validate state is enabled"):
                assert output[SystemConsts.STATE] == 'enabled', f"Cluster state is , " \
                    f"{output[SystemConsts.STATE]}, Expected to be: " \
                    f"enabled"
                assert NMXC_CONN in output, f"{NMXC_CONN} was not found in {output}"
                expected_nmxc_state = NMXC_CONN_STATE_PER_CLUSTER_STATE[output[SystemConsts.STATE]]
                assert output[NMXC_CONN] == expected_nmxc_state, f"{NMXC_CONN} state was expected to be {expected_nmxc_state} but instead it was {output[NMXC_CONN]}"

    @staticmethod
    def check_cluster_state(cluster, output_format):
        with allure.step("Check cluster state"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()
            return output[SystemConsts.STATE]

    @staticmethod
    def reverse_cluster_state(cluster, output_format):
        if ClusterTools.check_cluster_state(cluster, output_format) == 'enabled':
            ClusterTools.stop_cluster(cluster, output_format)
        else:
            ClusterTools.start_cluster(cluster, output_format)

    @staticmethod
    def stop_cluster(cluster, output_format):
        with allure.step("Stop cluster"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()

            if output[SystemConsts.STATE] == 'enabled':
                cluster.set(op_param_name="state", op_param_value='disabled', apply=True)
                ClusterTools.wait_for_apps_to_be_in_wanted_state()

            with allure.step("Validate state is disabled"):
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=output_format),
                    output_format=output_format).get_returned_value()
                assert output[SystemConsts.STATE] == 'disabled', f"State state is , " \
                    f"{output[SystemConsts.STATE]}, Expected to be: " \
                    f"disabled"
                assert NMXC_CONN in output, f"{NMXC_CONN} was not found in {output}"
                expected_nmxc_state = NMXC_CONN_STATE_PER_CLUSTER_STATE[output[SystemConsts.STATE]]
                assert output[NMXC_CONN] == expected_nmxc_state, f"{NMXC_CONN} state was expected to be {expected_nmxc_state} but instead it was {output[NMXC_CONN]}"

    @staticmethod
    def verify_app_is_up(engines, app):
        with allure.step("Checking if service is up using docker ps | grep -i nmx"):
            output = engines.dut.run_cmd('docker ps | grep -i nmx')
            assert output != '', f"nmx docker is still down, {output}"
            output = output.split('\n')
            expected_services = CONTROLLER_SERVICES if app == NMX_CONTROLLER else TELEMETRY_SERVICES
            all_services_present = all(any(service in line for line in output) for service in expected_services)
            assert all_services_present, f"Missing services - expected services {expected_services}, actual: {output}"

    @staticmethod
    def verify_app_is_down(engines):
        with allure.step("Checking if service is down using docker ps | grep -i nmx"):
            output = engines.dut.run_cmd('docker ps | grep -i nmx')
            assert output == '', f"nmx docker is still up, {output}"

    @staticmethod
    def verify_lid_value(devices):
        with allure.step("Create an IB object"):
            ib = Ib(None)

        with allure.step('Run nv show ib device command and verify that each field has a value'):
            output = OutputParsingTool.parse_json_str_to_dictionary(ib.device.show()).get_returned_value()

            ValidationTool.verify_all_fields_value_exist_in_output_dictionary(
                output, devices.dut.device_list).verify_result()
            assert len(devices.dut.device_list) == len(output), "Unexpected amount of ib devices.\n" \
                                                                "Expect {} devices:{} \n" \
                                                                "but got {} devices: {}".format(
                len(devices.dut.device_list),
                devices.dut.device_list,
                len(output), output.keys())

            for device in output:
                with allure.step('Run nv show ib device <device-id> command and verify that each field has a value'):
                    dev_output = OutputParsingTool.parse_json_str_to_dictionary(
                        ib.device.show(device)).get_returned_value()

                if IbConsts.DEVICE_ASIC_PREFIX in device:
                    assert dev_output['lid'] > 0, "Invalid number of lid"

    @staticmethod
    def verify_interface_up(devices):
        port_type = devices.dut.switch_type.lower()
        selected_port = Tools.RandomizationTool.select_random_port(requested_ports_logical_state=NvosConsts.LINK_LOG_STATE_ACTIVE).get_returned_value()
        output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
            selected_port.interface.link.show()).get_returned_value()
        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.LINK_STATE,
                                                          expected_value=NvosConsts.LINK_STATE_UP).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.LINK_LOGICAL_PORT_STATE,
                                                          expected_value=NvosConsts.LINK_LOGICAL_PORT_STATE_ACTIVE).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                          field_name=IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE,
                                                          expected_value=NvosConsts.LINK_PHYSICAL_PORT_STATE_LINK_UP).verify_result()

    # @staticmethod
    # def verify_interface_down(devices, selected_port):
    #     port_type = devices.dut.switch_type.lower()
    #     output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
    #         selected_port.interface.link.show()).get_returned_value()
    #     Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
    #                                                       field_name=IbInterfaceConsts.LINK_STATE,
    #                                                       expected_value=NvosConsts.LINK_STATE_DOWN).verify_result()
    #     Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
    #                                                       field_name=IbInterfaceConsts.LINK_LOGICAL_PORT_STATE,
    #                                                       expected_value=IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_DOWN).verify_result()
    #     Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
    #                                                       field_name=IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE,
    #                                                       expected_value=IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_POLLING).verify_result()

    @staticmethod
    def start_stop_cluster(cluster, output_format):
        ClusterTools.start_cluster(cluster, output_format)
        ClusterTools.stop_cluster(cluster, output_format)
        return ResultObj(result=True)

    @staticmethod
    def verify_apps_running(engines, devices, cluster, expected_state, output_format):
        with allure.step("Running 'nv show cluster apps running' command and verifying output"):
            for app in INITIAL_EXPECTED_APPS:
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.apps.running.show(output_format=output_format),
                    output_format=output_format).get_returned_value()
                app_status = output[app]['status']
                assert app_status == expected_state, f"App {app} status is {app_status} instead of {expected_state}"
                ClusterTools.verify_app_is_up(engines, app)
            ClusterTools.verify_lid_value(devices)

    @staticmethod
    def verify_app_version(cluster, app, expected_version):
        with allure.step("Running 'nv show cluster apps running' command and verifying output"):
            output = OutputParsingTool.parse_show_output_to_dict(cluster.apps.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(output, app)
            assert output[app][ClusterConsts.APP_VERSION] == expected_version, \
                f"Expected {app} version: {expected_version}. Actual version: {output[app][ClusterConsts.APP_VERSION]}"

    @staticmethod
    def start_app(cluster, app):
        with allure.step(f"Start app {app}"):
            cluster.apps.apps_name[app].action_start_cluster_apps()
            with allure.step("Running 'nv show cluster apps running' command and verifying output"):
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.apps.running.show(output_format=OutputFormat.json),
                    output_format=OutputFormat.json).get_returned_value()
                app_status = output[app]['status']
                assert app_status == 'ok', f"App {app} status is {app_status} instead of 'ok"

    @staticmethod
    def stop_app(cluster, app):
        with allure.step(f"Stop app {app}"):
            cluster.apps.apps_name[app].action_stop_cluster_apps()

    @staticmethod
    def get_current_config_files_paths(control_plane):
        files_dict = {}
        with allure.step("Fetch & Generate config files"):
            for file_type in NMX_CONTROLLER_CONFIG_FILE_TYPES:
                output = control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].action_generate_control_plane()
                installed_file = get_generated_file_name(output.returned_value, 'config')
                output = OutputParsingTool.parse_show_output_to_dict(control_plane.config.app.app_name[NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=OutputFormat.json),
                                                                     output_format=OutputFormat.json).get_returned_value()
                current_installed_config_path = output[installed_file]['path']
                files_dict[file_type] = current_installed_config_path
        return files_dict

    @staticmethod
    def get_generated_file_name(output, file_type):
        # Regular expression to match the file name
        match = re.search(rf'App {file_type} file (\S+) is successfully generated', output)
        file_name = None
        # Extract the file name if found
        assert match, f"File was not generated successfully"
        if match:
            file_name = match.group(1)
            logger.info(f"Extracted file name: {file_name}")
        return file_name

    @staticmethod
    def verify_log_level(log_level, app, output_format, cluster, system):
        with allure.step(f"Verifying log level is updated to {log_level}"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.apps_name[app].loglevel.show(output_format=output_format),
                output_format=output_format).get_returned_value()
            # Add assert on log level
            assert output['log-level'] == log_level, f"Expected log level: {log_level}, Actual log-level {output['log-level']}"

            # Get the index of the current log level
            current_level_index = ClusterAppsLogLevelsList.index(log_level)

            # Define the expected log levels based on the current log level
            expected_log_levels = ClusterAppsLogLevelsList[current_level_index:]

            # Convert expected log levels to uppercase
            expected_log_levels_upper = [level.upper() for level in expected_log_levels]

            show_output = system.log.show_log(param=f"| grep -E \"{'|'.join(NMX_LOG_MESSAGES_TAGS)}\"", exit_cmd='q').split('\n')[1:]
            for line in show_output:
                assert any(level in line for level in expected_log_levels_upper), f"Line in logs is {line}, which does not contain any of the expected log levels {expected_log_levels_upper}"

    @staticmethod
    def verify_app_version(cluster, app, expected_version):
        with allure.step("Running 'nv show cluster apps running' command and verifying output"):
            output = OutputParsingTool.parse_show_output_to_dict(cluster.apps.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(output, app).verify_result()
            assert output[app][ClusterConsts.APP_VERSION] == expected_version, \
                f"Expected {app} version: {expected_version}. Actual version: {output[app][ClusterConsts.APP_VERSION]}"

    @staticmethod
    def wait_for_apps_to_be_in_wanted_state():
        time.sleep(WAIT_FOR_APPS_RUNNING)
        logger.info(f'Sleeping for {WAIT_FOR_APPS_RUNNING} seconds until apps are running')

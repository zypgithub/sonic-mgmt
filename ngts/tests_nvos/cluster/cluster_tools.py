import logging
import time
import re
import inspect
from collections import namedtuple, defaultdict
from functools import wraps

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import PlatformConsts, IbConsts, ApiType, OutputFormat, SystemConsts, ClusterAppsLogLevels, NvosConst
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, NvosConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.nvos_tools.platform.Platform import Platform

logger = logging.getLogger()


class ClusterTools:

    @staticmethod
    def stop_start_app(cluster, engines, devices, has_loopbox):
        with allure.step("Stop/Start apps"):
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                with allure.step(f"Validate app {app} is up"):
                    ClusterTools.verify_app_is_up(engines, app)
                    if app == ClusterConsts.NMX_CONTROLLER:
                        ClusterTools.verify_lid_value(devices)
                        ClusterTools.verify_interface_up(devices, has_loopbox)
                with allure.step("Running 'nv show cluster apps running' command and verifying output"):
                    if has_loopbox and app == ClusterConsts.NMX_CONTROLLER:
                        pass
                    else:
                        output = OutputParsingTool.parse_show_output_to_dict(
                            cluster.apps.running.show(output_format=OutputFormat.json),
                            output_format=OutputFormat.json).get_returned_value()
                        app_status = output[app]['status']
                        assert app_status == 'ok', f"App {app} status is {app_status} instead of 'ok"
                with allure.step(f"Stop app {app} and validate its down"):
                    cluster.apps.apps_name[app].action_stop_cluster_apps()
                    ClusterTools.wait_for_apps_to_be_in_wanted_state()
                    # TBD -- once "running" is working, use it to verify app is not running
                    ClusterTools.verify_app_is_down(engines, app)

                with allure.step(f"Start app again {app} and validate its up"):
                    output = cluster.apps.apps_name[app].action_start_cluster_apps()
                    ClusterTools.wait_for_apps_to_be_in_wanted_state()
                ClusterTools.verify_app_is_up(engines, app)
                if app == ClusterConsts.NMX_CONTROLLER:
                    ClusterTools.verify_lid_value(devices)
                    ClusterTools.verify_interface_up(devices, has_loopbox)
                with allure.step("Running 'nv show cluster apps running' command and verifying output"):
                    if has_loopbox and app == ClusterConsts.NMX_CONTROLLER:
                        pass
                    else:
                        output = OutputParsingTool.parse_show_output_to_dict(
                            cluster.apps.running.show(output_format=OutputFormat.json),
                            output_format=OutputFormat.json).get_returned_value()
                        app_status = output[app]['status']
                        assert app_status == 'ok', f"App {app} status is {app_status} instead of 'ok"

            return ResultObj(result=True)

    @staticmethod
    def start_cluster(cluster, output_format=OutputFormat.json, verify_nmx_c=True):
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
                assert ClusterConsts.NMXC_CONN in output, f"{ClusterConsts.NMXC_CONN} was not found in {output}"
                if verify_nmx_c:
                    expected_nmxc_state = ClusterConsts.NMXC_CONN_STATE_PER_CLUSTER_STATE[output[SystemConsts.STATE]]
                    Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output,
                                                                      field_name=ClusterConsts.NMXC_CONN,
                                                                      expected_value=expected_nmxc_state).verify_result()

    @staticmethod
    def validate_cluster_enabled(cluster, output_format=OutputFormat.json):
        output = OutputParsingTool.parse_show_output_to_dict(
            cluster.show(output_format=output_format),
            output_format=output_format).get_returned_value()

        with allure.step("Validate state is enabled"):
            assert output[SystemConsts.STATE] == 'enabled', f"Cluster state is , " \
                f"{output[SystemConsts.STATE]}, Expected to be: " \
                f"enabled"
            assert ClusterConsts.NMXC_CONN in output, f"{ClusterConsts.NMXC_CONN} was not found in {output}"
            expected_nmxc_state = ClusterConsts.NMXC_CONN_STATE_PER_CLUSTER_STATE[output[SystemConsts.STATE]]
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output,
                                                              field_name=ClusterConsts.NMXC_CONN,
                                                              expected_value=expected_nmxc_state).verify_result()
            assert output[ClusterConsts.NMXC_CONN] == expected_nmxc_state, f"{ClusterConsts.NMXC_CONN} state was expected to be {expected_nmxc_state} but instead it was {output[ClusterConsts.NMXC_CONN]}"

    @staticmethod
    def check_cluster_state(cluster, output_format=OutputFormat.json):
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
    def stop_cluster(cluster, output_format=OutputFormat.json):
        with allure.step("Stop cluster"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()

            if output[SystemConsts.STATE] == 'enabled':
                cluster.set(op_param_name="state", op_param_value='disabled', apply=True)

            ClusterTools.wait_for_apps_to_be_in_wanted_state()
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()

            with allure.step("Validate state is disabled"):
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=output_format),
                    output_format=output_format).get_returned_value()
                assert output[SystemConsts.STATE] == 'disabled', f"State state is , " \
                    f"{output[SystemConsts.STATE]}, Expected to be: " \
                    f"disabled"
                assert ClusterConsts.NMXC_CONN in output, f"{ClusterConsts.NMXC_CONN} was not found in {output}"
                expected_nmxc_state = ClusterConsts.NMXC_CONN_STATE_PER_CLUSTER_STATE[output[SystemConsts.STATE]]
                assert output[ClusterConsts.NMXC_CONN] == expected_nmxc_state, f"{ClusterConsts.NMXC_CONN} state was expected to be {expected_nmxc_state} but instead it was {output[ClusterConsts.NMXC_CONN]}"

    @staticmethod
    def verify_app_is_up(engines, app):
        with allure.step("Checking if service is up using docker ps | grep -i nmx"):
            output = engines.dut.run_cmd('docker ps | grep -i nmx')
            assert output != '', f"nmx docker is still down, {output}"
            output = output.split('\n')
            expected_services = ClusterConsts.CONTROLLER_SERVICES if app == ClusterConsts.NMX_CONTROLLER else ClusterConsts.TELEMETRY_SERVICES
            all_services_present = all(any(service in line for line in output) for service in expected_services)
            assert all_services_present, f"Missing services - expected services {expected_services}, actual: {output}"

    @staticmethod
    def verify_app_is_down(engines, app):
        with allure.step("Checking if service is down using docker ps | grep -i nmx"):
            output = engines.dut.run_cmd('docker ps | grep -i nmx')
            output = output.split('\n')
            expected_services = ClusterConsts.CONTROLLER_SERVICES if app == ClusterConsts.NMX_CONTROLLER else ClusterConsts.TELEMETRY_SERVICES
            none_services_present = all(not any(service in line for line in output) for service in expected_services)
            assert none_services_present, f"nmx docker is still up, {output}"

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
    def verify_interface_up(devices, has_loopbox):
        interface_types = ['fnm', 'acp'] if has_loopbox else []
        for interface_type in interface_types:
            port_type = 'fnm' if interface_type == 'fnm' else ''
            selected_port = Tools.RandomizationTool.select_random_port(requested_ports_logical_state=NvosConsts.LINK_LOG_STATE_ACTIVE, requested_ports_type=port_type, interface_type=interface_type).get_returned_value()
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_STATE,
                                                              expected_value=NvosConsts.LINK_STATE_UP).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_LOGICAL_PORT_STATE,
                                                              expected_value=IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_ACTIVE).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE,
                                                              expected_value=IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_LINK_UP).verify_result()

        with allure.step("Verify switch ports state - that are connected to transceivers"):
            ClusterTools().verify_external_interfaces_state_up_and_active(devices)

    @staticmethod
    def get_all_interfaces_with_transceivers(devices):
        interfaces = []
        platform = Platform()
        present_transceivers = platform.transceiver.get_list_of_connected_transceivers()

        for transceiver in present_transceivers:
            interfaces.extend([interface for interface in devices.dut.nvl5_trunk_ports_list if interface.startswith(transceiver)])
        return interfaces

    @staticmethod
    def verify_external_interfaces_state_up_and_active(devices):
        interfaces = ClusterTools().get_all_interfaces_with_transceivers(devices)
        for interface in interfaces:
            selected_port = Port(interface, "", "")
            # Verify fields.
            output_dictionary = Tools.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                selected_port.interface.link.show()).get_returned_value()
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_STATE,
                                                              expected_value=NvosConsts.LINK_STATE_UP).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_LOGICAL_PORT_STATE,
                                                              expected_value=IbInterfaceConsts.LINK_LOGICAL_PORT_STATE_ACTIVE).verify_result()
            Tools.ValidationTool.verify_field_value_in_output(output_dictionary=output_dictionary,
                                                              field_name=IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE,
                                                              expected_value=IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_LINK_UP).verify_result()

    @staticmethod
    def start_stop_cluster(cluster, output_format):
        ClusterTools.start_cluster(cluster, output_format)
        ClusterTools.stop_cluster(cluster, output_format)
        return ResultObj(result=True)

    @staticmethod
    def verify_apps_running(engines, devices, cluster, expected_state, output_format):
        with allure.step("Running 'nv show cluster apps running' command and verifying output"):
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
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
            assert expected_version in output[app][ClusterConsts.APP_VERSION], \
                f"Expected {app} version: {expected_version}. Actual version: {output[app][ClusterConsts.APP_VERSION]}"

    @staticmethod
    def start_app(cluster, app, has_loopbox):
        with allure.step(f"Start app {app}"):
            cluster.apps.apps_name[app].action_start_cluster_apps()
            ClusterTools.wait_for_apps_to_be_in_wanted_state()
            if has_loopbox and app == ClusterConsts.NMX_CONTROLLER:
                pass
            else:
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
            ClusterTools.wait_for_apps_to_be_in_wanted_state()

    @staticmethod
    def get_current_config_files_paths(sdn):
        files_dict = {}
        with allure.step("Fetch & Generate config files"):
            for file_type in ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES:
                output = sdn.config.app.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].action_generate_sdn()
                installed_file = ClusterTools().get_generated_file_name(output.returned_value, 'config')
                output = OutputParsingTool.parse_show_output_to_dict(sdn.config.app.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=OutputFormat.json),
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
    def verify_log_level(log_level, app, output_format, cluster):
        with allure.step(f"Verifying log level is updated to {log_level}"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.apps_name[app].loglevel.show(output_format=output_format),
                output_format=output_format).get_returned_value()
            # Add assert on log level
            assert output['log-level'] == log_level, f"Expected log level: {log_level}, Actual log-level {output['log-level']}"

    @staticmethod
    def verify_log_messages_log_level(log_level, system, test_api, cluster):
        ClusterTools().stop_cluster(cluster)
        ClusterTools().start_cluster(cluster)
        TestToolkit.tested_api = 'NVUE'
        lines_checked = 0
        # Get the index of the current log level
        current_level_index = ClusterConsts.ClusterAppsLogLevelsList.index(log_level)

        # Define the expected log levels based on the current log level
        expected_log_levels = ClusterConsts.ClusterAppsLogLevelsList[current_level_index:]
        unexpected_log_levels = ClusterConsts.ClusterAppsLogLevelsList[0:current_level_index]
        # Convert expected log levels to uppercase
        expected_log_levels_upper = [level.upper() for level in expected_log_levels]
        unexpected_log_levels = [level.upper() for level in unexpected_log_levels]

        show_output = system.log.show_log(param=f"| grep -E \"{'|'.join(ClusterConsts.NMX_LOG_MESSAGES_TAGS)}\"").split('\n')[1:]
        for line in show_output:
            if ":~$" in line:  # Symbolizes start of prompt line, no need to check.
                continue
            lines_checked = lines_checked + 1
            assert any(level in line for level in expected_log_levels_upper), f"Line in logs is {repr(line)}, which does not contain any of the expected log levels {expected_log_levels_upper}"
            assert all(level not in line for level in unexpected_log_levels), f"Line in logs is {repr(line)}, which does contains an unexpected log levels {unexpected_log_levels}"
        assert lines_checked > 0, "No lines were checked. No log message related to nmx "

        TestToolkit.tested_api = test_api

    @staticmethod
    def wait_for_apps_to_be_in_wanted_state():
        time.sleep(ClusterConsts.WAIT_FOR_APPS_RUNNING)
        logger.info(f'Sleeping for {ClusterConsts.WAIT_FOR_APPS_RUNNING} seconds until apps are running')

    @staticmethod
    def verify_sdn_config_files_deleted(sdn):
        with allure.step("Running nv show sdn config app <app> type <type> files and make sure files are deleted"):
            for file_type in ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES:
                files = OutputParsingTool.parse_show_output_to_dict(sdn.config.app.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=OutputFormat.json),
                                                                    output_format=OutputFormat.json).get_returned_value()
                assert not files, f"Expected to get empty output, but instead received {output}"

    @staticmethod
    def verify_sdn_state_files_deleted(sdn):
        with allure.step("Running nv show sdn state app <app> type <type> files and make sure files are deleted"):
            for file_type in ClusterConsts.NMX_CONTROLLER_STATE_FILE_TYPES:
                files = OutputParsingTool.parse_show_output_to_dict(sdn.state.app.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[file_type].files.show(output_format=OutputFormat.json),
                                                                    output_format=OutputFormat.json).get_returned_value()
                assert not files, f"Expected to get empty output, but instead received {output}"

    @staticmethod
    def wa_to_get_active_interface_for_loopbox_systems(cluster, sdn, devices, engines, has_loopbox):
        ClusterTools().stop_cluster(cluster)

        devices.dut.nvl5_access_ports_list
        logger.info("Disable access ports")
        port_name = summarize_ports(devices.dut.nvl5_access_ports_list)  # Returns range of ports.
        selected_port = Port(port_name, "", "")
        port_state = NvosConsts.LINK_STATE_DOWN
        selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
        time.sleep(90)

        ClusterTools().start_cluster(cluster)
        sm_config = ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES[1]
        output = sdn.config.app.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[sm_config].action_generate_sdn().get_returned_value()
        generated_file_name = ClusterTools().get_generated_sdn_file(output, 'config')
        output_format = OutputFormat.json
        output = OutputParsingTool.parse_show_output_to_dict(sdn.config.app.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[sm_config].files.show(output_format=output_format),
                                                             output_format=output_format).get_returned_value()
        path_to_generated_file = output[generated_file_name]['path']
        logger.info("Comment lines - Part of WA")
        engines.dut.run_cmd(
            f"sudo sed -i \"/^nvlink_enable TRUE/s/^/#/\" {path_to_generated_file} && sudo sed -i \"/^plugin_name grpc_mgr/s/^/#/\" {path_to_generated_file}"
        )

        sdn.config.app.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[sm_config].files.file_name[generated_file_name].action_file_install(force=False)

        selected_port = Port(port_name, "", "")
        port_state = NvosConsts.LINK_STATE_UP
        selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
        time.sleep(90)

        ClusterTools().stop_app(cluster, ClusterConsts.NMX_CONTROLLER)
        ClusterTools().start_app(cluster, ClusterConsts.NMX_CONTROLLER, has_loopbox)

        ClusterTools().validate_cluster_enabled(cluster)
        yield

        engines.dut.run_cmd(
            f"sudo sed -i \"/^#nvlink_enable TRUE/s/^#//\" {path_to_generated_file} && sudo sed -i \"/^#plugin_name grpc_mgr/s/^#//\" {path_to_generated_file}"
        )
        sdn.config.app.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[sm_config].files.file_name[generated_file_name].action_file_install(force=False)
        sdn.config.app.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[sm_config].files.file_name[generated_file_name].action_delete()

    @staticmethod
    def get_generated_sdn_file(output, file_type):
        # Use a regular expression to capture the filename
        match = re.search(fr"App {file_type} file (\S+)", output)
        if match:
            filename = match.group(1)
            return filename
        else:
            return None


def summarize_switch_ports(ports_list):
    # Dictionary to store ranges for each prefix
    segments = defaultdict(set)

    # Regex to match any prefix followed by numbers (e.g., "sw1", "p1", "s1")
    pattern = re.compile(r'([a-zA-Z]+)(\d+)')

    for port in ports_list:
        # Find all (prefix, number) pairs in each port string
        matches = pattern.findall(port)
        for prefix, num in matches:
            segments[prefix].add(int(num))  # Collect numbers for each prefix

    # Build the summary string
    summary_parts = []
    for prefix, numbers in segments.items():
        min_num, max_num = min(numbers), max(numbers)
        summary_parts.append(f"{prefix}{min_num}-{max_num}")

    # Join the parts into the final string
    return ''.join(summary_parts)


def refresh_switch_ports(ports_list, engines):
    TestToolkit.tested_api = 'NVUE'
    port_name = summarize_switch_ports(ports_list)
    selected_port = Port(port_name, "", "")
    port_state = NvosConsts.LINK_STATE_DOWN
    selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
    TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
    time.sleep(30)
    port_state = NvosConsts.LINK_STATE_UP
    selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
    TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
    time.sleep(30)


def disabled_access_ports(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Access a specific named argument, 'test_api', if it exists
        sig = inspect.signature(func)
        # Bind the arguments to the signature
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        # Access 'devices' from bound arguments
        devices = bound_args.arguments.get('devices', None)
        engines = bound_args.arguments.get('engines', None)
        has_access_ports = True
        try:
            TestToolkit.tested_api = 'NVUE'
            if not hasattr(devices.dut, 'nvl5_access_ports_list'):
                has_access_ports = False
            if has_access_ports:
                port_name = summarize_ports(devices.dut.nvl5_access_ports_list)
                selected_port = Port(port_name, "", "")
                port_state = NvosConsts.LINK_STATE_DOWN
                selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
                TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
            # Execute the test function
            return func(*args, **kwargs)
        finally:
            if has_access_ports:
                port_name = summarize_ports(devices.dut.nvl5_access_ports_list)
                selected_port = Port(port_name, "", "")
                port_state = NvosConsts.LINK_STATE_UP
                selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
                TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
    return wrapper


def summarize_ports(ports_list):
    if not ports_list:
        return ''

    # Extract the prefix and numbers from the port names
    pattern = re.compile(r'([^\d]+)(\d+)')
    prefixes = set()
    numbers = []

    for port in ports_list:
        match = pattern.match(port)
        if match:
            prefix, num = match.groups()
            prefixes.add(prefix)
            numbers.append(int(num))
        else:
            raise ValueError(f"Port name '{port}' does not match expected pattern.")

    if len(prefixes) > 1:
        raise ValueError(f"Multiple prefixes found: {prefixes}")

    prefix = prefixes.pop()
    min_num = min(numbers)
    max_num = max(numbers)

    # Check if numbers are consecutive
    expected_numbers = set(range(min_num, max_num + 1))
    if set(numbers) != expected_numbers:
        # If not consecutive, return the list as is
        return ','.join(ports_list)

    return f'{prefix}{min_num}-{max_num}'

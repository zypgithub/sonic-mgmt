import inspect
import logging
import random
import re
import time
from collections import defaultdict
from functools import wraps
from retry import retry

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import IbConsts, OutputFormat, SystemConsts
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, NvosConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RegressionConfigurations import Configurations
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.nmx.Sdn import Sdn
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch

logger = logging.getLogger()


class ClusterTools:

    @staticmethod
    def stop_start_app(cluster, engines, devices, has_loopbox, setup_name, standalone_system):
        with allure.step("Stop/Start apps"):
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                with allure.step(f"Validate app {app} is up"):
                    ClusterTools.reboot_compute_nodes_gpus(setup_name)
                    ClusterTools.verify_app_is_up(engines, app)
                    if app == ClusterConsts.NMX_CONTROLLER and (has_loopbox or not standalone_system):
                        ClusterTools.verify_lid_value(devices)
                        ClusterTools.verify_interface_up(devices, has_loopbox, setup_name)
                with allure.step("Running 'nv show cluster apps running' command and verifying output"):
                    if app == ClusterConsts.NMX_CONTROLLER and is_bug_active(4207869) and standalone_system:
                        pass
                    else:
                        output = OutputParsingTool.parse_show_output_to_dict(
                            cluster.apps.running.show(output_format=OutputFormat.json),
                            output_format=OutputFormat.json).get_returned_value()
                        app_status = output[app]['status']
                        assert app_status == 'ok', f"App {app} status is {app_status} instead of 'ok"
                with allure.step(f"Stop app {app} and validate its down"):
                    cluster.apps.app_name[app].action_stop_cluster_app()
                    nmx_c_expected_state = 'down' if app == ClusterConsts.NMX_CONTROLLER else ''
                    ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state=nmx_c_expected_state)
                    # TBD -- once "running" is working, use it to verify app is not running
                    ClusterTools.verify_app_is_down(engines, app)

                with allure.step(f"Start app again {app} and validate its up"):
                    output = cluster.apps.app_name[app].action_start_cluster_app()
                    nmx_c_expected_state = 'up' if app == ClusterConsts.NMX_CONTROLLER else ''
                    ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled', nmx_c_expected_state=nmx_c_expected_state)
                    ClusterTools.reboot_compute_nodes_gpus(setup_name)
                ClusterTools.verify_app_is_up(engines, app)
                if app == ClusterConsts.NMX_CONTROLLER and (has_loopbox or not standalone_system):
                    ClusterTools.verify_lid_value(devices)
                    ClusterTools.verify_interface_up(devices, has_loopbox, setup_name)
                with allure.step("Running 'nv show cluster apps running' command and verifying output"):
                    if app == ClusterConsts.NMX_CONTROLLER and is_bug_active(4207869) and standalone_system:
                        pass
                    else:
                        output = OutputParsingTool.parse_show_output_to_dict(
                            cluster.apps.running.show(output_format=OutputFormat.json),
                            output_format=OutputFormat.json).get_returned_value()
                        app_status = output[app]['status']
                        assert app_status == 'ok', f"App {app} status is {app_status} instead of 'ok"

            return ResultObj(result=True)

    @staticmethod
    def start_cluster(cluster, setup_name, output_format=OutputFormat.json, verify_nmx_c=True):
        with allure.step("Start cluster"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()

            if output[SystemConsts.STATE] == 'disabled':
                cluster.set(op_param_name="state", op_param_value='enabled', apply=True)

            ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled', nmx_c_expected_state='up')
            ClusterTools.reboot_compute_nodes_gpus(setup_name)
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
    def reverse_cluster_state(cluster, setup_name, output_format):
        if ClusterTools.check_cluster_state(cluster, output_format) == 'enabled':
            ClusterTools.stop_cluster(cluster, output_format)
        else:
            ClusterTools.start_cluster(cluster, setup_name, output_format=output_format)

    @staticmethod
    def stop_cluster(cluster, output_format=OutputFormat.json):
        with allure.step("Stop cluster"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()

            if output[SystemConsts.STATE] == 'enabled':
                cluster.set(op_param_name="state", op_param_value='disabled', apply=True)

            ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()

            with allure.step("Validate state is disabled"):
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=output_format),
                    output_format=output_format).get_returned_value()
                assert output[SystemConsts.STATE] == 'disabled', f"State is: " \
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
    def verify_interface_up(devices, has_loopbox, setup_name):
        if setup_name in Configurations.non_standalone_systems:
            interface_types = ['acp']
        if setup_name not in Configurations.non_standalone_systems and has_loopbox:
            interface_types = ['fnm', 'acp']
        else:
            interface_types = []
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
            interfaces.extend([interface for interface in devices.dut.nvl5_trunk_ports_list if interface.startswith(f"{transceiver}p")])
            # This way, if sw1 is present and sw10 is not, we will not take sw10. because we force sw1p so sw10p falls.
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
    def start_stop_cluster(cluster, setup_name, output_format):
        ClusterTools.start_cluster(cluster, setup_name, output_format)
        ClusterTools.stop_cluster(cluster, output_format)
        return ResultObj(result=True)

    @staticmethod
    def verify_apps_running(engines, devices, cluster, expected_state, output_format, standalone_system, has_loopbox):
        with allure.step("Running 'nv show cluster apps running' command and verifying output"):
            for app in ClusterConsts.INITIAL_EXPECTED_APPS:
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.apps.running.show(output_format=output_format),
                    output_format=output_format).get_returned_value()
                app_status = output[app]['status']
                if app == ClusterConsts.NMX_CONTROLLER and is_bug_active(4207869) and standalone_system:
                    pass
                else:
                    assert app_status == expected_state, f"App {app} status is {app_status} instead of {expected_state}"
                ClusterTools.verify_app_is_up(engines, app)
            if has_loopbox or not standalone_system:
                ClusterTools.verify_lid_value(devices)

    @staticmethod
    def verify_app_version(cluster, app, expected_version):
        with allure.step("Running 'nv show cluster apps running' command and verifying output"):
            output = OutputParsingTool.parse_show_output_to_dict(cluster.apps.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(output, app)
            assert expected_version in output[app][ClusterConsts.APP_VERSION], \
                f"Expected {app} version: {expected_version}. Actual version: {output[app][ClusterConsts.APP_VERSION]}"

    @staticmethod
    def start_app(cluster, app, has_loopbox, standalone_system):
        with allure.step(f"Start app {app}"):
            cluster.apps.app_name[app].action_start_cluster_app()
            ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled', nmx_c_expected_state='up')
            if app == ClusterConsts.NMX_CONTROLLER and is_bug_active(4207869) and standalone_system:
                pass
            else:
                with allure.step("Running 'nv show cluster apps running' command and verifying output"):
                    for _ in range(10):
                        output = OutputParsingTool.parse_show_output_to_dict(
                            cluster.apps.running.show(output_format=OutputFormat.json),
                            output_format=OutputFormat.json).get_returned_value()
                        app_status = output[app]['status']
                        if app_status == 'ok':
                            break
                        logger.info("Sleeping for 5 seconds until app state is ok.")
                        time.sleep(5)
                    assert app_status == 'ok', f"App {app} status is {app_status} instead of 'ok"

    @staticmethod
    def stop_app(cluster, app):
        with allure.step(f"Stop app {app}"):
            cluster.apps.app_name[app].action_stop_cluster_app()
            if app == ClusterConsts.NMX_CONTROLLER:
                ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='', nmx_c_expected_state='down')
            else:
                logger.info("Stopping nmx-telemetry app, sleeping for 10 seconds till its status is updated")
                time.sleep(10)

    @staticmethod
    def get_current_config_files_paths(sdn, app, files_types):
        files_dict = {}
        with allure.step("Fetch & Generate config files"):
            for file_type in files_types:
                output = sdn.config.apps.app_name[app].type.file_type[file_type].action_generate_sdn()
                installed_file = ClusterTools().get_generated_file_name(output.returned_value, 'config')
                output = OutputParsingTool.parse_show_output_to_dict(sdn.config.apps.app_name[app].type.file_type[file_type].files.show(output_format=OutputFormat.json),
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
                cluster.apps.app_name[app].loglevel.show(output_format=output_format),
                output_format=output_format).get_returned_value()
            # Add assert on log level
            assert output['log-level'] == log_level, f"Expected log level: {log_level}, Actual log-level {output['log-level']}"

    @staticmethod
    def create_empty_partition(sdn, partitions_mapping, output_format=OutputFormat.json):
        with allure.step("Create empty partition"):
            resiliency_mode = random.choice(ClusterConsts.RESILIENCY_MODES)
            mcast_limit = random.randint(ClusterConsts.MIN_MCAST, ClusterConsts.MAX_MCAST)
            sdn.partition.partition_id[ClusterConsts.EMPTY_PARTITION_ID].action_create_partition_id(name=ClusterConsts.EMPTY_PARTITION_NAME, resiliency_mode=resiliency_mode, mcast_limit=mcast_limit)

        with allure.step("Checking newly created partition"):
            output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()
            assert ClusterConsts.EMPTY_PARTITION_ID in list(output.keys()), f'Partition {ClusterConsts.EMPTY_PARTITION_ID} was not created'
            output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[ClusterConsts.EMPTY_PARTITION_ID].show(output_format=output_format),
                                                                 output_format=output_format).get_returned_value()
            partitions_mapping[int(ClusterConsts.EMPTY_PARTITION_ID)] = []
            if not is_bug_active(4209873):
                expected_output = {'health': 'healthy', 'locations': {}, 'mcast-limit': mcast_limit, 'name': ClusterConsts.EMPTY_PARTITION_NAME, 'num-gpus': 0, 'partition-type': '', 'resiliency-mode': resiliency_mode}
                ClusterTools.validate_partition_content(output, expected_output)

    @staticmethod
    def validate_partition_content(output, expected_output):
        for key, val in expected_output.items():
            if key in ['locations'] and (not expected_output[key]):
                continue
            else:
                if (is_bug_active(4290901) and (val == 'user_action')) or val == '':
                    pass
                else:
                    assert str(output[key]) == str(val), f'Expected value: {val}, Actual value:{output[key]}'

    @staticmethod
    def create_empty_partition_and_add_gpu(sdn, no_reroute='', output_format=OutputFormat.json):
        mapping, original_partition_type = ClusterTools.get_partition_mapping(sdn)
        valid_ids = [key for key, value in mapping.items() if len(value) > 0]
        ClusterTools.create_empty_partition(sdn, mapping)
        partition_type = random.choice(ClusterConsts.PARTITION_TYPES)
        partition_to_remove_from = random.choice(valid_ids)
        gpus_in_partition = mapping[partition_to_remove_from]
        (uuid, location) = random.choice(gpus_in_partition)
        with allure.step(f"Remove GPU from partition {partition_to_remove_from}"):
            if original_partition_type == 'location_based':
                sdn.partition.partition_id[partition_to_remove_from].location.location_id[location].action_restore_partition(reroute_param=no_reroute).verify_result()
            else:
                sdn.partition.partition_id[partition_to_remove_from].uuid.uuid_value[uuid].action_restore_partition(reroute_param=no_reroute).verify_result()

        if is_bug_active(4285786):
            time.sleep(15)

        with allure.step(f"Add GPU {uuid} {location} to empty partition {ClusterConsts.EMPTY_PARTITION_ID}"):
            empty_partition_type = random.choice(['uuid', 'location'])
            if empty_partition_type == 'location':
                sdn.partition.partition_id[ClusterConsts.EMPTY_PARTITION_ID].location.location_id[location].action_update_partition(reroute_param=no_reroute).verify_result()
            else:
                sdn.partition.partition_id[ClusterConsts.EMPTY_PARTITION_ID].uuid.uuid_value[uuid].action_update_partition(reroute_param=no_reroute).verify_result()
        return uuid, location, ClusterConsts.EMPTY_PARTITION_ID, partition_to_remove_from

    @staticmethod
    def uuid_location_in_partition(sdn, partition_id):
        output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[partition_id].show()).get_returned_value()
        uuids = [info['uuid'] for _, info in output['locations'].items()]
        locations = list((output['locations']).keys())
        return uuids, locations

    @staticmethod
    def get_partition_mapping(sdn, output_format=OutputFormat.json):
        mapping = {}
        with allure.step("Show All Partitions - at the beginning its just the default partition"):
            initial_partition_output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                                   output_format=output_format).get_returned_value()
            partition_ids = list(initial_partition_output.keys())
            default_partition_id = partition_ids[-1]
            default_partition_type = initial_partition_output[default_partition_id]['partition-type']
        with allure.step("Show partition per partition id"):
            for partition_id in partition_ids:
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.partition_id[partition_id].show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                list_of_tuples = ClusterTools.get_partition_uuid_location_map(output)
                mapping[partition_id] = list_of_tuples
        return mapping, default_partition_type

    @staticmethod
    def get_partition_uuid_location_map(partition_output):
        location_uuid_map = partition_output['locations']
        mapping_list = [(info['uuid'], location) for location, info in location_uuid_map.items()]
        return mapping_list

    @staticmethod
    def delete_empty_partition(sdn, partitions_mapping, output_format=OutputFormat.json):
        with allure.step("Delete empty partition"):
            sdn.partition.partition_id[ClusterConsts.EMPTY_PARTITION_ID].action_delete_partition()
            start_time = time.time()
            timeout = 25
            while True:
                output = OutputParsingTool.parse_show_output_to_dict(sdn.partition.show(output_format=output_format),
                                                                     output_format=output_format).get_returned_value()
                logger.info("Checking if partition is deleted,")
                if ClusterConsts.EMPTY_PARTITION_ID not in list(output.keys()):
                    elapsed_time = time.time() - start_time
                    logger.info(f"Condition met: Partition {ClusterConsts.EMPTY_PARTITION_ID} deleted after {elapsed_time:.2f} seconds")
                    break

                if time.time() - start_time > timeout:
                    logger.error(f"Timeout: Partition {ClusterConsts.EMPTY_PARTITION_ID} was not deleted within {timeout} seconds")
                    break
                logger.info("Partition is not deleted. Retrying")

            assert ClusterConsts.EMPTY_PARTITION_ID not in list(output.keys()), f'Partition {ClusterConsts.EMPTY_PARTITION_ID} was not deleted'
            partitions_mapping.pop(int(ClusterConsts.EMPTY_PARTITION_ID))

    @staticmethod
    def verify_log_messages_log_level(log_level, system, test_api, cluster, setup_name):
        ClusterTools().stop_cluster(cluster)
        ClusterTools().start_cluster(cluster, setup_name)
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
    def wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='', nmx_c_expected_state=''):
        for _ in range(15):
            final_sleep_time = 2
            if (not cluster_expected_state) and (not nmx_c_expected_state):
                final_sleep_time += 8
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=OutputFormat.json),
                output_format=OutputFormat.json).get_returned_value()
            with allure.step(
                    f"Polling until cluster state is {cluster_expected_state} "
                    f"and nmx-c state is {nmx_c_expected_state}"
            ):
                if (
                        (cluster_expected_state and output[SystemConsts.STATE] != cluster_expected_state) or
                        (nmx_c_expected_state and
                         output[ClusterConsts.NMXC_CONN] != nmx_c_expected_state)
                ):
                    logger.info("Cluster state not as expected yet. Retrying...")
                    logger.info(f"Expected: cluster {cluster_expected_state}, nmx_c {nmx_c_expected_state}.\n Actual: cluster {output[SystemConsts.STATE]}, nmx_c {output[ClusterConsts.NMXC_CONN]}")
                    logger.info("Sleeping for 3 seconds between iterations")
                    time.sleep(3)
                else:
                    logger.info(f"Cluster is now in the wanted state. Sleeping for {final_sleep_time} seconds.")
                    time.sleep(final_sleep_time)
                    break

    @staticmethod
    def verify_sdn_config_files_deleted(sdn):
        with allure.step("Running nv show sdn config app <app> type <type> files and make sure files are deleted"):
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_CONFIG_FILES:
                app = ClusterConsts.MAP_CONFIG_FILE_TYPE_TO_APP[file_type]
                files = OutputParsingTool.parse_show_output_to_dict(sdn.config.apps.app_name[app].type.file_type[file_type].files.show(output_format=OutputFormat.json),
                                                                    output_format=OutputFormat.json).get_returned_value()
                assert not files, f"Expected to get empty output, but instead received {files}"

    @staticmethod
    def verify_sdn_state_files_deleted(sdn):
        with allure.step("Running nv show sdn state app <app> type <type> files and make sure files are deleted"):
            for file_type in ClusterConsts.CONTROLLER_AND_TELEMETRY_STATE_FILES:
                app = ClusterConsts.MAP_STATE_FILE_TYPE_TO_APP[file_type]
                files = OutputParsingTool.parse_show_output_to_dict(sdn.state.apps.app_name[app].type.file_type[file_type].files.show(output_format=OutputFormat.json),
                                                                    output_format=OutputFormat.json).get_returned_value()
                assert not files, f"Expected to get empty output, but instead received {files}"

    @staticmethod
    def reboot_compute_nodes_gpus(setup_name):
        if setup_name in list(Configurations.compute_nodes_per_system.keys()):
            for node in Configurations.compute_nodes_per_system[setup_name]:
                ip_address = node['ip_address']
                username = node['username']
                password = node['password']
                new_engine = LinuxSshEngine(ip_address, username, password)
                new_engine.run_cmd(f"echo {password} | sudo -S nvidia-smi -r ; sleep 1")
                new_engine.run_cmd(f"{password}")
            time.sleep(10)

    @staticmethod
    def edit_config_file(path, edit_commands, engines):
        engines.dut.run_cmd("\n".join(edit_commands).replace("{file}", path))

    @staticmethod
    def edit_fm_config(sdn, engines, get_generated_file_info):
        fm_config = ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES[0]
        fm_generated_file_name, fm_path = get_generated_file_info(fm_config)
        fm_original_content = engines.dut.run_cmd(f"cat {fm_path}")
        logger.info("Adjusting fm_config file.")
        ClusterTools().edit_config_file(fm_path, [
            "sudo sed -i '/^MNNVL_TOPOLOGY=/c\\MNNVL_TOPOLOGY=gb200_nvl8r1_c2g4_etf_topology' {file} && \\",
            "sudo grep -q '^MNNVL_TOPOLOGY=' {file} || echo 'MNNVL_TOPOLOGY=gb200_nvl8r1_c2g4_etf_topology' | sudo tee -a {file} && \\",
            "sudo sed -i '/^MNNVL_PARTIALLY_POPULATED_TOPOLOGY=/c\\MNNVL_PARTIALLY_POPULATED_TOPOLOGY=1' {file} && \\",
            "sudo grep -q '^MNNVL_PARTIALLY_POPULATED_TOPOLOGY=' {file} || echo 'MNNVL_PARTIALLY_POPULATED_TOPOLOGY=1' | sudo tee -a {file}"
        ], engines)
        sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[fm_config].files.file_name[
            fm_generated_file_name].action_file_install(force=False)
        return fm_config, fm_generated_file_name, fm_path, fm_original_content

    @staticmethod
    def edit_sm_config(sdn, engines, get_generated_file_info):
        sm_config = ClusterConsts.NMX_CONTROLLER_CONFIG_FILE_TYPES[1]
        sm_generated_file_name, sm_path = get_generated_file_info(sm_config)
        sm_original_content = engines.dut.run_cmd(f"cat {sm_path}")
        logger.info("Adjusting sm_config file.")
        ClusterTools().edit_config_file(sm_path, [
            "# Ensure nvlink_enable=FALSE",
            "sudo sed -i '/^nvlink_enable[ ]*TRUE/c\\nvlink_enable FALSE' {file} && \\",
            "sudo grep -q '^nvlink_enable' {file} || echo 'nvlink_enable FALSE' | sudo tee -a {file}",

            "# Comment plugin_name grpc_mgr",
            "sudo sed -i '/^[ ]*plugin_name[ ]\\+grpc_mgr/s/^/#/' {file}",

            "# Comment plugin_options -grpc_mgr",
            "sudo sed -i '/^[ ]*plugin_options[ ]\\+-grpc_mgr[ ]\\+--config_file[ ]\\+/s/^/#/' {file}"
        ], engines)
        sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[sm_config].files.file_name[
            sm_generated_file_name].action_file_install(force=False)
        return sm_config, sm_generated_file_name, sm_path, sm_original_content

    @staticmethod
    def wa_to_get_active_interface_for_loopbox_systems(cluster, sdn, devices, engines, has_loopbox, setup_name,
                                                       standalone_system):
        def get_generated_file_info(config_type):
            output = sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[
                config_type].action_generate_sdn().get_returned_value()
            file_name = ClusterTools().get_generated_sdn_file(output, 'config')
            output_dict = OutputParsingTool.parse_show_output_to_dict(
                sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[config_type].files.show(
                    output_format=output_format),
                output_format=output_format).get_returned_value()
            path = output_dict[file_name]['path']
            return file_name, path

        output_format = OutputFormat.json

        fm_config, fm_generated_file_name, fm_path, fm_original_content = ClusterTools().edit_fm_config(sdn, engines,
                                                                                                        get_generated_file_info)

        if has_loopbox:
            sm_config, sm_generated_file_name, sm_path, sm_original_content = ClusterTools().edit_sm_config(sdn, engines,
                                                                                                            get_generated_file_info)

        ClusterTools().stop_app(cluster, ClusterConsts.NMX_CONTROLLER)
        ClusterTools().start_app(cluster, ClusterConsts.NMX_CONTROLLER, has_loopbox, standalone_system)
        ClusterTools.reboot_compute_nodes_gpus(setup_name)
        ClusterTools.validate_cluster_enabled(cluster)

        yield

        if ClusterTools.check_cluster_state(cluster, output_format) == 'disabled':
            ClusterTools.start_cluster(cluster, setup_name, output_format=output_format)

        if "Exists" in engines.dut.run_cmd(f'test -e {fm_path} && echo "Exists" || echo "Does not exist"'):
            engines.dut.run_cmd(f"echo '{fm_original_content}' | sudo tee {fm_path} > /dev/null")
            sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[fm_config].files.file_name[
                fm_generated_file_name].action_file_install(force=False)
            sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[fm_config].files.file_name[
                fm_generated_file_name].action_delete()

        if has_loopbox and "Exists" in engines.dut.run_cmd(
                f'test -e {sm_path} && echo "Exists" || echo "Does not exist"'):
            engines.dut.run_cmd(f"echo '{sm_original_content}' | sudo tee {sm_path} > /dev/null")
            sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[sm_config].files.file_name[
                sm_generated_file_name].action_file_install(force=False)
            sdn.config.apps.app_name[ClusterConsts.NMX_CONTROLLER].type.file_type[sm_config].files.file_name[
                sm_generated_file_name].action_delete()

    @staticmethod
    def get_generated_sdn_file(output, file_type):
        # Use a regular expression to capture the filename
        match = re.search(fr"App {file_type} file (\S+)", output)
        if match:
            filename = match.group(1)
            return filename
        else:
            return None

    @retry(Exception, tries=4, delay=5)
    def wait_until_app_expected_status(cluster, app, expected_status):
        with allure.step(f"Waiting for {app} to be in {expected_status} status"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.running.show(output_format=OutputFormat.json)).get_returned_value()
            app_status = output[app]['status']
            assert app_status == expected_status, f"App {app} status is {app_status} instead of {expected_status}"


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
        has_loopbox = bound_args.arguments.get('has_loopbox', None)
        standalone_system = bound_args.arguments.get('standalone_system', None)
        setup_name = bound_args.arguments.get('setup_name', None)
        has_access_ports = True
        interface_wa_called = False
        try:
            if isinstance(devices.dut, JulietSwitch):
                TestToolkit.tested_api = 'NVUE'
                if not hasattr(devices.dut, 'nvl5_access_ports_list'):
                    has_access_ports = False
                if has_access_ports and standalone_system and not has_loopbox:
                    port_name = summarize_ports(devices.dut.nvl5_access_ports_list)
                    selected_port = Port(port_name, "", "")
                    port_state = NvosConsts.LINK_STATE_DOWN
                    selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
                    TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
                if not standalone_system:
                    for port in Configurations.ports_to_disable[setup_name]:
                        selected_port = Port(port, "", "")
                        port_state = NvosConsts.LINK_STATE_DOWN
                        selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
                    TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)

                cluster = Cluster()
                sdn = Sdn()
                ClusterTools().stop_cluster(cluster)
                ClusterTools().start_cluster(cluster, setup_name)
                interfaces_wa = ClusterTools().wa_to_get_active_interface_for_loopbox_systems(cluster, sdn, devices, engines, has_loopbox, setup_name, standalone_system)
                next(interfaces_wa)
                interface_wa_called = True
                with allure.step("Unset Cluster before test starts to run, to make sure we are at the correct init state"):
                    cluster.unset(apply=True)
                    ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')
                    logger.info("Sleeping for 15 seconds to make sure nnx-t docker is down")
                    time.sleep(15)
                # Execute the test function
            return func(*args, **kwargs)
        finally:
            if isinstance(devices.dut, JulietSwitch):
                if has_access_ports and standalone_system and not has_loopbox:
                    port_name = summarize_ports(devices.dut.nvl5_access_ports_list)
                    selected_port = Port(port_name, "", "")
                    port_state = NvosConsts.LINK_STATE_UP
                    selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
                    TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
                if not standalone_system:
                    for port in Configurations.ports_to_disable[setup_name]:
                        selected_port = Port(port, "", "")
                        port_state = NvosConsts.LINK_STATE_UP
                        selected_port.interface.link.state.set(op_param_name=port_state, apply=True, ask_for_confirmation=True).verify_result()
                    TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)
                if interface_wa_called:
                    try:
                        next(interfaces_wa)
                    except StopIteration:
                        pass  # Or handle it if necessary
                if hasattr(devices.dut, 'nvl5_trunk_ports_list') and devices.dut.nvl5_trunk_ports_list:
                    refresh_switch_ports(devices.dut.nvl5_trunk_ports_list, engines)
                with allure.step("Reset cluster state"):
                    if ClusterTools.check_cluster_state(cluster, OutputFormat.json) == 'enabled':
                        cluster.unset(apply=True)
                        ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')
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


class ClusterSimulation:
    # simulation for the SDN maintenance state tests
    # simulate the cluster as topology of 2 racks

    def start_sdn_cluster_simulation(engines, setup_name):
        with allure.step("Start of sdn cluster simulation"):
            cluster = Cluster()

            with allure.step("Disable cluster"):
                ClusterTools.stop_cluster(cluster)

            with allure.step("Generate simulator_config.json file"):
                ClusterSimulation.generate_simulator_config_file(engines.dut)

            with allure.step("Apply the patch for /usr/share/cluster_pkgs/nmx-controller/job.json"):
                ClusterSimulation.apply_patch_for_nmc_controller_job(engines.dut)

            with allure.step("Enable cluster"):
                ClusterTools.start_cluster(cluster, setup_name)

            with allure.step("Config fm config"):
                ClusterSimulation.config_fm_config(engines.dut)

            with allure.step("Wait for nmx-controller to be in ok status"):
                ClusterTools.wait_until_app_expected_status(cluster, ClusterConsts.NMX_CONTROLLER, "ok")

    @staticmethod
    def end_of_sdn_cluster_simulation(engines, setup_name):
        with allure.step("End of sdn cluster simulation"):
            cluster = Cluster()

            with allure.step("Disable cluster"):
                ClusterTools.stop_cluster(cluster)

            with allure.step("Restore /usr/share/cluster_pkgs/nmx-controller/job.json"):
                ClusterSimulation.restore_nmc_controller_job(engines.dut)

            with allure.step("Enable cluster"):
                ClusterTools.start_cluster(cluster, setup_name)

            with allure.step("Reset sdn factory default"):
                Sdn().factory_default.action_reset(param='force')

    @staticmethod
    def generate_simulator_config_file(engine):
        with allure.step("Generate simulator_config.json file in /etc/cluster_infra/conf"):
            file_cont = '{"alids_start_id": 1024, "topology_id": 129, "vendor_id": 713, "gpu_pcie_id": 10496, "switch_pcie_id": 54004, \
                    "partition_start_id": 32766, "partition_default_name": "Default Partition", "gpu_description": "GB100 Nvidia Technologies", \
                    "switch_description": "MF0;mc-gb-nvl-020-001-switch:N5110_LD/U", "chassis1_serial_number": "27XYZ27000001", \
                    "chassis2_serial_number": "27XYZ27000002", "nmxc_uid_start": 0, "gpu_reset_probability": 0, "gpu_reset_timeout": 10, \
                    "switch_reset_probability": 0, "switch_reset_timeout": 10, "max_gpu_down": 0, "gpu_down_probability": 0, "max_switch_down": 0, \
                    "switch_down_probability": 0}'
            cmd = f"echo '{file_cont}' | sudo tee /etc/cluster_infra/conf/simulator_config.json"
            engine.run_cmd(cmd)

    @staticmethod
    def apply_patch_for_nmc_controller_job(engine):
        with allure.step("Apply the patch for /usr/share/cluster_pkgs/nmx-controller/job.json"):
            # Backup and modify job.json
            cmd_backup = "sudo mv /usr/share/cluster_pkgs/nmx-controller/job.json /usr/share/cluster_pkgs/nmx-controller/job.json.bak"
            engine.run_cmd(cmd_backup)
            cmd_modify = "cat /usr/share/cluster_pkgs/nmx-controller/job.json.bak | sed 's/\"\\/cfg\\/sdn_configs\\/fm_config\\.org\"$/\"\\/cfg\\/sdn_configs\\/fm_config\\.org\"\\,\\n                \"--sim-mode\"/' | sudo tee /usr/share/cluster_pkgs/nmx-controller/job.json"
            engine.run_cmd(cmd_modify)

    @staticmethod
    def restore_nmc_controller_job(engine):
        with allure.step("Restore /usr/share/cluster_pkgs/nmx-controller/job.json"):
            cmd_restore = "sudo mv /usr/share/cluster_pkgs/nmx-controller/job.json.bak /usr/share/cluster_pkgs/nmx-controller/job.json"
            engine.run_cmd(cmd_restore)

    @staticmethod
    def config_fm_config(engine):
        with allure.step("Config fm config"):
            cmd = "nv action generate sdn config app nmx-controller type fm_config"
            engine.run_cmd(cmd, validate=True)
            # Get the latest fm_config file
            cmd_get_latest = "ls -Art /host/cluster_infra/app_config/nmx-controller/fm_config/ | tail -n 1"
            latest_fm_config = engine.run_cmd(cmd_get_latest, validate=True).strip()
            fm_config_path = f"/host/cluster_infra/app_config/nmx-controller/fm_config/{latest_fm_config}"
            # Append the new configuration line
            cmd_modify = f"sed '$ a MNNVL_TOPOLOGY=gb200_nvl72r2_c2g4_topology' {fm_config_path} | sudo tee /host/cluster_infra/app_config/nmx-controller/fm_config/fm_cfg"
            engine.run_cmd(cmd_modify, validate=True)
            cmd = "nv action install sdn config app nmx-controller type fm_config files fm_cfg"
            engine.run_cmd(cmd, validate=True)

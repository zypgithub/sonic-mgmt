import logging
import time
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import PlatformConsts, IbConsts, ApiType, OutputFormat, SystemConsts
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.infra.ValidationTool import ValidationTool

logger = logging.getLogger()

NMX_CONTROLLER = 'nmx-controller'
NMX_TELEMETRY = 'nmx-telemetry'
TELEMETRY_SERVICES = ['nmx-connector', 'ib-telemetry']
CONTROLLER_SERVICES = ['nmxc-sdn', 'nmxc-fib', 'redis']
INITIAL_EXPECTED_APPS = [NMX_CONTROLLER, NMX_TELEMETRY]


class ClusterTools:

    @staticmethod
    def start_stop_app(cluster, engines, devices):
        with allure.step("Start/Stop apps"):
            for app in INITIAL_EXPECTED_APPS:
                with allure.step(f"Start app {app} and validate its up"):
                    output = cluster.apps.apps_name[app].action_start_cluster_apps()
                    ClusterTools.verify_app_is_up(engines, app)
                    if app == NMX_CONTROLLER:
                        ClusterTools.verify_lid_value(devices)
                with allure.step("Running 'nv show cluster apps running' command and verifying output"):
                    output = OutputParsingTool.parse_show_output_to_dict(
                        cluster.apps.running.show(output_format=OutputFormat.json),
                        output_format=OutputFormat.json).get_returned_value()
                    app_status = output[app]['status']
                    assert app_status == 'ok', f"App {app} status is {app_status} instead of 'ok"
                with allure.step(f"Stop app {app} and validate its down"):
                    cluster.apps.apps_name[app].action_stop_cluster_apps()
                    logger.info("Sleeping for 5 seconds to make sure all services are down")
                    time.sleep(5)
                    # TBD -- once "running" is working, use it to verify app is not running
                    ClusterTools.verify_app_is_down(engines)
            return ResultObj(result=True)

    @staticmethod
    def start_cluster(cluster, output_format):
        with allure.step("Start cluster"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()

            if output[SystemConsts.STATE] == 'disabled':
                cluster.set(op_param_name="state", op_param_value='enabled', apply=True)
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=output_format),
                    output_format=output_format).get_returned_value()

                with allure.step("Validate state is enabled"):
                    assert output[SystemConsts.STATE] == 'enabled', f"Cluster state is , " \
                        f"{output[SystemConsts.STATE]}, Expected to be: " \
                        f"enabled"

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

            with allure.step("Validate state is disabled"):
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=output_format),
                    output_format=output_format).get_returned_value()
                assert output[SystemConsts.STATE] == 'disabled', f"State state is , " \
                    f"{output[SystemConsts.STATE]}, Expected to be: " \
                    f"disabled"

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
    def start_stop_cluster(cluster, output_format):
        ClusterTools.start_cluster(cluster, output_format)
        ClusterTools.stop_cluster(cluster, output_format)

    @staticmethod
    def verify_apps_running(cluster, expected_state, output_format):
        with allure.step("Running 'nv show cluster apps running' command and verifying output"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.apps.running.show(output_format=output_format),
                output_format=output_format).get_returned_value()

    @staticmethod
    def start_app(cluster, app):
        with allure.step(f"Start app {app}"):
            cluster.apps.apps_name[app].action_start_cluster_apps()

    @staticmethod
    def stop_app(cluster, app):
        with allure.step(f"Stop app {app}"):
            cluster.apps.apps_name[app].action_stop_cluster_apps()

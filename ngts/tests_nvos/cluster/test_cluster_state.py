import logging
import random
import pytest
import time

from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.StressResourcesTool import StressResourcesTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_constants.constants_nvos import PlatformConsts, SystemConsts, OutputFormat, ApiType, IbConsts, NvosConst
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.ib.Ib import Ib
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime


logger = logging.getLogger()
UNDEFINED_STATE = 'undefined'
UNDEFINED_STATE_ERR_MSG = 'Error: At state: \'undefined\' is not one of [\'enabled\', \'disabled\']'
NMXC_CONN = 'nmxc-conn'
NMXC_CONN_STATE_PER_CLUSTER_STATE = {NvosConst.ENABLED: 'up', NvosConst.DISABLED: 'down'}


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_state(engines, devices, test_api):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    try:
        with allure.step("Create Cluster object"):
            cluster = Cluster()

        with allure.step("Running 'nv show cluster' command and parsing output"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()
            with allure.step("Validate initial state is disabled"):
                assert output[SystemConsts.STATE] == NvosConst.DISABLED, f"initial state is , " \
                    f"{output[SystemConsts.STATE]}, Expected to be: " \
                    f"{NvosConst.DISABLED}"
                # TBD - once bug fixed:
                # [NVOS - Design] Bug SW #3982533: [Functional] [NVL5 - NMX] | nmxc-conn field shows NONE value instead of empty string | Assignee: Oren Reiss | Status: Assigned
                # assert output['nmxc-conn'] == NvosConst.DISABLED, f"nmxc-conn state is {output['nmxc-conn']} " \
                #                                                   f"instead of disabled"
                assert NMXC_CONN in output, f"{NMXC_CONN} was not found in {output}"
                assert output[NMXC_CONN] == 'down', f"{NMXC_CONN} state was expected to be down but instead it was {output[NMXC_CONN]}"

        for state in [NvosConst.ENABLED, NvosConst.DISABLED]:
            with allure.step("Running 'nv set cluster state {state}' and validating state changed"):
                cluster.set(op_param_name="state", op_param_value=state, apply=True)
                ClusterTools.wait_for_apps_to_be_in_wanted_state()
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=output_format),
                    output_format=output_format).get_returned_value()

                with allure.step("Validate state is {state}"):
                    assert output[SystemConsts.STATE] == state, f"initial state is , " \
                        f"{output[SystemConsts.STATE]}, Expected to be: " \
                        f"{state}"
                    assert NMXC_CONN in output, f"{NMXC_CONN} was not found in {output}"
                    expected_nmxc_state = NMXC_CONN_STATE_PER_CLUSTER_STATE[output[SystemConsts.STATE]]
                    assert output[NMXC_CONN] == expected_nmxc_state, f"{NMXC_CONN} state was expected to be {expected_nmxc_state} but instead it was {output[NMXC_CONN]}"
                    # TBD - once bug fixed:
                    # [NVOS - Design] Bug SW #3982533: [Functional] [NVL5 - NMX] | nmxc-conn field shows NONE value instead of empty string | Assignee: Oren Reiss | Status: Assigned
                    # assert output['nmxc-conn'] == state, f"nmxc-conn state is {output['nmxc-conn']} " \
                    #                                                   f"instead of {state}"
        with allure.step("Apply a non defined state"):
            output = cluster.set(op_param_name="state", op_param_value=UNDEFINED_STATE)
            output = output.info.split('\n')[1]
            assert output == UNDEFINED_STATE_ERR_MSG, f"Expected error message {UNDEFINED_STATE_ERR_MSG}, " \
                f"actual message received {output}"

        with allure.step("Running 'nv set cluster state enabled' and validating state changed"):
            cluster.set(op_param_name="state", op_param_value=NvosConst.ENABLED, apply=True)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()

            with allure.step("Validate state is enabled"):
                assert output[SystemConsts.STATE] == NvosConst.ENABLED, f"state is , " \
                    f"{output[SystemConsts.STATE]}, Expected to be: " \
                    f"{state}"
                assert NMXC_CONN in output, f"{NMXC_CONN} was not found in {output}"
                expected_nmxc_state = NMXC_CONN_STATE_PER_CLUSTER_STATE[output[SystemConsts.STATE]]
                assert output[NMXC_CONN] == expected_nmxc_state, f"{NMXC_CONN} state was expected to be {expected_nmxc_state} but instead it was {output[NMXC_CONN]}"

            with allure.step("Running 'nv cluster unset' and validate state is back to disabled"):
                cluster.unset(apply=True)
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=output_format),
                    output_format=output_format).get_returned_value()

                with allure.step("Validate state is disabled after running unset command"):
                    assert output[SystemConsts.STATE] == NvosConst.DISABLED, f"State is , " \
                        f"{output[SystemConsts.STATE]}, Expected to be: " \
                        f"{state}"
                    assert NMXC_CONN in output, f"{NMXC_CONN} was not found in {output}"
                    expected_nmxc_state = NMXC_CONN_STATE_PER_CLUSTER_STATE[output[SystemConsts.STATE]]
                    assert output[NMXC_CONN] == expected_nmxc_state, f"{NMXC_CONN} state was expected to be {expected_nmxc_state} but instead it was {output[NMXC_CONN]}"

    finally:
        with allure.step("Reset cluster state"):
            cluster.unset(apply=True)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_stress_cluster_state(engines, devices, test_api, test_name):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()

    try:
        with allure.step("Stress testing cluster state"):
            for i in range(100):
                logger.info(f"Starting iteration {i}")
                result_obj, duration = OperationTime.save_duration('start stop cluster', '', test_name, ClusterTools.start_stop_cluster, cluster, output_format)
                OperationTime.verify_operation_time(duration, 'start stop cluster').verify_result()

    finally:
        with allure.step("Reset cluster state"):
            cluster.unset(apply=True)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_cluster_state_with_stressed_resources(engines, devices, test_api):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()
        installed_packages = []
    try:
        with allure.step("Test cluster with stressed CPU and Memory utilization"):
            # This will run in background &
            installed_packages = StressResourcesTool.stress_cpu_and_memory(engines, devices.dut.core_count)
            timeout = 300  # for example, 300 seconds

            # Get the current time
            start_time = time.time()

            # Loop until the timeout is reached
            while time.time() - start_time < timeout:
                result_obj, duration = OperationTime.save_duration('start stop cluster', '', test_name, ClusterTools.start_stop_cluster, cluster, output_format)
                OperationTime.verify_operation_time(duration, 'start stop cluster').verify_result()
                logger.info("Sleeping for 30 seconds between iterations")
                time.sleep(30)
    finally:
        with allure.step("Reset cluster state"):
            cluster.unset(apply=True)
            ClusterTools.wait_for_apps_to_be_in_wanted_state()
        if installed_packages:
            StressResourcesTool.delete_pacages(engines, installed_packages)

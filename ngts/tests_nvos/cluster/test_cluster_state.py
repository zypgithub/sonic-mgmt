import logging
import random
import pytest

from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_constants.constants_nvos import PlatformConsts, SystemConsts, OutputFormat, ApiType, IbConsts, NvosConst
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.ib.Ib import Ib
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools


logger = logging.getLogger()
NMX_CONTROLLER = 'nmx-controller'
NMX_TELEMETRY = 'nmx-telemetry'
INITIAL_EXPECTED_APPS = [NMX_CONTROLLER, NMX_TELEMETRY]
UNDEFINED_STATE = 'undefined'
UNDEFINED_STATE_ERR_MSG = 'Error: At state: \'undefined\' is not one of [\'enabled\', \'disabled\']'


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

        for state in [NvosConst.ENABLED, NvosConst.DISABLED]:
            with allure.step("Running 'nv set cluster state {state}' and validating state changed"):
                cluster.set(op_param_name="state", op_param_value=state, apply=True)
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=output_format),
                    output_format=output_format).get_returned_value()

                with allure.step("Validate state is {state}"):
                    assert output[SystemConsts.STATE] == state, f"initial state is , " \
                        f"{output[SystemConsts.STATE]}, Expected to be: " \
                        f"{state}"
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
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()

            with allure.step("Validate state is enabled"):
                assert output[SystemConsts.STATE] == NvosConst.ENABLED, f"state is , " \
                    f"{output[SystemConsts.STATE]}, Expected to be: " \
                    f"{state}"

            with allure.step("Running 'nv cluster unset' and validate state is back to disabled"):
                cluster.unset(apply=True)
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=output_format),
                    output_format=output_format).get_returned_value()

                with allure.step("Validate state is disabled after running unset command"):
                    assert output[SystemConsts.STATE] == NvosConst.DISABLED, f"State is , " \
                        f"{output[SystemConsts.STATE]}, Expected to be: " \
                        f"{state}"
    finally:
        with allure.step("Restore cluster to initial state"):
            output = OutputParsingTool.parse_show_output_to_dict(
                cluster.show(output_format=output_format),
                output_format=output_format).get_returned_value()
            if output[SystemConsts.STATE] == NvosConst.ENABLED:
                cluster.set(op_param_name="state", op_param_value=NvosConst.DISABLED, apply=True)


@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_stress_cluster_state(engines, devices, test_api):
    TestToolkit.tested_api = test_api
    output_format = OutputFormat.json

    with allure.step("Create Cluster object"):
        cluster = Cluster()

    try:
        with allure.step("Stress testing cluster state"):
            for i in range(100):
                logger.info(f"Starting iteration {i}")
                result_obj, duration = OperationTime.save_duration('start/stop cluster', '', test_name, ClusterTools.start_stop_cluster, cluster, output_format)
                OperationTime.verify_operation_time(duration, 'start stop cluster app').verify_result()

    finally:
        with allure.step("Stop cluster"):
            ClusterTools.stop_cluster(cluster, output_format)

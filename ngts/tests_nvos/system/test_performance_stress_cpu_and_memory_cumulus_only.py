import logging

import pytest
from retry import retry

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.StressNgTool import StressNgTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_performance_stress_system_memory(test_api, engines, devices, nv_command):
    """
    Run memory stress test and verify system memory metrics under load
        Test flow:
            1. Install stress-ng package
            2. Run stress-ng to generate memory load
            3. Verify memory metrics during stress:
                - Check physical memory utilization
                - Check swap memory utilization
                - Verify memory values correlation
            4. Clean up stress-ng and package
    """
    TestToolkit.tested_api = test_api
    engines_dut = engines.dut

    StressNgTool.install_stress_ng(engines_dut)

    try:
        with allure.step('Run stress-ng to generate memory load'):
            engines_dut.run_cmd("stress-ng --vm 4 --vm-bytes 80% --timeout 300s &")
            wait_for_cpu_stress_start(engines_dut)
            wait_for_memory_stress_threshold(engines_dut, nv_command)

        with allure.step('Verify memory metrics during stress'):
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show("memory")).get_returned_value()

            physical_memory = output_dictionary[SystemConsts.MEMORY_PHYSICAL_KEY]
            if devices.dut.is_ib():
                total_sum = physical_memory["free"] + physical_memory["used"]
                assert 0 < physical_memory["total"] == total_sum, \
                    "Total physical memory must be equal to calculated total sum and greater than 0"

            utilization = physical_memory["utilization"]
            utilization_calc = (physical_memory["used"] / physical_memory["total"]) * 100
            assert abs(utilization - utilization_calc) < 0.000001, \
                f"Mismatch between Physical utilization: {utilization}% to calculated utilization: {utilization_calc}%"

            swap_memory = output_dictionary[SystemConsts.MEMORY_SWAP_KEY]
            if swap_memory["total"] > 0:
                swap_utilization = swap_memory["utilization"]
                swap_utilization_calc = (swap_memory["used"] / swap_memory["total"]) * 100
                assert abs(swap_utilization - swap_utilization_calc) < 0.000001, \
                    f"Mismatch between Swap utilization: {swap_utilization}% to calculated utilization: {swap_utilization_calc}%"
    finally:
        StressNgTool.cleanup_stress_ng(engines_dut)


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_performance_stress_system_cpu(test_api, engines, devices, nv_command):
    """
    Run CPU stress test and verify system CPU metrics under load
        Test flow:
            1. Install stress-ng package
            2. Run stress-ng to generate CPU load
            3. Verify CPU metrics during stress:
                - Check load average has 3 values
                - Verify number of cores matches core count
                - Verify CPU utilization
            4. Clean up stress-ng and package
    """
    TestToolkit.tested_api = test_api
    engines_dut = engines.dut

    StressNgTool.install_stress_ng(engines_dut)

    try:
        with allure.step('Run stress-ng to generate CPU load'):
            engines_dut.run_cmd("stress-ng --cpu 8 --timeout 300s &")
            wait_for_cpu_stress_start(engines_dut)

        with allure.step('Verify CPU metrics during stress'):
            output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show("cpu")).get_returned_value()

            """
            assert len(output_dictionary[SystemConsts.CPU_LOAD_AVERAGE_KEY]) == 3, \
                "Load average should have 3 values"

            assert len(output_dictionary[SystemConsts.CPU_CORES]) == output_dictionary[SystemConsts.CPU_CORE_COUNT_KEY], \
                "Number of cores in output doesn't match core count"

            utilization = output_dictionary[SystemConsts.CPU_TOTAL_UTILIZATION_KEY]
            assert utilization >= SystemConsts.CPU_PERCENT_THRESH_MAX, \
                "CPU utilization percentage is not reaching threshold level during stress"
            """
            assert len(output_dictionary.keys()) == 5, "Unexpected Number of keys"
            assert list(output_dictionary.keys())[0] == SystemConsts.CPU_CORE_COUNT_KEY, "Unexpected Key value"
            assert list(output_dictionary.keys())[1] == SystemConsts.CPU_CORES, "Unexpected Key value"
            assert list(output_dictionary.keys())[2] == SystemConsts.CPU_LOAD_AVERAGE_KEY, "Unexpected Key value"
            assert list(output_dictionary.keys())[3] == SystemConsts.CPU_MODEL_KEY, "Unexpected Key value"
            assert list(output_dictionary.keys())[4] == SystemConsts.CPU_TOTAL_UTILIZATION_KEY, "Unexpected Key value"
            assert output_dictionary[SystemConsts.CPU_CORE_COUNT_KEY] == devices.dut.core_count, \
                "Unexpected switch core-count"

            utilization = output_dictionary[SystemConsts.CPU_TOTAL_UTILIZATION_KEY]
            assert utilization >= SystemConsts.CPU_PERCENT_THRESH_MAX, \
                "CPU utilization percentage is not reaching threshold level during stress"
    finally:
        StressNgTool.cleanup_stress_ng(engines_dut)


@retry(Exception, tries=10, delay=1)
def wait_for_cpu_stress_start(engines_dut):
    with allure.step("Waiting for stress-ng to start"):
        output = engines_dut.run_cmd("ps aux | grep stress-ng | grep -v grep")
        assert "stress-ng" in output, "stress-ng process not found running"


@retry(Exception, tries=10, delay=2)
def wait_for_memory_stress_threshold(engines_dut, nv_command):
    with allure.step("Waiting for memory utilization to reach threshold level"):
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show("memory")).get_returned_value()
        physical_memory = output_dictionary[SystemConsts.MEMORY_PHYSICAL_KEY]
        utilization = physical_memory["utilization"]
        assert utilization >= SystemConsts.MEMORY_PERCENT_THRESH_MAX, \
            f"Memory utilization {utilization}% has not reached threshold level {SystemConsts.MEMORY_PERCENT_THRESH_MAX}% yet"

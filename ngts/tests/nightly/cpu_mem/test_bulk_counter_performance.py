import logging
import pytest

from collections import namedtuple, Counter
from ngts.helpers.counterpoll_helper import CounterpollHelper
from ngts.helpers.sonic_branch_helper import is_sanitizer_image
from ngts.constants.constants import CounterpollConstants, SonicConst
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure


logger = logging.getLogger()
allure.logger = logger

MONIT_RESULT = namedtuple('MonitResult', ['processes', 'memory'])
MILLISECOND_TO_SECOND = 1000


AMPLIFY_FACTORY_FOR_SIMX_MEMORY_THR = {
    "x86_64-mlnx_msn2700_simx-r0": 1,
    "x86_64-mlnx_msn3700_simx-r0": 1.2,
    "x86_64-nvidia_sn4280_simx-r0": 1.25,
    "x86_64-mlnx_msn4700_simx-r0": 1.25,
    "x86_64-nvidia_sn5600_simx-r0": 1.25,
}


@pytest.fixture(params=[CounterpollConstants.WATERMARK])
def counterpoll_type(request):
    """
    Pytest fixture used to return the counterpoll test type
    :param request:
    :return: counterpoll test to be tested
    """
    return request.param


@pytest.fixture()
def restore_counter_poll(cli_objects, topology_obj):
    """
    Pytest fixture used to restore original counterpoll configuration
    :param cli_objects: cli_objects fixture
    :param topology_obj: topology_obj fixture
    """
    cli_obj = cli_objects.dut
    yield
    with allure.step("Reload config to refresh running configuration"):
        cli_obj.general.reboot_reload_flow(r_type=SonicConst.CONFIG_RELOAD_CMD, topology_obj=topology_obj)


@pytest.fixture(scope='module')
def setup_thresholds(topology_obj, is_simx, platform_params):
    """
    Pytest fixture used to return memory and cpu threshold value and high cpu consume processes list
    :param topology: topology fixture object
    :return: memory threshold, cpu threshold, high cpu consume processes list
    """
    cpu_threshold = CounterpollConstants.CPU_THRESHOLD_FOR_ORDINARY_PROCESS
    memory_threshold = CounterpollConstants.MEMORY_THRESHOLD
    if is_simx:
        # For simx platform we need to increase the memory threshold,
        # because the performance of simx is lower than the physical platform.
        # The initial value of amplify_factor_for_simx_memory_thr is got based on the test results
        memory_threshold = memory_threshold * AMPLIFY_FACTORY_FOR_SIMX_MEMORY_THR[platform_params.platform]
    high_cpu_consume_procs = {}
    is_asan = is_sanitizer_image(topology_obj)
    if is_asan:
        memory_threshold = CounterpollConstants.MEMORY_THRESHOLD_ASAN
    # The CPU usage of `sx_sdk` on mellanox is expected to be higher, and the actual CPU usage
    # is correlated with the number of ports
    high_cpu_consume_procs[CounterpollConstants.SX_SDK] = CounterpollConstants.CPU_THRESHOLD_FOR_HIGH_CONSUME_PROCESS
    return memory_threshold, cpu_threshold, high_cpu_consume_procs


@pytest.fixture(scope='module')
def bulk_counter_cpu_threshold():
    """
    Pytest fixture used to return counterpoll cpu usage threshold for watermark
    :return: counterpoll cpu usage threshold for watermark
    """
    counterpoll_cpu_usage_threshold = {CounterpollConstants.WATERMARK: CounterpollConstants.COUNTERPOLL_CPU_USAGE_THRESHOLD,
                                       CounterpollConstants.PORT: CounterpollConstants.COUNTERPOLL_CPU_USAGE_THRESHOLD,
                                       CounterpollConstants.RIF: CounterpollConstants.COUNTERPOLL_CPU_USAGE_THRESHOLD,
                                       CounterpollConstants.PG_DROP: CounterpollConstants.COUNTERPOLL_CPU_USAGE_THRESHOLD,
                                       CounterpollConstants.QUEUE: CounterpollConstants.COUNTERPOLL_CPU_USAGE_THRESHOLD,
                                       CounterpollConstants.PORT_BUFFER_DROP: CounterpollConstants.COUNTERPOLL_CPU_USAGE_THRESHOLD,
                                       CounterpollConstants.ACL: CounterpollConstants.COUNTERPOLL_CPU_USAGE_THRESHOLD,
                                       CounterpollConstants.TUNNEL_STAT: CounterpollConstants.COUNTERPOLL_CPU_USAGE_THRESHOLD}
    return counterpoll_cpu_usage_threshold


def test_cpu_memory_usage_all_processes(engines, setup_thresholds):
    """
    This method is used to check whether DUT memory usage and process cpu usage are within threshold.
    :param engines: engines fixture
    :param setup_thresholds: setup_thresholds fixture
    """
    with allure.step(f"Collect CPU and Memory usage of DUT - interval: {CounterpollConstants.CPU_MEMORY_SAMPLE_INTERVAL_1} iterations: {CounterpollConstants.CPU_MEMORY_SAMPLE_ITERATION_1}"):
        monit_results = CounterpollHelper.monit_process(engines, interval=CounterpollConstants.CPU_MEMORY_SAMPLE_INTERVAL_1, iterations=CounterpollConstants.CPU_MEMORY_SAMPLE_ITERATION_1)

    with allure.step("Check and then analyze CPU and Memory usage"):
        CounterpollHelper.check_and_analyse_cpu_memory_usage(monit_results, setup_thresholds)


def test_cpu_memory_usage_desired_process(engines, cli_objects, setup_thresholds, restore_counter_poll, counterpoll_type, bulk_counter_cpu_threshold):
    """
    This method is used to check whether DUT memory usage and process cpu usage are within threshold for specific bulk counter
    Focus on checking desired process, such as sx_sdk
    Disable all counterpoll types except tested one
    Collect memory and CPUs usage for 60 secs
    Compare the memory usage with the memory threshold
    Compare the average cpu usage with the cpu threshold for the specified progress
    Restore counterpoll status
    :param engines: engines fixture
    :param cli_objects: cli_objects fixture
    :param setup_thresholds: setup_threshold fixture
    :param restore_counter_poll: restore_counter_poll fixture
    :param counterpoll_type: restore_counter_poll fixture
    :param bulk_counter_cpu_threshold: bulk_counter_cpu_threshold fixture
    """
    cli_obj = cli_objects.dut
    program_to_check = CounterpollConstants.SX_SDK
    if program_to_check is None:
        pytest.skip("Skip no program is offered to check")

    memory_threshold, _, _ = setup_thresholds
    counterpoll_cpu_usage_threshold = bulk_counter_cpu_threshold[counterpoll_type]

    with allure.step(f"Disable all counterpoll except {counterpoll_type}"):
        CounterpollHelper.disable_all_counterpoll_type_except_tested(engines, cli_obj, counterpoll_type)

    with allure.step(f"Configure {counterpoll_type} interval to {CounterpollConstants.WATERMARK_INTERVAL_1}"):
        cli_obj.counterpoll.set_counterpoll_interval(counterpoll_type, CounterpollConstants.WATERMARK_INTERVAL_1)

    with allure.step(
            f"Collect CPU and Memory usage of DUT - interval: {CounterpollConstants.CPU_MEMORY_SAMPLE_INTERVAL_2} iterations: {CounterpollConstants.CPU_MEMORY_SAMPLE_ITERATION_2}"):
        monit_results = CounterpollHelper.monit_process(engines, iterations=CounterpollConstants.CPU_MEMORY_SAMPLE_ITERATION_2, interval=CounterpollConstants.CPU_MEMORY_SAMPLE_INTERVAL_2)

    with allure.step(f"Configure {counterpoll_type} interval to default value {CounterpollConstants.WATERMARK_INTERVAL_DEFAULT}"):
        cli_obj.counterpoll.set_counterpoll_interval(counterpoll_type, CounterpollConstants.WATERMARK_INTERVAL_DEFAULT)

    with allure.step("Calculate average CPU usage"):
        poll_interval = CounterpollConstants.COUNTERPOLL_INTERVAL[counterpoll_type] // MILLISECOND_TO_SECOND
        outstanding_mem_polls = {}
        cpu_usage_program_to_check = []
        CounterpollHelper.prepare_ram_cpu_usage_results(memory_threshold, monit_results, outstanding_mem_polls, program_to_check, cpu_usage_program_to_check)

        cpu_usage_average = CounterpollHelper.caculate_cpu_usge_average_value(CounterpollHelper.extract_valid_cpu_usage_data(cpu_usage_program_to_check, poll_interval), cpu_usage_program_to_check)
        logger.info(f"Average cpu_usage is {cpu_usage_average}")

    assert cpu_usage_average < counterpoll_cpu_usage_threshold, f"cpu_usage_average of {program_to_check} exceeds the cpu threshold:{counterpoll_cpu_usage_threshold}"
    assert not outstanding_mem_polls, f"Memory {outstanding_mem_polls} exceeds the memory threshold {memory_threshold}"

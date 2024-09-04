import pytest
import logging
from ngts.helpers.new_hw_thermal_control_helper import collect_sensors_info, get_tc_config, is_support_new_hw_tc, TC_CONST
from ngts.tests.conftest import toggle_rsyslog_configurations


logger = logging.getLogger()


def pytest_addoption(parser):
    """
        Adds options to pytest that are used by the new hw thermal control tests.
    """
    parser.addoption(
        "--sensor_type",
        type="choice",
        action="store",
        default="random",
        choices=["all", "random", "asic", "ambient", "cpu_pack", "module", "voltmon", "sodimm"],
        help="sensor type, the value could be all, random, asic, ambient, cpu_pack, module, voltmon, sodimm",
    )


@pytest.fixture(scope='package', autouse=True)
def skipping_new_hw_tc_tests(cli_objects, is_simx):
    if not is_support_new_hw_tc(cli_objects, is_simx):
        pytest.skip("The new hw tc feature is missing, skipping the test case")


@pytest.fixture(scope='package', autouse=True)
def get_dut_supported_sensors_and_tc_config(skipping_new_hw_tc_tests, engines, cli_objects):
    sensor_temperature_test_list = collect_sensors_info(cli_objects, engines.dut)
    tc_config_dict = get_tc_config(cli_objects)

    return sensor_temperature_test_list, tc_config_dict


@pytest.fixture(scope='package', autouse=True)
def recover_tc_service(skipping_new_hw_tc_tests, engines, cli_objects):

    yield
    if cli_objects.dut.general.stat(TC_CONST.SUSPEND_FILE)["exists"]:
        logger.warning("suspend file is not cleanup, please check the reason")
        engines.dut.run_cmd(f'sudo rm {TC_CONST.SUSPEND_FILE}')
    if not cli_objects.dut.hw_mgmt.is_thermal_control_running():
        logger.warning("tc is not running, please check the reason")
        cli_objects.dut.hw_mgmt.start_thermal_control()


@pytest.fixture(scope='package', autouse=True)
def disable_rsyslog_repeated_msg_reduction(engines, is_simx):
    dut_engine = engines.dut
    toggle_rsyslog_configurations(dut_engine, ['$RepeatedMsgReduction on'], 'pmon', 'disable')

    yield

    toggle_rsyslog_configurations(dut_engine, ['$RepeatedMsgReduction on'], 'pmon', 'enable')


@pytest.fixture(scope='function', autouse=True)
def print_test_start_end_tc_log(engines):
    get_last_one_line_tc_log = f'tail {TC_CONST.TC_LOG_FILE}  -n 1'
    logger.info(f"tc_log_start: {engines.dut.run_cmd(get_last_one_line_tc_log)}")

    yield

    logger.info(f"tc_log_end: {engines.dut.run_cmd(get_last_one_line_tc_log)}")

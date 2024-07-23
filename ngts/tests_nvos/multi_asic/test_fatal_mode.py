import logging
import time
from datetime import datetime
from os import path
from typing import Union

import pytest
from retry.api import retry_call

from ngts.nvos_constants.constants_nvos import ApiType, HealthConsts, NvosConst, ActionConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.system.clock.ClockConsts import ClockConsts
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()

SETTINGS = {"clear_time": 1, "events_count": 2}
NUM_TRIES_TO_RECOVER_AT_TEARDOWN = 4


#  FIXTURES AND TEARDOWN
################################################################################


@pytest.fixture(autouse=True)
def fatal_mode_setup_and_teardown(test_name, engines):
    if test_name == test_post_fatal_recovery.__name__:
        yield
        return

    with allure.step(f"Asserting health-status is OK before starting {test_name}"):
        assert (OutputParsingTool.parse_json_str_to_dictionary(System().health.show()).get_returned_value()
                [HealthConsts.STATUS]) == HealthConsts.OK

    _set_settings(**SETTINGS)
    yield

    with allure.step("Reverting fatal-mode settings"):
        Fae().system.fatal.unset()
        TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config(engines.dut, True)
        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engines.dut)


def test_post_fatal_recovery(engines):
    """
    Teardown called from .db file to make sure switch is not in fatal mode when the tests finish.
    """
    engines.dut.engine.set_base_prompt('$')  # Let the engine find the current prompt
    with allure.step("Check system health at end of test"):
        health_status = (OutputParsingTool.parse_json_str_to_dictionary(System().health.show())
                         .get_returned_value()[HealthConsts.STATUS])
        for i in range(NUM_TRIES_TO_RECOVER_AT_TEARDOWN):
            if health_status == HealthConsts.OK:
                break
            else:
                with allure.step(f"{health_status=}, will attempt to recover before moving-on to next test"):
                    try:
                        if health_status == HealthConsts.FATAL:
                            _manual_exit_fatal_mode(engines.dut)
                        elif health_status == HealthConsts.NOT_OK:
                            _manual_reboot(engines.dut)
                            _wait_to_exit_fatal()
                        health_status = (OutputParsingTool.parse_json_str_to_dictionary(System().health.show())
                                         .get_returned_value()[HealthConsts.STATUS])
                    except Exception:
                        if i == NUM_TRIES_TO_RECOVER_AT_TEARDOWN - 1:
                            raise

    engines.dut.engine.set_base_prompt('$')  # Let the engine find the current prompt


#  TESTS
################################################################################


@pytest.mark.checklist
@pytest.mark.fatal_mode
def test_flow_until_soft_reset(engines, devices, random_asic):
    """
    Test that health-events trigger fatal mode properly, and that the system leaves fatal mode when everything is fine.
    """
    TestToolkit.tested_api = ApiType.NVUE

    with allure.step(f"Trigger soft reset 1 or 2 times (randomly)"):
        repetitions = RandomizationTool.select_random_value([1, 2]).get_returned_value()
        logger.info(f"Soft reset will be triggered {repetitions} time{'s' if repetitions > 1 else ''}")
        for i in range(repetitions):
            _trigger_soft_reset(i == 0, random_asic)

    _wait_to_exit_fatal()


@pytest.mark.checklist
@pytest.mark.fatal_mode
def test_flow_until_reboot(engines, devices, random_asic, test_name):
    """
    Test repetitive health-events cause "soft reset" and then reboot. After everything is fine, leave fatal mode.
    Also generate tech-support and assert the dump contains /etc/system_fatal file.
    """
    TestToolkit.tested_api = ApiType.OPENAPI

    _trigger_soft_reset(False, random_asic)
    _trigger_soft_reset(True, random_asic)

    with allure.step(f"Trigger switch reboot 1 or 2 times (randomly)"):
        repetitions = RandomizationTool.select_random_value([1, 2]).get_returned_value()
        logger.info(f"Reboot will be triggered {repetitions} time{'s' if repetitions > 1 else ''}")
        for _ in range(repetitions):
            _trigger_reboot(random_asic)

    # todo: _check_tech_support(). nv set fae system fatal clear-time 4 (?)
    _wait_to_exit_fatal()


@pytest.mark.checklist
@pytest.mark.fatal_mode
def test_flow_until_close_ports(engines, devices, random_asic):
    """
    Test the full flow – repetitive health-events cause "soft reset", followed by reboot, followed by ports-close, and
    the system remains in this state.
    """
    TestToolkit.tested_api = ApiType.NVUE
    _set_settings(reboot_count=1)

    _trigger_soft_reset(False, random_asic)
    _trigger_soft_reset(True, random_asic)
    _trigger_reboot(random_asic)

    with allure.step("Trigger final fatal-mode reboot after which ports are closed"):
        _trigger_reboot(random_asic)
        # booting will take extra ~10 minutes waiting for the system-ready timeout (for CLI to become available)
        # todo: make it shorter somehow
        _assert_system_fatal_mode(True, )
        _assert_close_ports()

    with allure.step("Assert system remains in fatal mode with closed ports even after the clear-time"):
        _wait(1, 30)
        _assert_system_fatal_mode(True, )
        _assert_close_ports()

    # skip this because it's not very important and it takes way too long
    # with allure.step("Assert system remains in fatal mode with closed ports even after reboot"):
    #     _manual_reboot(engines.dut)  # again extra ~10 minutes
    #     _assert_system_fatal_mode(True, )
    #     _assert_close_ports()

    _manual_exit_fatal_mode(engines.dut)


@pytest.mark.checklist
@pytest.mark.fatal_mode
def test_remain_in_fatal_mode_until_manual_reboot(engines, devices, random_asic):
    """
    If after reboot or soft-reset there's a single health-event within n minutes, test that the system remains in
    fatal mode "forever" (no timeout) and does not restart the reboot-counter. After the user performs a manual
    reboot, test that the system exits fatal mode if no new events happen.
    """
    TestToolkit.tested_api = ApiType.OPENAPI
    _set_settings(events_time=1)

    _trigger_soft_reset(False, random_asic)

    with allure.step("Generate 1 event and verify fatal-mode doesn't time-out"):
        _simulate_events(1, random_asic, False)
        _assert_system_fatal_mode(True, )
        _wait(1, 30)
        _assert_system_fatal_mode(True, )

    _trigger_soft_reset(True, random_asic)
    _assert_system_fatal_file(0)

    with allure.step("Generate 1 event and verify fatal-mode doesn't time-out"):
        _simulate_events(1, random_asic, False)
        _wait(1, 30)
        _assert_system_fatal_mode(True, )
        _assert_system_fatal_file(0)

    with allure.step("Do manual reboot and check that system remains in fatal mode, then exits after 3 minutes"):
        TEMP_CLEAR_TIME = 3
        _set_settings(clear_time=TEMP_CLEAR_TIME)
        _manual_reboot(engines.dut)
        _assert_system_fatal_mode(True, )
        _assert_system_fatal_file(0)
        _wait_to_exit_fatal(TEMP_CLEAR_TIME)


@pytest.mark.checklist
@pytest.mark.fatal_mode
def _test_negative_flow_time_window(engines, devices, random_asic):
    """
    Test that fatal-mode is triggered only when there were the right number of health-events in the proper time window.
    """
    TestToolkit.tested_api = ApiType.NVUE
    _set_settings(events_time=3, events_count=5)
    _simulate_events(1, random_asic)
    _wait(1, 15)
    _simulate_events(1, random_asic)
    _wait(1, 30)
    _simulate_events(3, random_asic)
    _assert_syncd_restart(expect_restart=False)
    _assert_system_fatal_mode(False, False)
    _trigger_soft_reset(False, random_asic, 1)
    _wait_to_exit_fatal()


@pytest.mark.checklist
@pytest.mark.fatal_mode
def test_negative_flow_with_warnings(engines, devices, random_asic):
    """Test that fatal-mode is not triggered by health events with irrelevant event_ids."""
    TestToolkit.tested_api = ApiType.OPENAPI
    _set_settings(events_count=3)
    event_list = _get_random_event_list(2) + ["warning"]
    RandomizationTool.shuffle_in_place(event_list)
    _simulate_events(event_list, random_asic)
    _assert_syncd_restart(expect_restart=False)
    _assert_system_fatal_mode(False, False)


# todo: ask Ayal Lior for specs
@pytest.mark.checklist
@pytest.mark.fatal_mode
def _test_health_events_for_different_asics(engines, devices):
    """Test that fatal-mode is not triggered if the health events happen for different ASICs."""
    TestToolkit.tested_api = ApiType.NVUE
    _set_settings(events_count=3)
    asic1, asic2 = RandomizationTool.select_random_asics(devices.dut, how_many=2).get_returned_value()
    _simulate_events(2, asic1)
    _simulate_events(2, asic2)
    _assert_syncd_restart(expect_restart=False)
    _assert_system_fatal_mode(False, False)


# todo: skipped https://redmine.mellanox.com/issues/3866364
@pytest.mark.checklist
@pytest.mark.fatal_mode
def _test_disable_fatal_mode_reboot(engines, devices, random_asic):
    """Test that the "reboot-state" setting is working properly."""
    TestToolkit.tested_api = ApiType.OPENAPI
    _set_settings(reboot_state=NvosConst.DISABLED)

    with allure.step(f"Trigger fatal mode with no restart"):
        _simulate_events(2, random_asic)
        _assert_syncd_restart(expect_restart=False)
        _assert_system_fatal_mode(True, True)

    with allure.step(f"Simulate more events and assert still no restart"):
        _simulate_events(2, random_asic)
        _assert_syncd_restart(expect_restart=False)
        _assert_system_fatal_mode(True, False)

    _wait_to_exit_fatal()


# todo
@pytest.mark.parametrize('add_one_hour', [True, False])
@pytest.mark.checklist
@pytest.mark.fatal_mode
def _test_daylight_saving_time(engines, devices, random_asic, add_one_hour):
    """
    Test that moving the clock does not disturb the timekeeping of the fatal-mode feature.
    add_one_hour is True for simulating entering DST (adding 1 hour), False for exiting DST (moving back 1 hour).
    """
    TestToolkit.tested_api = ApiType.NVUE
    system = System()

    try:
        _set_dst(not add_one_hour, system)
        _set_settings(events_time=1)

        with allure.step(f"Simulate {'enter' if add_one_hour else 'exit'} DST between 2 health events"):
            _simulate_events(1, random_asic)
            _set_dst(add_one_hour, system)
            _trigger_soft_reset(False, random_asic, 1)

        with allure.step(f"Simulate {'exit' if add_one_hour else 'enter'} DST while waiting for fatal-mode timeout"):
            _set_dst(not add_one_hour, system)
            _assert_system_fatal_mode(True, False)
            _wait_to_exit_fatal()

    finally:
        system.unset(ClockConsts.TIMEZONE, apply=True)


# todo 5.12.	test_fail_to_start_once_after_firmware_burn
# todo 5.13.	test_burn_failure_and_manual_exit_from_fatal_mode
# todo 5.14.	test_exit_fatal_by_factory_reset
# todo 5.15.	test_exit_fatal_by_image_install


# HELPER FUNCTIONS
################################################################################


def _set_settings(reboot_state=None, reboot_count=None, events_time=None, events_count=None, clear_time=None):
    with allure.step("Change settings"):
        fae = Fae()
        for var in _set_settings.__code__.co_varnames[:_set_settings.__code__.co_argcount]:
            if eval(var) is not None:
                fae.system.fatal.set(var.replace('_', '-'), eval(var))
        TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config(TestToolkit.engines.dut, True)
        TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(TestToolkit.engines.dut)


def _get_random_event_list(n: int) -> list:
    return RandomizationTool.select_random_values(list(HealthConsts.FATAL_EVENT_IDS),
                                                  number_of_values_to_select=n,
                                                  allow_repetitions=True).get_returned_value()


def _trigger_soft_reset(already_in_fatal: bool, asic: int, number_of_events=2):
    with allure.step(_trigger_soft_reset.__name__ +
                     ': Generating health-events to trigger fatal-mode "soft-reset" (syncd restart)'):
        _simulate_events(number_of_events, asic, not already_in_fatal)
        _assert_syncd_restart()
        _assert_system_fatal_mode(True, not already_in_fatal)
        _wait(0, 10)


def _trigger_reboot(asic: int, number_of_events=2):
    with allure.step(_trigger_reboot.__name__ + ': Generating health-events to trigger fatal-mode reboot'):
        _simulate_events(number_of_events, asic, False)
        _assert_reboot()
        _assert_system_fatal_mode(True, )


def _simulate_events(number_of_events: Union[int, list], asic: int, verify_non_fatal=True):
    """
    Generates health-events relevant for fatal mode, on a given ASIC.
    number_of_events can instead contain an ordered list of the actual event_ids.
    todo If verify_non_fatal: after each event except the last, verify system is not in fatal mode.
    """
    len_events = number_of_events if isinstance(number_of_events, int) else len(number_of_events)
    with allure.step(f"{_simulate_events.__name__}: Simulating {len_events} MFDEs on ASIC{asic}"):
        event_list = (number_of_events if isinstance(number_of_events, list) else _get_random_event_list(number_of_events))
        for event_id in event_list:
            _simulate_event(event_id, asic)
            _wait(0, 10)  # fatal doesn't work if we don't wait between events


def _simulate_event(event_id, asic):
    """Runs the command that simulates a health events and asserts that it worked (returned no output)."""
    with allure.step(f"{_simulate_event.__name__}({event_id=}, {asic=})"):
        # todo: check serial-log to make sure the event was seen. or log. or show system events.
        cmd = HealthConsts.FATAL_HEALTH_EVENT_SIMULATION[event_id].format(asic=asic)
        output = TestToolkit.engines.dut.run_cmd(cmd).strip()
        assert not output


def _wait(minutes, seconds=0):
    logger.info(f"sleep {minutes}:{seconds:02} minutes")
    time.sleep(60 * minutes + seconds)


def _wait_to_exit_fatal(minutes=None):
    """Waits, then asserts system leaves fatal mode after desired time."""
    minutes = minutes or SETTINGS["clear_time"]
    with allure.step(_wait_to_exit_fatal.__name__):
        _wait(minutes, seconds=13)
        _assert_system_fatal_mode(False, state_just_changed=True)


def _manual_exit_fatal_mode(engine):
    """nv action resume fae system fatal monitor force. Verify the system reboots, exits fatal mode and opens ports."""
    with allure.step(f"{_manual_exit_fatal_mode.__name__}: Run FAE command to manually exit fatal mode and check that "
                     f"the system reboots to normal"):
        Fae().system.fatal.monitor.action(ActionConsts.RESUME, param_name="force", expect_reboot=True,
                                          output_format=None, dut_engine=engine, expected_output="Performing reboot"
                                          ).verify_result()
        _wait(0, 20)
        _assert_system_fatal_mode(False)
        # todo assert ports are open


def _manual_reboot(engine):
    with allure.step(f"{_manual_reboot.__name__}: Perform reboot by user"):
        System().reboot.action_reboot(engine, params='force').verify_result()
        _reset_base_prompt(engine)


def _set_dst(enter: bool, system: System):
    """Enter or exit DST (plus/minus 1 hour in system clock)."""
    with allure.step(f"{_set_dst}: Simulate {'entering' if enter else 'exiting'} DST"):
        if enter:
            system.set(ClockConsts.TIMEZONE, ClockConsts.DST_TIMEZONE, apply=True)
        else:
            system.set(ClockConsts.TIMEZONE, ClockConsts.DEFAULT_TIMEZONE, apply=True)


def _assert_system_fatal_mode(fatal: bool, state_just_changed=False):
    """
    Asserts system health status, led, health-issue and fatal-mode prompt are in Fatal mode (or are OK if fatal==False).
    If state_just_changed then also assert a system event was raised.
    if fatal and state_just_changed then wait for the system to detect fatal mode.
    """
    with allure.step(f"{_assert_system_fatal_mode.__name__}: Verify fatal mode is {fatal}"):
        system = System()
        engine = TestToolkit.engines.dut
        if fatal and state_just_changed:
            with allure.step("Check system health until it enters fatal mode"):
                health_dict = retry_call(_assert_health_fatal, [system, True],
                                         exceptions=AssertionError, tries=6, delay=3)
        else:
            with allure.step("Check system health status"):
                health_dict = _assert_health_fatal(system, fatal)

        with allure.step("Assert LED color"):
            expected_color = HealthConsts.LED_NOT_OK_STATUS if fatal else HealthConsts.LED_OK_STATUS
            led_color = health_dict[HealthConsts.STATUS_LED]
            assert expected_color in led_color  # todo: sometimes after reboot it's amber_blink instead of amber

        if fatal:
            with allure.step(f"Assert fatal health issue"):
                assert (health_dict[HealthConsts.ISSUES].get(HealthConsts.ASIC_HEALTH_ISSUE, {}).get(HealthConsts.ISSUE) ==
                        HealthConsts.ASIC_HEALTH_ISSUE_FATAL,
                        f"Expected issue '{HealthConsts.ASIC_HEALTH_ISSUE_FATAL}' but issues are "
                        f"{health_dict[HealthConsts.ISSUES]}")
        else:
            with allure.step(f"Assert no health issues"):
                assert not health_dict[HealthConsts.ISSUES], \
                    "Health issues exist:\n" + str(health_dict)

        with allure.step("Assert console prompt"):
            prompt = DutUtilsTool.get_prompt(engine)
            assert prompt.startswith(HealthConsts.FATAL_PROMPT) == fatal, \
                f"Prompt is '{prompt}' but it should {'' if fatal else 'not '} contain '{HealthConsts.FATAL_PROMPT}'."

        # todo: assert fatal-mode file? or does it not appear after soft-reset?

        if state_just_changed:
            with allure.step(f"Assert event was raised for {'entering' if fatal else 'exiting'} fatal mode"):
                ...  # todo: pending on Elias bugfix of fatal-mode system event
                event_list = system.events.show()  # todo: recent 1 (minute)
                logger.info(f"{event_list=}")


def _assert_health_fatal(system: System, expect_fatal: bool) -> dict:
    output = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).get_returned_value()
    status = output[HealthConsts.STATUS]
    expected_status = HealthConsts.FATAL if expect_fatal else HealthConsts.OK
    assert status == expected_status
    return output


def _assert_syncd_restart(expect_restart=True):
    """
    If expect_restart: asserts that syncd & swss of all ASICs go down and back up. Give it 2 minutes. If not all of
    these dockers stopped and re-started then raise AssertionError.
    If not expect_restart: monitor these dockers for 15 seconds to assert they don't go down.
    """
    SLEEP_SECONDS = 5
    RETRIES = 24 if expect_restart else 4
    with allure.step(f"{_assert_syncd_restart.__name__}: Verify syncd and swss are {'' if expect_restart else 'not '}"
                     f"restarted"):
        engine = TestToolkit.engines.dut
        dockers = {f"{name}{asic}" for name in ('syncd-ibv0', 'swss-ibv0')
                   for asic in range(TestToolkit.devices.dut.asic_amount)}
        logger.info(f"Test will monitor the status of these dockers: {dockers}")
        dockers_went_down = set()
        for i in range(RETRIES):
            running_dockers = set(DutUtilsTool.get_running_dockers(engine)) & dockers
            logger.info(f"{i * SLEEP_SECONDS} seconds elapsed, the following relevant dockers are currently running: "
                        f"{running_dockers}")
            dockers_went_down |= (dockers - running_dockers)
            if expect_restart:
                if len(dockers_went_down) == len(running_dockers) == len(dockers):
                    return  # because all dockers have already went down and then went back up
            else:
                if dockers_went_down:
                    raise AssertionError(f"The following dockers went down: {dockers_went_down}")
            time.sleep(SLEEP_SECONDS)

        if expect_restart:
            raise AssertionError(
                f"The following dockers never went down: {dockers - dockers_went_down}\n"
                f"The following dockers did not come back up: {dockers - running_dockers}")
        else:
            return


def _assert_reboot():
    with allure.step(f"{_assert_reboot.__name__}: Verify switch is rebooted"):
        DutUtilsTool.wait_on_system_reboot(TestToolkit.engines.dut, wait_time_before_reboot=20)
        _reset_base_prompt(TestToolkit.engines.dut)
        _wait(0, 15)


def _reset_base_prompt(engine):
    """Tells the engine that FATAL_PROMPT does not necessarily appear in the prompt."""
    engine.engine.base_prompt = engine.engine.base_prompt.replace(HealthConsts.FATAL_PROMPT, '')


def _assert_close_ports():
    with allure.step(f"{_assert_close_ports.__name__}: Verify ports are close"):
        nv_interface = Interface(None)
        interface_output = OutputParsingTool.parse_json_str_to_dictionary(nv_interface.show()).get_returned_value()
        assert len(interface_output) < 5  # when ports are closed we should only have ['eth0', 'ib0', 'lo']


def _assert_system_fatal_file(count: int):
    """Verifies /etc/system_fatal exists with content `count`. If count==-1, verify file doesn't exist."""
    with allure.step(f"{_assert_system_fatal_file.__name__}: Verifying file {HealthConsts.FATAL_FILE}"):
        engine = TestToolkit.engines.dut
        cmd_output = engine.run_cmd(f"cat {HealthConsts.FATAL_FILE}")
        actual_count = -1 if ('No such file or directory' in cmd_output) else int(cmd_output or 0)  # todo: or 0 ?
        assert actual_count == count, (
            f"File {HealthConsts.FATAL_FILE} expected: {count if count >= 0 else 'does not exist'}, "
            f"actual: {actual_count if actual_count >= 0 else 'does not exist'}"
        )


def _check_tech_support(engines, test_name, num_reboots_done):
    # this part of the test is currently removed because generating the tech-support takes too long and we have to
    # change the fatal-mode clear-time accordingly
    with allure.step(f"Generate tech-support and validate it contains {HealthConsts.FATAL_FILE}"):
        start_time = datetime.now()
        tech_support_tar, _ = System().techsupport.action_generate(engines.dut, option="1 minute ago",
                                                                   since_time="1 minute ago",
                                                                   test_name=test_name)  # todo: params for save duration?
        with allure.step("Verify dump contains " + HealthConsts.FATAL_FILE):
            fatal_file_path = path.basename(tech_support_tar).replace(".tar.gz", HealthConsts.FATAL_FILE)
            cmd = f"tar -Ox {fatal_file_path} -f {tech_support_tar}"
            logger.info(f"{start_time=}\n{tech_support_tar=}\n{fatal_file_path=}\n{cmd=}")
            fatal_file_contents = engines.dut.run_cmd(cmd)
            logger.info(f"{fatal_file_contents=}")
            assert "Not found in archive" not in fatal_file_contents
        with allure.step("Verify contents of " + HealthConsts.FATAL_FILE):
            assert fatal_file_contents.isnumeric() and int(fatal_file_contents) == num_reboots_done

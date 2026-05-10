import logging
import random

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.tests_nvos.platform.els_fiber_tuning.cpo_constants import CpoConsts
from ngts.tests_nvos.system.clock.ClockConsts import ClockConsts
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.platform.els_fiber_tuning.helpers import (
    show_cpo, verify_cpo_field, verify_cpo_fields, get_ports_in_up_state,
    verify_timestamp_recent, verify_timer_service, wait_for_fine_tuning_complete,
    get_device_local_time,
)

logger = logging.getLogger()


@pytest.mark.platform
@pytest.mark.cpo
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_fae_cpo_els_fine_tuning(engines, devices, nv_command, test_api, get_els_list):
    """
    Test Objective:
    Verify the ELS fine-tuning show command returns valid status and recent
    timestamps for all transceivers.

    Test Steps:
    1. Wait for any in-progress fine-tuning to complete (poll up to 120s)
    2. Verify transceiver count matches expected
    3. For each ELS entry, check last-fine-tune-status is 'success'
    4. For each ELS entry, check last-fine-tune-ts is <= 3 minutes ago
    """
    TestToolkit.tested_api = test_api

    with allure.step("Wait for any in-progress fine-tuning to complete"):
        fine_tune_output = wait_for_fine_tuning_complete(nv_command.fae.system)

    with allure.step("Verify transceiver count"):
        ValidationTool.assert_expected_value(
            len(fine_tune_output), devices.dut.number_of_transceivers)

    with allure.step("Verify status and timestamp for each ELS"):
        device_time = get_device_local_time(nv_command)
        logger.info(f"Device local time: {device_time}")
        for els_name, els_data in fine_tune_output.items():
            with allure.independent_step(f"Verify {els_name}"):
                status = els_data.get(CpoConsts.LAST_FINE_TUNE_STATUS, '')
                timestamp = els_data.get(CpoConsts.LAST_FINE_TUNE_TS, '')
                logger.info(f"{els_name}: status={status}, ts={timestamp}")

                assert status == CpoConsts.FineTuneStatus.SUCCESS.value, \
                    f"{els_name}: expected 'success', got '{status}'"
                assert timestamp, f"{els_name}: timestamp is empty"
                verify_timestamp_recent(timestamp, device_time)


@pytest.mark.platform
@pytest.mark.cpo
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_fae_cpo_fine_tuning_state(engines, devices, nv_command, test_api, get_els_list):
    """
    Test Objective:
    Verify that disabling fine-tuning stops the timer service and re-enabling
    restores it.

    Test Steps:
    1. Disable fine-tuning, verify show + systemctl inactive
    2. Re-enable fine-tuning, verify show + systemctl active
    """
    TestToolkit.tested_api = test_api
    fae_system = nv_command.fae.system

    try:
        with allure.step("Disable fine-tuning"):
            fae_system.cpo.set(CpoConsts.FINE_TUNING_STATE,
                               CpoConsts.State.DISABLED.value, apply=True)

        verify_cpo_field(fae_system, CpoConsts.FINE_TUNING_STATE,
                         CpoConsts.State.DISABLED.value)
        verify_timer_service(engines.dut, expected_active=False)

        with allure.step("Re-enable fine-tuning"):
            fae_system.cpo.set(CpoConsts.FINE_TUNING_STATE,
                               CpoConsts.State.ENABLED.value, apply=True)

        verify_cpo_field(fae_system, CpoConsts.FINE_TUNING_STATE,
                         CpoConsts.State.ENABLED.value)
        verify_timer_service(engines.dut, expected_active=True)

    finally:
        fae_system.cpo.unset(CpoConsts.FINE_TUNING_STATE, apply=True)


@pytest.mark.platform
@pytest.mark.cpo
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_fae_cpo_fine_tuning_interval(engines, devices, nv_command, test_api, get_els_list):
    """
    Test Objective:
    Verify that the fine-tuning interval can be set to upper boundary, a random
    mid-range value, and restored to default via unset.

    Test Steps:
    1. Set to upper boundary (86400), verify
    2. Set to random mid-range, verify
    3. Unset, verify default (180)
    """
    TestToolkit.tested_api = test_api
    fae_system = nv_command.fae.system
    mid_value = random.randint(CpoConsts.DEFAULT_FINE_TUNING_INTERVAL + 1,
                               CpoConsts.MAX_FINE_TUNING_INTERVAL - 1)

    try:
        for value in [CpoConsts.MAX_FINE_TUNING_INTERVAL, mid_value]:
            with allure.step(f"Set interval to {value}"):
                fae_system.cpo.set(CpoConsts.FINE_TUNING_INTERVAL,
                                   value, apply=True)
            verify_cpo_field(fae_system, CpoConsts.FINE_TUNING_INTERVAL, value)
    finally:
        with allure.step("Unset interval to restore default"):
            fae_system.cpo.unset(CpoConsts.FINE_TUNING_INTERVAL, apply=True)
        verify_cpo_field(fae_system, CpoConsts.FINE_TUNING_INTERVAL,
                         CpoConsts.DEFAULT_FINE_TUNING_INTERVAL)


@pytest.mark.platform
@pytest.mark.cpo
def test_fae_cpo_fine_tuning_traffic(engines, devices, nv_command, get_els_list):
    """
    Test Objective:
    Verify that ELS fine-tuning does not disrupt traffic or generate errors.

    Test Steps:
    1. Capture baseline ports in up state
    2. Clear counters, capture PHY baseline
    3. Start traffic between hosts for 10 minutes
    4. Stop traffic and verify results
    5. Verify no link errors or PHY counter changes
    6. Verify all baseline ports still up
    """
    traffic_duration = CpoConsts.TRAFFIC_DURATION_10MIN_SECONDS
    traffic_timeout = CpoConsts.TRAFFIC_TIMEOUT_10MIN_SECONDS
    server_output = CpoConsts.TRAFFIC_SERVER_OUTPUT_10MIN
    client_output = CpoConsts.TRAFFIC_CLIENT_OUTPUT_10MIN

    with allure.step("Capture baseline ports in up state"):
        baseline_up_ports = get_ports_in_up_state()
        logger.info(f"Baseline: {len(baseline_up_ports)} ports up")

    with allure.step("Clear counters and capture PHY baseline"):
        Tools.TrafficValidatorTool.clear_traffic_port_counters(engines.dut).verify_result()
        baselines = Tools.TrafficValidatorTool.capture_baseline(engines.dut)

    with allure.step(f"Start traffic for {int(traffic_duration) // 60} minutes"):
        traffic_start_time = Tools.TrafficGeneratorTool.start_traffic_between_2_hosts(
            engines.ha, engines.hb, traffic_duration, server_output, client_output)

    with allure.step("Stop traffic and verify results"):
        num_of_iterations = Tools.TrafficGeneratorTool.stop_traffic_between_2_hosts(
            engines.ha, engines.hb, traffic_start_time, traffic_timeout,
            server_output, client_output)
        logger.info(f"Traffic completed: {num_of_iterations} iterations")

    with allure.step("Verify no errors"):
        with allure.independent_step("Verify no link errors"):
            Tools.TrafficValidatorTool.verify_no_link_errors(
                engines.dut, devices.dut).verify_result()

        with allure.independent_step("Verify no PHY detail counter changes"):
            Tools.TrafficValidatorTool.compare_with_baseline(
                baselines, engines.dut).verify_result()

    with allure.step("Verify all baseline ports still up"):
        ValidationTool.validate_subset_in_superset(
            baseline_up_ports, get_ports_in_up_state()).verify_result()


@pytest.mark.platform
@pytest.mark.cpo
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_fae_cpo_fine_tuning_bad_flow(engines, devices, nv_command, test_api, get_els_list):
    """
    Test Objective:
    Verify that invalid inputs for fine-tuning-state and fine-tuning-interval
    are rejected without affecting system state.

    Test Steps:
    1. Set fine-tuning-state to invalid values -- expect failure
    2. Set fine-tuning-interval out of range / wrong type -- expect failure
    3. Verify config unchanged
    """
    TestToolkit.tested_api = test_api
    fae_system = nv_command.fae.system

    with allure.step("Test invalid fine-tuning-state values"):
        for val in CpoConsts.INVALID_FINE_TUNE_STATES:
            with allure.independent_step(f"Set state to '{val}' -- expect failure"):
                fae_system.cpo.set(CpoConsts.FINE_TUNING_STATE, val).verify_result(
                    False, expected_value='is not one of')

    with allure.step("Test invalid fine-tuning-interval values"):
        for val, expected_err in CpoConsts.INVALID_FINE_TUNE_INTERVAL_CASES[test_api]:
            with allure.independent_step(f"Set interval to '{val}' -- expect failure"):
                fae_system.cpo.set(CpoConsts.FINE_TUNING_INTERVAL, val).verify_result(
                    False, expected_value=expected_err)

    with allure.step("Verify config unchanged"):
        verify_cpo_fields(fae_system, {
            CpoConsts.FINE_TUNING_STATE: CpoConsts.State.ENABLED.value,
            CpoConsts.FINE_TUNING_INTERVAL: CpoConsts.DEFAULT_FINE_TUNING_INTERVAL,
        })


@pytest.mark.platform
@pytest.mark.cpo
def test_fae_cpo_fine_tuning_timezone(engines, devices, nv_command, get_els_list):
    """
    Test Objective:
    Verify that ELS fine-tuning timestamps reflect timezone changes.

    Test Steps:
    1. Wait for fine-tuning to complete, capture baseline timestamps
    2. Save original timezone, set a random different one
    3. Re-query timestamps and verify they changed
    4. Restore original timezone
    5. Re-query timestamps and verify they match the baseline
    """
    system_obj = nv_command.system

    with allure.step("Wait for fine-tuning to complete and capture baseline"):
        baseline_output = wait_for_fine_tuning_complete(nv_command.fae.system)
        baseline_els = next(iter(baseline_output))
        baseline_ts = baseline_output[baseline_els].get(CpoConsts.LAST_FINE_TUNE_TS, '')
        assert baseline_ts, f"Baseline timestamp is empty for {baseline_els}"
        logger.info(f"Baseline ELS: {baseline_els}, timestamp: {baseline_ts}")

    with allure.step("Get current timezone"):
        orig_tz = ClockTools.normalize_timezone(
            ClockTools.get_timezone_from_timedatectl_output(
                engines.dut.run_cmd(ClockConsts.TIMEDATECTL_CMD)))
        logger.info(f"Original timezone: {orig_tz}")

    with allure.step("Pick a random timezone different from current"):
        new_tz = random.choice(
            [tz for tz in CpoConsts.TIMEZONE_CANDIDATES if tz != orig_tz])
        logger.info(f"New timezone: {new_tz}")

    try:
        with allure.step(f"Set timezone to '{new_tz}'"):
            ClockTools.set_timezone(new_tz, system_obj, apply=True).verify_result()

        with allure.step("Verify fine-tuning timestamp changed"):
            changed_output = show_cpo(nv_command.fae.system, CpoConsts.ELS_FINE_TUNING)
            changed_ts = changed_output[baseline_els].get(CpoConsts.LAST_FINE_TUNE_TS, '')
            logger.info(f"Timestamp after timezone change: {changed_ts}")
            assert changed_ts != baseline_ts, \
                (f"Timestamp for {baseline_els} did not change after timezone update. "
                 f"Before: {baseline_ts}, After: {changed_ts}")

    finally:
        with allure.step(f"Restore original timezone '{orig_tz}'"):
            ClockTools.set_timezone(orig_tz, system_obj, apply=True).verify_result()

    with allure.step("Verify timestamp reverted to baseline"):
        restored_output = show_cpo(nv_command.fae.system, CpoConsts.ELS_FINE_TUNING)
        restored_ts = restored_output[baseline_els].get(CpoConsts.LAST_FINE_TUNE_TS, '')
        logger.info(f"Timestamp after restore: {restored_ts}")
        assert restored_ts == baseline_ts, \
            (f"Timestamp for {baseline_els} did not revert after restoring timezone. "
             f"Baseline: {baseline_ts}, Restored: {restored_ts}")

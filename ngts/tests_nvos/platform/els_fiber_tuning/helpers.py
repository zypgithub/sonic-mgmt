import logging
import time

from ngts.tests_nvos.platform.els_fiber_tuning.cpo_constants import CpoConsts
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port, PortRequirements
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


def show_cpo(fae_system, param=""):
    """Show CPO config/status and return parsed dict."""
    return Tools.OutputParsingTool.parse_json_str_to_dictionary(
        fae_system.cpo.show(param)).get_returned_value()


def wait_for_fine_tuning_complete(fae_system, timeout=120, poll_interval=10):
    """Poll ELS fine-tuning until no entry has 'in-progress' status.

    Returns the final fine-tuning output dict once all entries have settled,
    or the last polled output if timeout is reached.
    """
    in_progress = CpoConsts.FineTuneStatus.IN_PROGRESS.value
    status_field = CpoConsts.LAST_FINE_TUNE_STATUS
    deadline = time.time() + timeout

    output = show_cpo(fae_system, CpoConsts.ELS_FINE_TUNING)
    pending = [name for name, data in output.items()
               if data.get(status_field) == in_progress]

    while pending and time.time() < deadline:
        logger.info(f"Fine-tuning in-progress for {len(pending)} ELS: "
                    f"{sorted(pending)}. Retrying in {poll_interval}s ...")
        time.sleep(poll_interval)
        output = show_cpo(fae_system, CpoConsts.ELS_FINE_TUNING)
        pending = [name for name, data in output.items()
                   if data.get(status_field) == in_progress]

    if pending:
        logger.warning(f"Fine-tuning still in-progress after {timeout}s for: "
                       f"{sorted(pending)}")
    else:
        logger.info("All ELS fine-tuning completed")

    return output


def verify_cpo_field(fae_system, field, expected, output=None):
    """Show CPO and assert a single field value.

    Args:
        fae_system: FAE system object
        field: Field name to check
        expected: Expected value
        output: Optional pre-fetched show output to avoid redundant show calls
    """
    if output is None:
        output = show_cpo(fae_system)
    ValidationTool.verify_field_value_in_output(output, field, expected).verify_result()


def verify_cpo_fields(fae_system, fields_and_values):
    """Show CPO once and assert multiple field values.

    Args:
        fae_system: FAE system object
        fields_and_values: Dict of {field_name: expected_value}
    """
    output = show_cpo(fae_system)
    for field, expected in fields_and_values.items():
        ValidationTool.verify_field_value_in_output(output, field, expected).verify_result()


def get_ports_in_up_state():
    """Get list of port names currently in up state."""
    port_requirements = PortRequirements()
    port_requirements.set_port_state(NvosConsts.LINK_STATE_UP)
    return [port.name for port in Port.get_list_of_ports(
        port_requirements_object=port_requirements)]


def validate_ports_state(expected_ports):
    """Assert that all expected ports are currently in up state."""
    actual_ports = get_ports_in_up_state()
    ValidationTool.validate_subset_in_superset(expected_ports, actual_ports).verify_result()


def get_completed_els(fae_system):
    """Get list of ELS transceivers where all init steps match expected defaults."""
    els_init_output = show_cpo(fae_system, CpoConsts.ELS_INITIALIZATION)

    els_in_good_state = []
    for els_name, els_data in els_init_output.items():
        if all(els_data.get(step) == expected
               for step, expected in CpoConsts.ELS_INIT_DEFAULT_DICT.items()):
            els_in_good_state.append(els_name)

    return els_in_good_state


def validate_els_against_baseline(fae_system, baseline_els):
    """Validate that baseline ELS are still in completed state."""
    with allure.step(f"Validating {len(baseline_els)} baseline ELS transceivers"):
        current_completed_els = get_completed_els(fae_system)

        els_not_completed = [els for els in baseline_els if els not in current_completed_els]

        logger.info(f"Current ELS in good state ({len(current_completed_els)}): {sorted(current_completed_els)}")
        logger.info(f"Baseline ELS expected ({len(baseline_els)}): {sorted(baseline_els)}")

        if els_not_completed:
            logger.error(f"ELS from baseline not completed ({len(els_not_completed)}): {sorted(els_not_completed)}")

        ValidationTool.validate_subset_in_superset(baseline_els, current_completed_els).verify_result()


def verify_timer_service(engine, expected_active):
    """Assert the fine-tune timer service is active or inactive."""
    with allure.step(f"Verify timer service is {'active' if expected_active else 'inactive'}"):
        status = engine.run_cmd(
            f'sudo systemctl is-active {CpoConsts.FINE_TUNE_TIMER_SERVICE}')
        if expected_active:
            assert 'inactive' not in status and 'active' in status, \
                f"Expected active, got: {status}"
        else:
            assert 'inactive' in status, f"Expected inactive, got: {status}"


def get_device_local_time(nv_command):
    """Get the device's current local time from 'nv show system date-time'."""
    return ClockTools.get_local_time_from_show_system_date_time_output(
        nv_command.system.datetime.show())


def _parse_as_naive_datetime(timestamp_str):
    """Parse timestamp string to a naive datetime, dropping any timezone info.

    Since we only compare times from the same device, we can safely
    strip timezone info and compare as naive local times.
    """
    try:
        dt = ClockTools.parse_datetime(timestamp_str)
    except (ValueError, Exception):
        # Ambiguous TZ abbreviation (e.g. 'IST') - strip it and retry
        parts = timestamp_str.rsplit(maxsplit=1)
        if len(parts) == 2 and parts[1].isalpha():
            dt = ClockTools.parse_datetime(parts[0])
        else:
            raise
    dt = dt.replace(tzinfo=None)
    return dt


def verify_timestamp_recent(timestamp_str, device_local_time, max_age_sec=180):
    """Assert a fine-tune timestamp is no older than max_age_sec.

    Compares using the device's own local time (from get_device_local_time) so
    the comparison is not affected by clock skew between test runner and DUT.
    """
    fine_tune_dt = _parse_as_naive_datetime(timestamp_str)
    device_dt = _parse_as_naive_datetime(device_local_time)
    age = abs((device_dt - fine_tune_dt).total_seconds())
    assert age <= max_age_sec, \
        f"Timestamp '{timestamp_str}' is {age:.0f}s old (device local: {device_local_time}), exceeds max {max_age_sec}s"

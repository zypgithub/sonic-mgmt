import logging
import pytest
import random

from retry import retry

from ngts.nvos_tools.infra.Simulator import HWSimulator
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.infra.Tools import Tools
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.platform.helpers import (
    filter_eligible_sensors,
    validate_health,
    validate_health_issues,
    validate_sensor_state,
)
from ngts.nvos_constants.constants_nvos import HealthConsts, PlatformConsts

logger = logging.getLogger()

TEMPERATURE_BASE_PATH = PlatformConsts.TEMPERATURE_FILES_PATH
THERMAL_PWM_PATH = '/var/run/hw-management/thermal/pwm1'
HEALTH_STABILIZE_DELAY = 15
TEMPERATURE_MARGIN_FACTOR = 1.05
DEGREES_TO_MILLIDEGREES = 1000
FAN_RAMP_UP_MIN_PCT = 20


# --- Temperature simulation helpers ---


def _pick_sensor(engine, devices):
    """Pick a random ok-state temperature sensor with a max threshold.

    The CLI/health daemon reads temperature from
    /var/run/hw-management/thermal/<sensor>_input, not the /ui/temperature/...
    layer. We discover the sensor via /ui/temperature/ (which gives us
    name<->dir mapping), then resolve the symlink one level to get the
    actual thermal/ path to inject into.
    """
    platform = Platform()
    temp_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
        platform.environment.temperature.show()).verify_result()
    available_psu_list = platform.environment.get_available_psus() if devices.dut.psu_list else []
    eligible_sensors = filter_eligible_sensors(
        devices.dut.temperature_sensors, temp_output, available_psu_list,
        required_keys=('max', 'current'))
    assert eligible_sensors, "No temperature sensors with max/current found for simulation"

    last_err = None
    random.shuffle(eligible_sensors)
    for sensor in eligible_sensors:
        try:
            sensor_dir = HWSimulator.find_sensor_dir(engine, TEMPERATURE_BASE_PATH, sensor)
        except FileNotFoundError as e:
            last_err = e
            continue
        ui_input_path = f"{sensor_dir}/input"
        thermal_input_path = engine.run_cmd(f"readlink {ui_input_path}").strip()
        assert thermal_input_path, f"Could not resolve symlink for {ui_input_path}"
        sensor_data = temp_output[sensor]
        logger.info(f"Selected sensor: {sensor}, inject at: {thermal_input_path}, "
                    f"current: {sensor_data['current']}, max: {sensor_data['max']}, "
                    f"crit: {sensor_data.get('crit', '-')}")
        return sensor, sensor_data, thermal_input_path

    raise AssertionError(
        f"None of the eligible temperature sensors map to a sysfs dir under {TEMPERATURE_BASE_PATH}. "
        f"Last error: {last_err}"
    )


def _read_pwm(engine):
    """Read main thermal-control PWM (0-255). Returns None if the platform
    doesn't expose it (the fan-ramp-up check then degrades to a no-op).
    """
    try:
        return int(engine.run_cmd(f"cat {THERMAL_PWM_PATH}").strip())
    except (ValueError, Exception) as e:
        logger.warning(f"Could not read PWM at {THERMAL_PWM_PATH}: {e}")
        return None


@retry(AssertionError, tries=12, delay=10)
def _validate_fans_ramped_up(engine, baseline_pwm):
    """Assert PWM rose at least FAN_RAMP_UP_MIN_PCT above baseline.

    Thermal control reacts slowly on some platforms (observed ~60-120s lag on
    Crocodile), so this retries for up to ~2 minutes.
    """
    if baseline_pwm is None:
        return
    current = _read_pwm(engine)
    assert current is not None, "Could not read current PWM"
    threshold = baseline_pwm + max(10, int(baseline_pwm * FAN_RAMP_UP_MIN_PCT / 100))
    assert current >= threshold, (
        f"Expected fans to ramp up: baseline_pwm={baseline_pwm}, current={current}, "
        f"threshold={threshold}"
    )
    logger.info(f"Fan PWM increased: baseline={baseline_pwm} -> current={current}")


# --- Temperature simulation test ---


@pytest.mark.platform
@pytest.mark.disable_loganalyzer
@pytest.mark.timeout(10 * MINUTE, func_only=True)
def test_simulate_temperature_fault_high(engines, devices):
    """
    @summary: Inject a high temperature value into a sensor and verify the
              system detects the fault, raises a health issue, and (when the
              platform has fans) ramps up fan PWM. Restores the sensor and
              verifies recovery.

    Steps:
    1. Validate system health is OK
    2. Pick a random temperature sensor with a max threshold
    3. Inject value = max * 1.05 (just above max threshold)
    4. Validate sensor state is 'failed', health is 'Not OK', sensor is in
       health issues
    5. If devices.dut.fan_list is non-empty, validate fan PWM increased
    6. Restore original symlink
    7. Validate sensor state is 'ok', health is 'OK', sensor not in health
       issues
    """
    system = System()
    temperature_show = Platform().environment.temperature.show

    with allure.step("Pick sensor and validate initial health"):
        sensor_name, sensor_data, sensor_input_path = _pick_sensor(engines.dut, devices)
        validate_health(system, HealthConsts.OK)

    fault_value = int(float(sensor_data['max']) * DEGREES_TO_MILLIDEGREES * TEMPERATURE_MARGIN_FACTOR)
    has_fans = bool(devices.dut.fan_list)

    with allure.step(f"Inject high temperature fault: value={fault_value}"):
        baseline_pwm = _read_pwm(engines.dut) if has_fans else None
        logger.info(f"Baseline PWM before injection: {baseline_pwm} (has_fans={has_fans})")

        with HWSimulator.simulate_sensor(engines.dut, sensor_input_path, fault_value, HEALTH_STABILIZE_DELAY):
            validate_sensor_state(temperature_show, sensor_name, 'failed')
            validate_health(system, HealthConsts.NOT_OK)
            validate_health_issues(system, sensor_name, expected_present=True)
            if has_fans:
                _validate_fans_ramped_up(engines.dut, baseline_pwm)
            else:
                logger.info("Skipping fan ramp-up check: platform has no fans")

        validate_sensor_state(temperature_show, sensor_name, 'ok')
        validate_health(system, HealthConsts.OK)
        validate_health_issues(system, sensor_name, expected_present=False)

import logging
import re
import pytest
import random

from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_constants.constants_nvos import DatabaseConst, PlatformConsts

logger = logging.getLogger()


@pytest.mark.cumulus
@pytest.mark.platform
@pytest.mark.simx
@pytest.mark.skynet
@pytest.mark.nvos_chipsim_ci
def test_show_platform_environment_voltage(engines, devices):
    """
    Show platform environment test
    """
    with allure.step("Create System object"):
        platform = Platform()

    with (allure.step("Execute show platform environment and make sure all the components exist")):
        voltage_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
            platform.environment.voltage.show()).verify_result()
        sensors = devices.dut.get_voltage_sensors(engines.dut)
        assert len(sensors) == len(voltage_output.keys()), ("test failed - expected sensors count = "
                                                            "{expected}, show command output = {output} \n "
                                                            "expected sensors list: {expected_list}").format(
            expected=len(sensors), output=len(voltage_output.keys()), expected_list=sensors)

    with allure.step("Check all details of all sensors are available in show platform environment voltage"):
        sensors_absent = []
        actual_volt_absent = []
        available_psu_list = platform.environment.get_available_psus() if devices.dut.psu_list else []
        for sensor in devices.dut.voltage_sensors:
            if voltage_output[sensor]['state'] != 'ok':
                if is_sensor_for_absent_psu(sensor, available_psu_list):
                    # Ignore absence of sensor for absent PSU
                    continue
                sensors_absent.append(sensor)
                continue
            if 'actual' not in voltage_output[sensor].keys():
                actual_volt_absent.append(sensor)

        assert len(sensors_absent) == 0 and len(actual_volt_absent) == 0, \
            'Absent sensors={}, Actual voltage missing={}'.format(sensors_absent, actual_volt_absent)

    with allure.step("Execute show platform environment voltage for every sensor and compare with aggregated show"):
        mismatch = False
        err = []
        for sensor in devices.dut.voltage_sensors:
            if is_sensor_for_absent_psu(sensor, available_psu_list):
                # Ignore absence of sensor for for absent PSU
                continue
            sensor_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
                platform.environment.voltage.show(sensor)).verify_result()
            voltage_output_for_sensor = voltage_output[sensor].copy()
            # the actual voltage might fluctuate between the two `nv show` commands, so we keep 5% tolerance
            if 'actual' in sensor_output.keys():
                actual_voltage_low = float(voltage_output_for_sensor['actual']) * 0.95
                actual_voltage_high = float(voltage_output_for_sensor['actual']) * 1.05
                if not (actual_voltage_low <= float(sensor_output['actual']) <= actual_voltage_high):
                    mismatch = True
                    err.append("Actual voltage of sensor {} varied more than 5%, from {} to {}".
                               format(sensor, voltage_output_for_sensor['actual'], sensor_output['actual']))
                del sensor_output['actual']
                del voltage_output_for_sensor['actual']
            else:
                mismatch = True
                err.append('Actual voltage for sensor {} not present in sensor specific output'.format(sensor))
            if sensor_output != voltage_output_for_sensor:
                mismatch = True
                err.append('Min/max not matching for {}:{}'.format(sensor, voltage_output_for_sensor - sensor_output))

        assert not mismatch, "Mismatch between aggregated output and single sensor output:{}".format(err)

    with allure.step("Check voltage range for voltage sensors"):
        voltage_issue = False
        err_msg = []
        for sensor in devices.dut.voltage_sensors:
            err = check_voltage_in_range(sensor, voltage_output[sensor])
            if err != "":
                voltage_issue = True
                err_msg.append(err)
        assert not voltage_issue, 'Voltage of sensors out of range:{}'.format(err_msg)


@pytest.mark.cumulus
@pytest.mark.platform
@pytest.mark.skynet
@pytest.mark.simx
def test_show_voltage_bad_flow(engines, devices):
    """
    For Each Sensor we have DB (should be part of init flow)
    """
    with allure.step("Create System object"):
        platform = Platform()
        expected_msg = 'The requested item does not exist'
    with allure.step("Try nv show platform environment voltage <not_exist_sensor>"):
        output = platform.environment.voltage.show('not_sensor', should_succeed=False)
        assert expected_msg in output, "check the show command for not exist sensor, the expected message is {}, " \
                                       "the current output is {}".format(expected_msg, output)


@pytest.mark.platform
@pytest.mark.simx
@pytest.mark.skynet
def test_database_platform_environment_voltage(engines, devices):
    """
    For Each Sensor we have DB (should be part of init flow)
    """
    with allure.step("Create System object"):
        platform = Platform()

    with allure.step("get expected sensors"):
        sensors_list = platform.environment.voltage.get_sensors_list(engines.dut)
        logger.info("the expected sensors from switch's file system are: {}".format(sensors_list))

    with allure.step("get expected CLI voltage sensors"):
        cli_sensors_list = platform.environment.voltage.get_cli_sensors_list(engines.dut)

        logger.info("the sensors from switch's CLI are: {}".format(cli_sensors_list))

    with allure.step("get all the tabled with SENSOR in STATE_DB"):
        database_output = Tools.DatabaseTool.sonic_db_cli_get_keys(engine=engines.dut, asic="",
                                                                   db_name=DatabaseConst.STATE_DB_NAME,
                                                                   grep_str="VOLTAGE").splitlines()

    with allure.step("Check the Sensors output from CLI and db tables"):
        # since sensor names are formatted differently in DB vs. CLI, we normalize them to the same form by removing all
        # spaces and other non-alphanumeric characters
        def normalization(s): return re.sub(r'[^a-z0-9]', '', s.lower())

        with allure.independent_step("Verify for every sensor in sensors_dict[VOLTAGE], it exist in nv show platform environment voltage"):
            ValidationTool.validate_equal_with_normalization(cli_sensors_list, devices.dut.sensors_dict["VOLTAGE"],
                                                             normalization).verify_result()

        with allure.independent_step("Verify for every sensor: VOLTAGE_INFO|<sensor_name> table exist in STATE_DB"):
            ValidationTool.validate_equal_with_normalization(
                database_output, sensors_list, normalization,
                lambda s: normalization("VOLTAGE_INFO|" + s.replace('+Volt', '').replace('+Vol', ''))
            ).verify_result()


def is_sensor_for_absent_psu(sensor, available_psu_list):
    psu_name = re.search(r"PSU-(\d+)-.*", sensor)
    if psu_name is not None:
        # Sensor is a PSU sensor
        psu_name = "PSU" + psu_name.group(1)
        if psu_name not in available_psu_list:
            # Sensor belongs to an absent PSU
            return True
    return False


def get_random_sensor_max_min(sensors_dic):
    """
        get random sensor out of all the sensors with: ok state and have max, min values
    :param sensors_dic:
    :return:
    """
    sensors_list = []
    for item in sensors_dic.keys():
        if 'min' in sensors_dic[item].keys() and 'max' in sensors_dic[item].keys():
            sensors_list.append(item)
    assert sensors_list, "No sensors with Max and Min values"
    return random.choice(sensors_list)


def check_voltage_in_range(sensor, sensor_output):
    """
    :param sensor
    :param sensor_output:
    :return:
    """
    with allure.step("Verify the actual voltage is between min and max inclusive for {}".format(sensor)):
        if 'max' in sensor_output.keys():
            if float(sensor_output['actual']) > float(sensor_output['max']):
                return "Actual voltage {} more than max of {}".format(sensor_output['actual'], sensor_output['max'])
        if 'min' in sensor_output.keys():
            if float(sensor_output['actual']) < float(sensor_output['min']):
                return "Actual voltage {} less than min of {}".format(sensor_output['actual'], sensor_output['min'])
        return ""

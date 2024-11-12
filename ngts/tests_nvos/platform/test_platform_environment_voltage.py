import logging
import re
import pytest
import random
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

    with allure.step("Execute show platform environment voltage for every sensor"):
        for sensor in devices.dut.voltage_sensors:
            sensor_output = Tools.OutputParsingTool.parse_json_str_to_dictionary(
                platform.environment.voltage.show(sensor)).verify_result()
            with allure.step("Verify both dictionaries are equal"):
                voltage_output_for_sensor = voltage_output[sensor].copy()
                # the actual voltage might fluctuate between the two `nv show` commands, so we don't compare it
                del sensor_output['actual']
                del voltage_output_for_sensor['actual']
                assert sensor_output == voltage_output_for_sensor, ""

    with allure.step("Check voltage range for random sensor"):
        random_sensor = get_random_sensor_max_min(voltage_output)
        check_voltage_in_range(voltage_output[random_sensor])


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
        raw_database_output = Tools.DatabaseTool.sonic_db_cli_get_keys(engine=engines.dut, asic="",
                                                                       db_name=DatabaseConst.STATE_DB_NAME,
                                                                       grep_str="VOLTAGE").splitlines()
        database_output = [re.sub(r"PMIC-\d+ ", "", sensor_str) for sensor_str in raw_database_output]

    with allure.step("Check the Sensors output from CLI and db tables"):
        with allure.independent_step("Verify for every sensor in sensors_dict[VOLTAGE], it exist in nv show platform environment voltage"):
            err_mes = compare_sensors(devices.dut.sensors_dict["VOLTAGE"], cli_sensors_list)
            assert not err_mes, f"This sensors are missing: {err_mes}"

        with allure.independent_step("Verify for every sensor: VOLTAGE_INFO|<sensor_name> table exist in STATE_DB"):
            err_mes = compare_sensors(sensors_list, database_output)
            assert not err_mes, f"This sensors are missing: {err_mes}"


def compare_sensors(expected_sensors_list, actual_sensors_list):
    expected = set([re.sub(r'[^a-z0-9]', '', s.lower()) for s in expected_sensors_list])
    actual = set([re.sub(r'[^a-z0-9]', '', s.lower()) for s in actual_sensors_list])
    missing = expected - actual
    excess = actual - expected
    result = excess.union(missing)
    psu_found = [key for key in result if 'psu' in key]
    assert len(psu_found) < 4, f"Found more than 4 missing psu {psu_found}"
    result.difference_update(psu_found)
    return result


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


def check_voltage_in_range(sensor_output):
    """

    :param sensor_output:
    :return:
    """
    with allure.step("Verify the actual voltage is between min and max inclusive"):
        assert sensor_output['state'] == 'ok', ""
        assert float(sensor_output['actual']) <= float(sensor_output['max']), "the actual voltage out of range, max voltage = {}".format(sensor_output['max'])
        assert float(sensor_output['actual']) >= float(sensor_output['min']), "the actual voltage out of range, min voltage = {}".format(sensor_output['min'])

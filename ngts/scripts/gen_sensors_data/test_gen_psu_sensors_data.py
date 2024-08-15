#!/usr/bin/env python
import os
import re
import allure
import logging
import pytest
import json

from test_gen_sensors_data import parse_sensors_data, gen_sensors_data_yaml_file
from ngts.constants.constants import MarsConstants
logger = logging.getLogger()

GEN_SENSORS_DATA_PATH = os.path.dirname(os.path.abspath(__file__))

PSU_SENSORS_DATA_PATH = f"{MarsConstants.SONIC_MGMT_DIR}/tests/platform_tests/sensors_utils/psu_sensors.json"
PSU_NUM_PLACE_HOLDER = "PSU-*"
PSU_FAN_DIR_PATTERN = r'-(PSF|PSR)-'


@pytest.mark.disable_loganalyzer
def test_gen_psu_sensors_data_yml(topology_obj):
    """
    This script will generate a yml file which includes psu sensors test data for platform_tests/test_sensors.py
    When we need to add psu sensors data for a new psu, we can generate the data by running the test (same to run ngts test)
    on a device which has this psu installed and copy the sensors data into the file of ansible/group_vars/sonic/psu-sensors-data.yml
    :param topology_obj: topology object fixture
    :return: raise assertion error in case of script failure
    """
    try:
        dut_engine = topology_obj.players['dut']['engine']
        cli_object = topology_obj.players['dut']['cli']
        with allure.step("Get platform, psu data and sensors data"):
            platform = cli_object.chassis.get_platform()
            psu_dict = get_psu_dict(dut_engine)
            psu_mapping = get_json_mapping(platform)
            psu_sensor_prefix = get_sensor_prefix(psu_mapping)
            raw_sensors_data = json.loads(
                dut_engine.run_cmd(f'sensors -A -j {psu_sensor_prefix}-*-*'))  # captures PSU sensors
        with allure.step("Parse sensors data"):
            sensors_dict = parse_sensors_data(raw_sensors_data)
            psu_sensor_dict = filter_psu_platform_sensors(sensors_dict, psu_dict, psu_sensor_prefix)
        with allure.step("Gen yml file for sensors data"):
            for psu_model, psu_sensors in psu_sensor_dict.items():
                psu_model_no_fan_dir = re.sub(PSU_FAN_DIR_PATTERN, '-', psu_model)
                yml_file_full_path = os.path.join(GEN_SENSORS_DATA_PATH, f"psu_sensors_{psu_model_no_fan_dir}.yml")
                gen_sensors_data_yaml_file(yml_file_full_path, psu_model_no_fan_dir, psu_sensors)

    except Exception as err:
        raise AssertionError(err)


def get_psu_dict(dut_engine):
    """
    The function returns a dictionary consisting entries {psuNum: psuModel} of PSU installed on the dut
    :param dut_engine: dut_engine fixture
    :return: a dictionary of installed PSUs entries, mapping psu slots (numbers) to the psu models
    """
    psu_data = json.loads(dut_engine.run_cmd('show platform psu --json'))
    psu_dict = {psu["index"]: psu["model"] for psu in psu_data if psu["model"] != "N/A"}
    return psu_dict


def get_json_mapping(platform):
    """
    This function will parse the psu_sensors.json file and fetch the platform data from it.
    :param platform: platform of the current dut
    :return: psu sensors data of platform as appears in psu_sensors.json
    """

    psu_sensors_json_file_full_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                   PSU_SENSORS_DATA_PATH)
    with open(psu_sensors_json_file_full_path) as file:
        psu_json_mapping = json.load(file)
        return psu_json_mapping[platform]


def get_sensor_prefix(psu_sensors_data):
    """
    This function will fetch the sensor bus pattern prefix from psu_sensors_data.
    :param psu_sensors_data: psu sensors data of platform as appears in psu_sensors.json
    :return: sensor psu sensor prefix without buss num and address of dut - for example, dps460-i2c of dps460-i2c-4-58"
    """
    psu_bus_path = list(psu_sensors_data["default"]["chip"].keys())[0]  # grab some key from the chip part
    psu_bus_parts = psu_bus_path.split('-')[:2]  # Split the string by '-', the prefix is the first 2 words
    return '-'.join(psu_bus_parts)


def filter_psu_platform_sensors(sensors_checks, psu_dict, psu_sensor_prefix):
    """
    The function sorts the psu sensors of the device to their appropriate psu model
    :param sensors_checks: output of "sensors" command, containing psu sensors of the device
    :param psu_dict: a dictionary of installed PSUs entries, mapping psu slots (numbers) to the psu models,
    without repetitions of the same PSU
    :param psu_sensor_prefix: psu sensor prefix of the platform - for example dps460-i2c
    :return: a dictionary mapping psu_model to its sensors, in a similar format to the sku-sensors-data.yml file
    """
    psu_sensors_dict = {psu_dict[psu_num]: dict() for psu_num in psu_dict.keys()}
    psu_indexes_per_model = dict()
    for index, model in psu_dict.items():
        psu_indexes_per_model.setdefault(model, []).append(index)
    psu_models = set(psu_dict.values())
    path_count = {model: dict() for model in psu_models}
    # Count the number of time a sensor appears on some psu slot per model
    for check_type, checks in sensors_checks.items():
        for check in checks:
            if not check:
                # If the check is an empty line, it is needed for parsing, so we add it to all models
                for model in psu_models:
                    psu_sensors_dict[model].setdefault(check_type, []).append(check)
                continue
            model, path = process_sensor_path(check, psu_dict, psu_sensor_prefix)
            if model:
                path_count[model].setdefault(check_type, {}).setdefault(path, 0)
                path_count[model][check_type][path] += 1

    # Only add a sensor path of a model if it appeared in all psu slots that use this model
    for model, check_types in path_count.items():
        for check_type, paths in check_types.items():
            for path, count in paths.items():
                if count == len(psu_indexes_per_model[model]):
                    psu_sensors_dict[model].setdefault(check_type, []).append(path)

    return psu_sensors_dict


def process_sensor_path(sensor_path, psu_dict, psu_sensor_prefix):
    """
    The function processes a given sensor path, generalizes it (see example) and returns the PSU number
    it belonged to. Example - dps460-i2c-4-5a/PSU-2(R) Temp 2/temp2_input --> dps460-i2c-*-*/PSU-* Temp 2/temp2_input
    :param sensor_path: line of output from .yml file, containing a sensor path
    :param psu_dict: mapping between psu number to psu model
    :param psu_sensor_prefix: psu sensor prefix of the platform - for example dps460-i2c

    :return: two values, the generalized sensor_path and the psu_model it belonged to before generalizing.
    """
    psu_num_sensor_pattern = r'PSU-(\d+)(?:\([A-Z]\))?'  # matching PSU-i(side) part with side being optional
    psu_bus_sensor_pattern = rf'({psu_sensor_prefix}-)(\d+[a-zA-Z]*-\d+[a-zA-Z]*)'
    # psu_model and generalized_sensor_path will be None if the sensor didn't match psu_num_sensor_path
    psu_model = None
    generalized_sensor_path = None
    match = re.search(psu_num_sensor_pattern, sensor_path)
    if match:
        index = match.group(1)
        psu_model = psu_dict[index]
        # Replace the PSU number with * for each line
        generalized_sensor_path = re.sub(psu_num_sensor_pattern, PSU_NUM_PLACE_HOLDER, sensor_path)

        # Replace the bus path with *-* (from dps460-i2c-4-59 to dps460-i2c-*-*)
        generalized_sensor_path = re.sub(psu_bus_sensor_pattern, f"{psu_sensor_prefix}-*-*", generalized_sensor_path)
    else:
        # If the path doesn't match our format, we want to ignore it
        logger.warning(f"path {sensor_path} didn't match PSU sensor format")

    return psu_model, generalized_sensor_path

import re
import allure
import pandas as pd
import logging
from ngts.cli_wrappers.sonic.sonic_cli import SonicCli
from ngts.constants.performance_constants import PerfConsts, SPCControllers, PowerConsts, ValidationConsts, MongoDbConsts
from ngts.helpers.performance.performance_db_helpers import add_test_mongo_metadata, get_base_df, calculate_avg_on_all_samples
from infra.tools.exceptions.test_issue import TestIssue
from infra.tools.redmine.redmine_api import is_redmine_issue_active

logger = logging.getLogger()


def validate_temperature(traffic_json, temperature_threshold, violations_list):
    with allure.step(f"Validate all temperature samples are below {temperature_threshold}"):
        temperature_samples = traffic_json[ValidationConsts.TEMPERATURE_SAMPLES]
        temperature_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)
        higher_temperature_samples = []
        for sample_id, temperature_samples_dict in temperature_samples.items():
            temperature = temperature_samples_dict[ValidationConsts.TEMPERATURE]
            if int(temperature) > temperature_threshold:
                higher_temperature_samples.append(f"{sample_id} - temperature: {temperature}")
        if higher_temperature_samples:
            violations_list.append(f"Not all temperature samples were lower than threshold {temperature_threshold}, "
                                   f"please check {higher_temperature_samples}")


def validate_power(traffic_json, players, test_name, chip_type, power_threshold, violations_list):
    """
    Validates power consumption samples against defined thresholds and generates power consumption reports.

    This function also attaches the power consumption dataframe to mongo DB

    Args:
        traffic_json (dict): JSON containing power samples data
        players (dict): Dictionary containing test players, including DUT CLI object
        test_name (str): Name of the test being executed
        chip_type (str): Type of chip being tested (e.g., 'SPC3')
        power_threshold (dict): Dictionary containing power thresholds for different collectors
        violations_list (list): List to store any power threshold violations

    Returns:
        tuple: A tuple containing two pandas DataFrames:
            - power_df_with_total: Detailed power consumption data for all collectors with total
            - power_df_by_collectors_group_with_total: Summarized power consumption by collector groups with total
    """
    with allure.step(f"Validate all power samples are below the power_thresholds"):
        dut_cli_obj = players['dut']['cli']
        power_samples = traffic_json[ValidationConsts.POWER_SAMPLES]
        power_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)
        power_df = get_avg_samples_power_dataframe(dut_cli_obj, chip_type, power_samples)
        power_df_with_total = validate_power_df_by_collectors(power_df, power_threshold, violations_list)
        allure.attach(power_df_with_total.to_html(), 'Power full dataframe', allure.attachment_type.HTML)
        power_df_by_collectors_group_with_total = get_sum_power_df_by_collectors_group(power_df)
        allure.attach(power_df_by_collectors_group_with_total.to_html(),
                      'Power summary by collectors', allure.attachment_type.HTML)
        add_test_mongo_metadata(test_name, {
            MongoDbConsts.POWER_TOTAL: power_df_with_total.to_dict(orient='records'),
            MongoDbConsts.POWER_BY_COLLECTORS: power_df_by_collectors_group_with_total.to_dict(orient='records')})
        return power_df_with_total, power_df_by_collectors_group_with_total


def get_avg_samples_power_dataframe(cli_obj, chip_type, power_samples):
    df_list = []
    for sample_id, power_sample in power_samples.items():
        sensors_output = get_sensors_data(cli_obj, power_sample)
        power_df = get_power_dataframe(cli_obj, sensors_output, chip_type)
        df_list.append(power_df)
    df_result = get_base_df(df_list)
    power_df[PowerConsts.POWER_CURRENT] = calculate_avg_on_all_samples(df_list, power_samples, PowerConsts.POWER_CURRENT)
    power_df[PowerConsts.POWER_WATT] = calculate_avg_on_all_samples(df_list, power_samples, PowerConsts.POWER_WATT)
    return power_df


def get_sensors_data(cli_obj, power_sample):
    sensors_output = power_sample[ValidationConsts.SENSORS_OUTPUT]
    if not sensors_output and isinstance(cli_obj, SonicCli):
        sensors_output = cli_obj.performance.get_sensors_data()
    elif not sensors_output:
        raise TestIssue("Sensors data was not collected by validator as expected by DVS/CL OS")
    return sensors_output


def get_power_dataframe(cli_obj, sensors_output, chip_type):
    """
    Args:
        cli_obj: a cli object of the device DUT
        sensors_output: output of command "sensors *-i2c-5-*" on the device
        chip_type: i.e, "SPC3"
    The Function uses the arguments to parse the sensors data into a power dataframe:
        controller_names_list: a list of the controllers names ['mp2975-i2c-5-63','mp2975-i2c-5-6c',...]
        controllers_info_dicts_list: a list of dicts, each dict contains the values of a controller on the device,
                                     i.e, [{'vout1': 1.20, 'vout2': 1.20, 'iout1': 13.00, 'iout2': 94.00},...]
        controllers_by_address_dict: a dict of controller addresses keys and controller names values, i.e,
                                     { "0x61": "HVDD TILES (HVDD_T47)",...}

    Returns:
    A Pandas Dataframe based on the list of dicts,
    [{"Power Supply": "HVDD TILES (HVDD_T47)",
    "Address": "0x61",
    "Voltage (V)": 1.20,
    "Current (A)": 13.00,
    "Power (W)": 15.6},...]
    """
    controller_names_list = re.findall(PowerConsts.CONTROLLER_REGEX, sensors_output)
    controllers_info_dicts_list = cli_obj.performance.get_controllers_info_dicts_list(sensors_output)
    controllers_by_address_dict = SPCControllers.SPCControllers_DICT[chip_type]
    power_dp = []
    for controller_idx, controller_name in enumerate(controller_names_list):
        address = str(hex(int(re.search(r'.*-i2c-5-(.*)', controller_name).group(1), 16)))
        controller_info_dict = controllers_info_dicts_list[controller_idx]
        controller_name = controllers_by_address_dict[address]
        for index in [1, 2]:
            if controller_info_dict.get(f"vout{index}"):
                controller_dict_df_entry = {}
                voltage = controller_info_dict[f"vout{index}"]
                current = controller_info_dict[f"iout{index}"]
                controller_dict_df_entry[PowerConsts.POWER_SUPPLY] = controller_name
                controller_dict_df_entry[PowerConsts.POWER_SUPPLY_ADDRESS] = address
                controller_dict_df_entry[PowerConsts.POWER_VOLTAGE] = voltage
                controller_dict_df_entry[PowerConsts.POWER_CURRENT] = current
                controller_dict_df_entry[PowerConsts.POWER_WATT] = get_controller_power(index, controller_info_dict, voltage, current)
                power_dp.append(controller_dict_df_entry)
    return pd.DataFrame(power_dp)


def get_controller_power(index, controller_info_dict, voltage, current):
    if controller_info_dict.get(f"pout{index}"):
        power = controller_info_dict.get(f"pout{index}")
    else:
        power = current * voltage
    return power


def get_sum_power_df_by_collectors_group(power_df):
    """
    This function is calculating a new summary dataframe, summing the power consumption
    per collector, i.e, VCORE TILES, DVDD TILES, etc.
    Args:
        power_df: a pandas dataframe including the power stats

    Returns:
    a dataframe such as this:

        Power Supply	        Address	              Power (W)
    0	HVDD TILES (HVDD_T03)	0x6c	              224.585
    1	VCORE MAIN (VDD_M)	    0x62	              206.500
    2	VDDSCC	                0x6e	              42.807
    3	VCORE TILES	            0x63,0x64,0x65,0x66	  114.366
    4	DVDD TILES	            0x67,0x68,0x69,0x6a	  123.498
    5	Total Power	            NaN	                  711.756

    """
    rows_to_drop = []
    collectors_regex_counters = {
        r"VCORE & 1.8V_Tile": {"counter": 0, PowerConsts.POWER_SUPPLY: "VCORE & 1.8V_Tile", PowerConsts.POWER_SUPPLY_ADDRESS: []},
        r"VCORE TILES \d & \d \(VDD_Tx\)": {"counter": 0, PowerConsts.POWER_SUPPLY: "VCORE TILES", PowerConsts.POWER_SUPPLY_ADDRESS: []},
        r"DVDD TILES \d & \d \(DVDD_Tx\)": {"counter": 0, PowerConsts.POWER_SUPPLY: "DVDD TILES", PowerConsts.POWER_SUPPLY_ADDRESS: []},
    }
    power_df_by_group = power_df.groupby([PowerConsts.POWER_SUPPLY, PowerConsts.POWER_SUPPLY_ADDRESS])[PowerConsts.POWER_WATT].sum().reset_index()
    for index, row in power_df_by_group.iterrows():
        for collector_regex in collectors_regex_counters.keys():
            if re.search(collector_regex, row[PowerConsts.POWER_SUPPLY]):
                collectors_regex_counters[collector_regex]["counter"] += row[PowerConsts.POWER_WATT]
                collectors_regex_counters[collector_regex][PowerConsts.POWER_SUPPLY_ADDRESS].append(row[PowerConsts.POWER_SUPPLY_ADDRESS])
                rows_to_drop.append(index)
    power_df_by_group = power_df_by_group.drop(rows_to_drop)
    power_df_to_concat = []
    for collector_regex, counter_dict in collectors_regex_counters.items():
        if counter_dict["counter"] > 0:
            new_row = {PowerConsts.POWER_SUPPLY: counter_dict[PowerConsts.POWER_SUPPLY],
                       PowerConsts.POWER_SUPPLY_ADDRESS: ",".join(counter_dict[PowerConsts.POWER_SUPPLY_ADDRESS]),
                       PowerConsts.POWER_WATT: counter_dict["counter"]}
            power_df_to_concat.append(new_row)
    new_rows = pd.DataFrame(power_df_to_concat)
    power_df_by_collectors_group = pd.concat([power_df_by_group, new_rows], ignore_index=True)
    power_df_by_collectors_group_with_total = append_total_power(power_df_by_collectors_group)
    return power_df_by_collectors_group_with_total


def validate_power_df_by_collectors(power_df, collectors_power_threshold, violations_list):
    power_total_th = collectors_power_threshold.get("TOTAL")
    total_power = power_df[PowerConsts.POWER_WATT].sum()
    for index, row in power_df.iterrows():
        collector_name = row[PowerConsts.POWER_SUPPLY]
        collector_power = row[PowerConsts.POWER_WATT]
        for power_supply_regex, collector_th in collectors_power_threshold.items():
            if re.search(power_supply_regex, collector_name):
                if collector_power > collector_th:
                    # TODO: remove this 'if' statement once FW bug #4526752 is fixed. Keep only the 'else' part.
                    if collector_name == "HVDD TILES (HVDD_T03)" and is_redmine_issue_active([4526752])[0]:
                        logger.info(f"Power for {collector_name}: {collector_power} W,  "
                                    f"was higher than threshold {collector_th}, "
                                    f"please check table \"Power full dataframe\" in allure attachments. "
                                    f"Not failing test, due to bug FW #4526752")
                    else:
                        violations_list.append(f"Power for {collector_name}: {collector_power} W,  "
                                               f"was higher than threshold {collector_th}, "
                                               f"please check table \"Power full dataframe\" in allure attachments")

    if total_power > power_total_th:
        violations_list.append(f"Total power {total_power} W was higher than total power threshold {power_total_th}, "
                               f"please check table \"Power full dataframe\" in allure attachments")
    power_df_with_total = append_total_power(power_df)
    return power_df_with_total


def append_total_power(power_df):
    total_power = power_df[PowerConsts.POWER_WATT].sum()
    new_row = pd.DataFrame([{PowerConsts.POWER_SUPPLY: PowerConsts.TOTAL_POWER,
                             PowerConsts.POWER_SUPPLY_ADDRESS: None,
                             PowerConsts.POWER_WATT: total_power}])
    power_df_with_total = pd.concat([power_df, new_row], ignore_index=True)
    return power_df_with_total

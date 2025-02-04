import re
import allure
import pandas as pd
from ngts.constants.performance_constants import PerfConsts, SPCControllers, PowerConsts


def validate_temperature(traffic_json, temperature_threshold, violations_list):
    with allure.step(f"Validate all temperature samples are below {temperature_threshold}"):
        temperature_samples = traffic_json["Temperature_samples"]
        temperature_samples.pop('sample_params', None)
        higher_temperature_samples = []
        for sample_id, temperature_samples_dict in temperature_samples.items():
            temperature = temperature_samples_dict["temperature"]
            if int(temperature) > temperature_threshold:
                higher_temperature_samples.append(f"{sample_id} - temperature: {temperature}")
        if higher_temperature_samples:
            violations_list.append(f"Not all temperature samples were lower than threshold {temperature_threshold}, "
                                   f"please check {higher_temperature_samples}")


def validate_power(players, chip_type, traffic_json, power_threshold, violations_list):
    with allure.step(f"Validate all power samples are below the power_thresholds"):
        dut_cli_obj = players['dut']['cli']
        power_samples = traffic_json["Power_samples"]
        power_samples.pop('sample_params', None)
        power_df = get_avg_samples_power_dataframe(dut_cli_obj, chip_type, power_samples)
        power_df_with_total = validate_power_df_by_collectors(power_df, power_threshold, violations_list)
        allure.attach(power_df_with_total.to_html(), 'Power full dataframe', allure.attachment_type.HTML)
        get_sum_power_df_by_collectors_group(power_df)


def get_avg_samples_power_dataframe(cli_obj, chip_type, power_samples):
    current_sum = None
    for sample_id, power_sample in power_samples.items():
        power_df = get_power_dataframe(cli_obj, power_sample['sensors_output'], chip_type)
        if current_sum is not None:
            current_sum += power_df["Current (A)"]
        else:
            current_sum = power_df["Current (A)"]
    power_df["Current (A)"] = current_sum.div(len(power_samples)).round(3)
    power_df["Power (W)"] = (power_df["Voltage (V)"] * power_df["Current (A)"]).round(3)
    return power_df


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
                controller_dict_df_entry["Power Supply"] = controller_name
                controller_dict_df_entry["Address"] = address
                controller_dict_df_entry["Voltage (V)"] = controller_info_dict[f"vout{index}"]
                controller_dict_df_entry["Current (A)"] = controller_info_dict[f"iout{index}"]
                controller_dict_df_entry["Power (W)"] = (controller_dict_df_entry["Voltage (V)"] *
                                                         controller_dict_df_entry["Current (A)"])
                power_dp.append(controller_dict_df_entry)
    return pd.DataFrame(power_dp)


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
        r"VCORE & 1.8V_Tile": {"counter": 0, "Power Supply": "VCORE & 1.8V_Tile", "Address": []},
        r"VCORE TILES \d & \d \(VDD_Tx\)": {"counter": 0, "Power Supply": "VCORE TILES", "Address": []},
        r"DVDD TILES \d & \d \(DVDD_Tx\)": {"counter": 0, "Power Supply": "DVDD TILES", "Address": []},
    }
    power_df_by_group = power_df.groupby(["Power Supply", "Address"])["Power (W)"].sum().reset_index()
    for index, row in power_df_by_group.iterrows():
        for collector_regex in collectors_regex_counters.keys():
            if re.search(collector_regex, row["Power Supply"]):
                collectors_regex_counters[collector_regex]["counter"] += row["Power (W)"]
                collectors_regex_counters[collector_regex]["Address"].append(row["Address"])
                rows_to_drop.append(index)
    power_df_by_group = power_df_by_group.drop(rows_to_drop)
    power_df_to_concat = []
    for collector_regex, counter_dict in collectors_regex_counters.items():
        if counter_dict["counter"] > 0:
            new_row = {"Power Supply": counter_dict["Power Supply"],
                       "Address": ",".join(counter_dict["Address"]),
                       "Power (W)": counter_dict["counter"]}
            power_df_to_concat.append(new_row)
    new_rows = pd.DataFrame(power_df_to_concat)
    power_df_by_collectors_group = pd.concat([power_df_by_group, new_rows], ignore_index=True)
    power_df_by_collectors_group_with_total = append_total_power(power_df_by_collectors_group)
    allure.attach(power_df_by_collectors_group_with_total.to_html(),
                  'Power summary by collectors', allure.attachment_type.HTML)
    return power_df_by_collectors_group


def validate_power_df_by_collectors(power_df, collectors_power_threshold, violations_list):
    power_total_th = collectors_power_threshold.get("TOTAL")
    total_power = power_df["Power (W)"].sum()
    for index, row in power_df.iterrows():
        collector_name = row["Power Supply"]
        collector_power = row["Power (W)"]
        for power_supply_regex, collector_th in collectors_power_threshold.items():
            if re.search(power_supply_regex, collector_name):
                if collector_power > collector_th:
                    violations_list.append(f"Power for {collector_name}: {collector_power} W,  "
                                           f"was higher than threshold {collector_th}, "
                                           f"please check table \"Power full dataframe\" in allure attachments")

    if total_power > power_total_th:
        violations_list.append(f"Total power {total_power} W was higher than total power threshold {power_total_th}, "
                               f"please check table \"Power full dataframe\" in allure attachments")
    power_df_with_total = append_total_power(power_df)
    return power_df_with_total


def append_total_power(power_df):
    total_power = power_df["Power (W)"].sum()
    new_row = pd.DataFrame([{"Power Supply": "Total Power", "Power (W)": total_power}])
    power_df_with_total = pd.concat([power_df, new_row], ignore_index=True)
    return power_df_with_total

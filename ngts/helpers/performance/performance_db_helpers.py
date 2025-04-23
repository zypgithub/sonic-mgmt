import os.path
import json
import pandas as pd
from datetime import datetime

from ngts.constants.constants import InfraConst
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, ValidationConsts, PowerConsts, MRCConsts


def create_performance_db_template(players, session_id, setup_name):
    """
    The function creates a file with the DUT system information

    Args:
        players: setups players fixture
        session_id: Mars session id, i.e, "9438676"
        setup_name: i.e, "nv_performance_mtvr-moose-17"

    Returns:
    the DUT system information template, and write into perf_db.json file
    {
        "testType": "Switch",
        "documentVersion": 0,
        "documentSource": "NV_Performance",
        "regression": true,
        "runDate": "23-02-2025 14:07:40",
        "linkToData": null,
        "dutSystemInformation": {
            "marsSessionId": "9438676",
            "setupName": "nv_performance_mtvr-moose-17",
            "osType": "DVS",
            "chip": "SPECTRUM4",
            "board": "sn5600",
            "sdkVersion": "4.7.3094-003",
            "hwChassisRev": "AJ",
            "modelNumber": "MSN-9N402-00RI-7N0_Ax",
            "hostDetails": "mtvr-moose-17, IP N/A",
            "serialNumber": "MT2443J011Q7",
            "onieVersion": "2023.11-5.3.0012-115200",
            "psid": "MT_0000000955",
            "osVersion": "dvs-os-sonic_4.7.1920_DEV_LK6.1.38_x86_64---2024-09-09 10:43:49"
        },
        result: {},
    }
    """
    cli_object = players['dut']['cli']
    dut_system_information = cli_object.performance.get_dut_system_information(session_id, setup_name)
    performance_db_template = {
        "testType": "Switch",
        "documentVersion": 0,
        "documentSource": "NV_Performance",
        "regression": True,
        "runDate": datetime.now().strftime(MongoDbConsts.TIME_REGEX_FORMAT),
        "linkToData": None,
        "dutSystemInformation": dut_system_information,
        "result": {}
    }
    with open(MongoDbConsts.PERF_MONGO_DB_RESULTS_PATH, 'w') as file:
        json.dump(performance_db_template, file, indent=4)
    return performance_db_template


def add_test_mongo_metadata(testname, metadata_dict):
    """
    Any test maintains a JSON file with the test specific information,
    that later will be stored in the full db file that will be uploaded into mongo db

    Args:
        testname: i.e, test_ar_perf_link_flap[port_repeated_toggle-4096-IPv6]
        metadata_dict: a dictionary with the info to update on the test, i.e., {"timeStamp": "23-02-2025 14:07:40"}

    Returns:
     None
    """
    test_info_path = os.path.join(PerfConsts.REQUIRMENTS_DIR, f"{testname}_info_dump.json")
    if os.path.exists(test_info_path):
        with open(test_info_path, "r+") as f:
            test_specific_values = json.load(f)
            test_specific_values.update(metadata_dict)
        with open(test_info_path, "w") as f:
            json.dump(test_specific_values, f, indent=4)
    else:
        test_specific_values = metadata_dict
        with open(test_info_path, "w") as f:
            json.dump(test_specific_values, f, indent=4)


def create_test_validation_entry_to_db(players, test_name):
    """
    Args:
        players: setups players fixture
        test_name: i.e, test_ar_perf_link_flap[port_repeated_toggle-4096-IPv6]

    Returns:
        create tests validation information entry in the mongo db format,
        and write the update test entry into the test information file
    """
    cli_object = players['dut']['cli']
    test_specific_values = cli_object.performance.get_test_specific_values(test_name)
    validation_json = test_specific_values.pop(MongoDbConsts.VALIDATOR_RESULTS, None)
    ports_group_df = pd.DataFrame(test_specific_values.pop(MongoDbConsts.PORT_GROUP_DF))
    os_ports_name_mapping_df = pd.DataFrame(test_specific_values.pop(ValidationConsts.OS_PORTS_NAME_MAPPING_DATAFRAME))
    power_total = test_specific_values.pop(MongoDbConsts.POWER_TOTAL, [])
    power_by_collectors_group = test_specific_values.pop(MongoDbConsts.POWER_BY_COLLECTORS, [])
    if validation_json:
        test_specific_values[MongoDbConsts.VALIDATOR_RESULTS] = restructure_validator_results(validation_json,
                                                                                              ports_group_df,
                                                                                              os_ports_name_mapping_df,
                                                                                              power_total,
                                                                                              power_by_collectors_group)

    test_info_path = os.path.join(PerfConsts.REQUIRMENTS_DIR, f"{test_name}_info_dump.json")
    with open(test_info_path, "w") as f:
        json.dump(test_specific_values, f, indent=4)


def restructure_validator_results(validation_json, ports_group_df, os_ports_name_mapping_df, power_total, power_by_collectors_group):
    """
    Args:
        validation_json: the JSON from the SDK TrafficValidator
        ports_group_df: a list of dicts with group name for each port
        power_total: a list of dictionaries representing a dataframe with the power information
        power_by_collectors_group: a list of dictionaries representing a dataframe with the power information
        by collectors group

    Returns:
        an updated dict with the validator info for mongo db
    """
    test_validation_to_mongo_db = {}
    test_validation_to_mongo_db[MongoDbConsts.BW_COUTERS_DATA] = get_bw_counters_data(validation_json, ports_group_df, os_ports_name_mapping_df)
    test_validation_to_mongo_db[MongoDbConsts.TC_DATA] = restructure_tc(validation_json)
    test_validation_to_mongo_db[MongoDbConsts.TEMP_DATA] = restructure_temp(validation_json)
    test_validation_to_mongo_db[MongoDbConsts.POWER_TOTAL] = restructure_power(power_total)
    test_validation_to_mongo_db[MongoDbConsts.POWER_BY_COLLECTORS] = restructure_power(power_by_collectors_group)
    if not test_validation_to_mongo_db[MongoDbConsts.TC_DATA]:
        test_validation_to_mongo_db.pop(MongoDbConsts.TC_DATA)
    return test_validation_to_mongo_db


def restructure_counters(validation_json):
    """
    take the max counter value from all the samples
    Args:
        validation_json: the JSON from the SDK TrafficValidator

    Returns:
        a single df with the counters max values
    """
    counters_samples = validation_json[ValidationConsts.COUNTERS_SAMPLES]
    counters_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)
    counters_df_list = collect_all_samples_into_df_list(counters_samples, ValidationConsts.COUNTERS_DATAFRAME)
    max_df = pd.concat(counters_df_list).groupby(level=0).max()
    updated_columns_names = get_updated_columns_names()
    counters_df = max_df.rename(columns=updated_columns_names)
    return counters_df


def get_updated_columns_names():
    updated_columns_names = {
        'if_out_discards': MongoDbConsts.IF_OUT_DISCARDS,
        'a_mac_control_frames_transmitted': MongoDbConsts.MAC_CONTROL_FRAMES_TRANSMITTED,
        'a_mac_control_frames_received': MongoDbConsts.MAC_CONTROL_FRAMES_RECEIVED,
        'a_pause_mac_ctrl_frames_transmitted': MongoDbConsts.PAUSE_MAC_CONTROL_FRAMES_TRANSMITTED,
        'a_pause_mac_ctrl_frames_received': MongoDbConsts.PAUSE_MAC_CONTROL_FRAMES_RECEIVED
    }
    ecn_counters_columns_names = dict(list(zip(MRCConsts.ECN_COUNTERS, MongoDbConsts.MONGO_DB_ECN_COUNTERS)))
    updated_columns_names.update(ecn_counters_columns_names)
    return updated_columns_names


def collect_all_samples_into_df_list(samples, sample_df_key):
    df_list = []
    for sample_id, sample in samples.items():
        df = pd.DataFrame(sample[sample_df_key])
        df_list.append(df)
    return df_list


def restructure_bw(validation_json):
    """
    Args:
        validation_json: the JSON from the SDK TrafficValidator

    Returns:
        a single df with the bandwidth avg values based on all the samples
    """
    bw_samples = validation_json[ValidationConsts.BW_SAMPLES]
    bw_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)
    df_list = collect_all_samples_into_df_list(bw_samples, ValidationConsts.BW_DATAFRAME)
    df_result = get_base_df(df_list)
    df_result[ValidationConsts.TX_RATE] = calculate_avg_on_all_samples(df_list, bw_samples, ValidationConsts.TX_RATE)
    df_result[ValidationConsts.RX_RATE] = calculate_avg_on_all_samples(df_list, bw_samples, ValidationConsts.RX_RATE)
    return df_result


def get_base_df(df_list):
    return df_list[0].copy()


def calculate_avg_on_all_samples(df_list, samples, sample_key):
    return round(sum(df[sample_key] for df in df_list) / len(samples), 3)


def get_bw_counters_data(validation_json, ports_group_df, os_ports_name_mapping_df):
    """
    Args:
        validation_json: the JSON from the SDK TrafficValidator
        ports_group_df: a list of dicts with group name for each port
        os_ports_name_mapping_df: a list of dicts with os port name for each port
    Returns:
        all the bandwidth and counters data for each port with the port group
    """
    counters_df = restructure_counters(validation_json)
    bw_df = restructure_bw(validation_json)
    bw_counters_data = pd.merge(counters_df, bw_df, on=ValidationConsts.PORT)
    merged_df = pd.merge(bw_counters_data, ports_group_df, on=ValidationConsts.PORT)
    if not os_ports_name_mapping_df.empty:
        merged_df = pd.merge(merged_df, os_ports_name_mapping_df, on=ValidationConsts.PORT)
    return merged_df.to_dict(orient='records')


def restructure_tc(validation_json):
    """
    Args:
        validation_json: the JSON from the SDK TrafficValidator

    Returns:
        a single df with the tc avg values based on all the samples
    """
    tc_samples = validation_json.get(ValidationConsts.TC_SAMPLES, None)
    tc_info = []
    if tc_samples:
        tc_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)
        df_list = collect_all_samples_into_df_list(tc_samples, ValidationConsts.TC_DATAFRAME)
        df_result = get_base_df(df_list)
        df_result.drop("occMaxByPort", axis=1, inplace=True)
        df_result[ValidationConsts.TC_OCC_AVG] = calculate_avg_on_all_samples(df_list, tc_samples, ValidationConsts.TC_OCC_AVG)
        df_result[ValidationConsts.TC_OCC_99] = calculate_avg_on_all_samples(df_list, tc_samples, ValidationConsts.TC_OCC_99)
        df_result[ValidationConsts.TC_OCC_MAX] = calculate_avg_on_all_samples(df_list, tc_samples, ValidationConsts.TC_OCC_MAX)
        df_result[ValidationConsts.TC_MAX_WATERMARK] = calculate_avg_on_all_samples(df_list, tc_samples, ValidationConsts.TC_MAX_WATERMARK)
        tc_info = df_result.to_dict(orient='records')
    return tc_info


def restructure_temp(validation_json):
    """
    Args:
        validation_json: the JSON from the SDK TrafficValidator

    Returns:
        a single average temp value based on all the samples
    """
    temperature_samples = validation_json[ValidationConsts.TEMPERATURE_SAMPLES]
    temperature_samples.pop(ValidationConsts.SAMPLES_PARAMS, None)
    temp_sum = 0
    for sample_id, temperature_samples_dict in temperature_samples.items():
        temp_sum += int(temperature_samples_dict[ValidationConsts.TEMPERATURE])
    temp_avg = temp_sum / len(temperature_samples)
    return temp_avg


def restructure_power(power_df):
    """
    removes null values from the power dataframe for the value of Total power
    Args:
        power_df: a list of dictionaries representing a dataframe with the power information, i.e,
        [{
            "powerSupply": "DVDD TILES",
            "address": "0x67,0x68,0x69,0x6a",
            "powerWatt": 103.38000000000001
        },
        {
            "powerSupply": "Total Power",
            "address": null,
            "powerWatt": 696.439
        }, ...]

    Returns:
        the updated power dataframe, i.e,
        [{
            "powerSupply": "DVDD TILES",
            "address": "0x67,0x68,0x69,0x6a",
            "powerWatt": 103.38000000000001
        },
        {
            "powerSupply": "Total Power",
            "powerWatt": 696.439
        }, ...]
    """
    for power_supply_dict in power_df:
        for key, value in power_supply_dict.items():
            if key == PowerConsts.POWER_SUPPLY and value == PowerConsts.TOTAL_POWER:
                power_supply_dict.pop(PowerConsts.POWER_SUPPLY_ADDRESS, None)
                power_supply_dict.pop(PowerConsts.POWER_CURRENT, None)
                power_supply_dict.pop(PowerConsts.POWER_VOLTAGE, None)
                break
    return power_df


def add_allure_url_into_perf_test(report_url, test_case_name, is_ipv6):
    """
    updates the allure URL report in the test info
    Args:
        report_url: a url link to the test's allure report
        test_case_name: the pytest name of the test
        is_ipv6: is the test running with the ipv6 flag

    Returns:
        None
    """
    test_name = test_case_name.split("::")[-1]
    class_name = test_case_name.split("::")[-2]
    full_test_name = class_name + "_" + test_name
    ip = InfraConst.IPV6 if is_ipv6 else InfraConst.IPV4
    perf_test_name = full_test_name.replace("]", f"-{ip}]")
    test_info_path = os.path.join(PerfConsts.REQUIRMENTS_DIR, f"{perf_test_name}_info_dump.json")
    if os.path.exists(test_info_path):
        with open(test_info_path, "r+") as f:
            db_json = json.load(f)
            db_json[MongoDbConsts.ALLURE_URL] = report_url
        with open(test_info_path, "w") as f:
            json.dump(db_json, f, indent=4)


def get_perf_test_name(request, is_ipv6):
    """
    Args:
        request: pytest request object
        is_ipv6: is the test running with the ipv6 flag, i.e, True

    Returns:
        name of the test including the class and ip flag info,
        i.e, TestSPCXRA_x1Split_800G_test_ar_perf_link_flap[port_repeated_toggle-4096-IPv6]
    """
    ip = InfraConst.IPV6 if is_ipv6 else InfraConst.IPV4
    test_name = request.node.cls.__name__ + "_" + request.node.name
    test_name_with_ip_param = test_name.replace("]", f"-{ip}]")
    return test_name_with_ip_param

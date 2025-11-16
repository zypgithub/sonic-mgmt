import allure
import pandas as pd
from collections import defaultdict
from ngts.constants.performance_constants import ValidationConsts, MongoDbConsts, PerfConsts
from ngts.cli_wrappers.dvs.dvs_cli import DvsCli
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.helpers.performance.performance_db_helpers import restructure_performance_counters, restructure_bw
from ngts.helpers.performance.performance_db_helpers import add_test_mongo_metadata


def get_port_expected_packets_value(port_speed, packet_size, interval):
    return get_port_expected_pps(port_speed, packet_size) * interval


def get_performance_counters_params():
    """
    This function is used to get the performance counters interval and
    allowed margin between sdk dump generation time with and without performance counters

    if the issue 4618585 is active,
    the performance counters interval is 30 milliseconds
    and performance counters impact on SDK generation time MUST be <= 1.3 seconds in all scenarios

    if the issue is closed,
    the performance counters interval is 100 microseconds
    and performance counters impact on SDK generation time MUST be <= 1 seconds in all scenarios

    :return: performance counters interval in seconds, dump generation time margin in seconds
    """
    if is_redmine_issue_active([4618585])[0]:
        return 0.03, 1.3
    else:
        return 0.0001, 1


def parse_performance_counters(cli_object, performance_counters_df):
    sdk_port_to_local_port_mapping, sdk_port_to_speed_mapping = cli_object.performance.get_port_mapping_df()
    sdk_port_to_local_port_mapping_df = pd.DataFrame(list(sdk_port_to_local_port_mapping.items()), columns=[ValidationConsts.PORT, ValidationConsts.INSTANCE])
    sdk_port_to_speed_mapping_df = pd.DataFrame(list(sdk_port_to_speed_mapping.items()), columns=[ValidationConsts.PORT, ValidationConsts.SPEED])
    performance_counters_df = pd.merge(performance_counters_df, sdk_port_to_local_port_mapping_df, on=ValidationConsts.INSTANCE, how='left')
    performance_counters_df = pd.merge(performance_counters_df, sdk_port_to_speed_mapping_df, on=ValidationConsts.PORT, how='left')
    return performance_counters_df


def validate_performance_counters(traffic_json, cli_object, allowed_deviation, packet_size, test_name, violations_list):
    """
    Validates the performance counters from the performance counters json.
    """
    if is_redmine_issue_active([4731421])[0]:
        with allure.step(f"Skipping performance counters validation due to performance bug #4731421"):
            original_violations_list = violations_list.copy()

    with allure.step(f"Validate performance counters"):
        interval, dump_generation_time_margin = get_performance_counters_params()
        performance_counters_df, sdk_generation_time_with_perf_counters, sdk_generation_time_without_perf_counters = restructure_performance_counters(traffic_json)
        bw_df = restructure_bw(traffic_json)
        performance_counters_df = parse_performance_counters(cli_object, performance_counters_df)
        performance_counters_bw_df = update_performance_counters_df(performance_counters_df, bw_df, packet_size, interval, allowed_deviation)
        ports_with_deviation_above_threshold = get_ports_with_deviation_above_threshold(performance_counters_bw_df, allowed_deviation)
        if ports_with_deviation_above_threshold:
            violations_list.append(f"Performance counters for Ports: {ports_with_deviation_above_threshold} are not within the expected range of {allowed_deviation}%")
        if sdk_generation_time_with_perf_counters > PerfConsts.SDK_GENERATION_SECONDS_THRESHOLD:
            violations_list.append(f"SDK generation time with performance counters is greater than 30 seconds, please check the SDK generation time")
        if sdk_generation_time_without_perf_counters > PerfConsts.SDK_GENERATION_SECONDS_THRESHOLD:
            violations_list.append(f"SDK generation time without performance counters is greater than 30 seconds, please check the SDK generation time")
        if sdk_generation_time_with_perf_counters > sdk_generation_time_without_perf_counters + dump_generation_time_margin:
            violations_list.append(f"SDK generation time with performance counters is: {sdk_generation_time_with_perf_counters} seconds,"
                                   f"greater than SDK generation time without performance counters: {sdk_generation_time_without_perf_counters} seconds"
                                   f"+ dump generation time margin: {dump_generation_time_margin} seconds")
        allure.attach(performance_counters_bw_df.to_html(), name="Performance Counters", attachment_type=allure.attachment_type.HTML)
        performance_counters_mongo_db_df = performance_counters_bw_df[[ValidationConsts.PORT, ValidationConsts.PERFORMANCE_COUNTER_NAME, ValidationConsts.PERFORMANCE_COUNTER_VALUE]].to_dict(orient='records')
        add_test_mongo_metadata(test_name, {
            MongoDbConsts.PERFORMANCE_COUNTERS_DATA: {ValidationConsts.SDK_GENERATION_TIME_WITH_PERF_COUNTERS: sdk_generation_time_with_perf_counters,
                                                      ValidationConsts.SDK_GENERATION_TIME_WITHOUT_PERF_COUNTERS: sdk_generation_time_without_perf_counters},
            ValidationConsts.PERFORMANCE_COUNTERS_DATAFRAME: performance_counters_mongo_db_df})
    if is_redmine_issue_active([4731421])[0]:
        return original_violations_list
    return violations_list


def update_performance_counters_df(performance_counters_df, bw_df, packet_size, interval, allowed_deviation):
    """
    This function is used to update the performance counters dataframe with the bandwidth dataframe
    :param performance_counters_df: performance counters dataframe
    :param bw_df: bandwidth dataframe
    :param packet_size: packet size
    :param interval: interval
    :param allowed_deviation: allowed deviation
    :return: performance counters dataframe with the updated columns, for:
    - ValidationConsts.PORT_BW: the port bandwidth in bytes per second,
    i.e, if speed is 400G and TX_RATE is 0.97, then PORT_BW is 400G * 0.97 = 388Gbps
    - ValidationConsts.PERFORMANCE_COUNTER_EXPECTED_VALUE: the expected performance counter value
    - ValidationConsts.DEVIATION: the deviation of the performance counter value from the expected value
    - ValidationConsts.DEVIATION_ABOVE_THRESHOLD: True if the deviation is above the allowed deviation, False otherwise
    """
    performance_counters_bw_df = pd.merge(performance_counters_df, bw_df, on=[ValidationConsts.PORT], how='right')
    performance_counters_bw_df[ValidationConsts.PORT_BW] = performance_counters_bw_df[ValidationConsts.SPEED] * performance_counters_bw_df[ValidationConsts.TX_RATE]
    performance_counters_bw_df[ValidationConsts.PERFORMANCE_COUNTER_EXPECTED_VALUE] = performance_counters_bw_df[ValidationConsts.PORT_BW].apply(get_port_expected_packets_value, args=(packet_size, interval))
    performance_counters_bw_df[ValidationConsts.DEVIATION] = (abs(performance_counters_bw_df[ValidationConsts.PERFORMANCE_COUNTER_VALUE] - performance_counters_bw_df[ValidationConsts.PERFORMANCE_COUNTER_EXPECTED_VALUE]) / performance_counters_bw_df[ValidationConsts.PERFORMANCE_COUNTER_EXPECTED_VALUE]) * 100
    performance_counters_bw_df[ValidationConsts.DEVIATION_ABOVE_THRESHOLD] = performance_counters_bw_df[ValidationConsts.DEVIATION] > allowed_deviation
    return performance_counters_bw_df


def get_ports_with_deviation_above_threshold(performance_counters_bw_df, allowed_deviation):
    """
    This function is used to get the ports with deviation above the threshold
    :param performance_counters_bw_df: performance counters bandwidth dataframe
    :param allowed_deviation: allowed deviation
    :return: ports with deviation above the threshold, i.e, "0x1001, 0x1002, 0x1003"
    """
    ports_with_deviation_above_threshold = performance_counters_bw_df[performance_counters_bw_df[ValidationConsts.DEVIATION_ABOVE_THRESHOLD]][ValidationConsts.PORT].tolist()
    ports_with_deviation_above_threshold = [str(port) for port in ports_with_deviation_above_threshold]
    ports_with_deviation_above_threshold_str = ", ".join(ports_with_deviation_above_threshold)
    return ports_with_deviation_above_threshold_str


def get_port_expected_pps(bandwidth_Gbps, packet_size_bytes):
    """
    This function is used to get the expected pps for a port
    :param bandwidth_Gbps: bandwidth in Gigabits
    :param packet_size_bytes: packet size in bytes

    Explanation of the formula:
    Step 1: Define the conversion constant
            bits_per_byte = 8 - There are 8 bits in one byte
    Step 2: Convert gigabits to bytes
            bytes_per_gigabit = 1e9 / 8 = 125,000,000 bytes
            1 gigabit = 10⁹ bits
            Divide by 8 to convert bits to bytes
    Step 3: Calculate bandwidth in bytes per second
            bandwidth_Bps = bandwidth_Gbps * 125,000,000
            This converts the port's bandwidth from Gbps (gigabits per second) to Bps (bytes per second)
            For example: A 10 Gbps port = 10 × 125,000,000 = 1,250,000,000 bytes/second
    Step 4: Calculate packets per second
            pps = bandwidth_Bps / packet_size_bytes
            Divides total bytes per second by the size of each packet
            For example: If bandwidth is 1,250,000,000 Bps and packet size is 64 bytes:
            PPS = 1,250,000,000 / 64 = 19,531,250 packets/second
    :return: expected pps
    """
    bits_per_byte = 8
    bytes_per_gigabit = 1e9 / bits_per_byte
    bandwidth_Bps = bandwidth_Gbps * bytes_per_gigabit
    pps = bandwidth_Bps / packet_size_bytes
    return pps


def should_validate_performance_counters(cli_object):
    """
    This function is used to check if the performance counters should be validated,
    i.e, if the cli object is a DvsCli, then the performance counters should be validated
    :param cli_object: cli object
    :return: True if the performance counters should be validated, False otherwise
    """
    return isinstance(cli_object, DvsCli)

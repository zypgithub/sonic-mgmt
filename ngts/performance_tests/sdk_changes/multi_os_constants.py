import os
import sys

LIB_ROOT = os.path.join(os.path.abspath(__file__)[:os.path.abspath(__file__)
                        .find('sx_sdk_py_tests')]) + 'sx_sdk_py_tests'
if LIB_ROOT not in sys.path:
    sys.path.append(LIB_ROOT)

from libs.base_classes.multi_nos.power_temp_constants import PowerTempConsts


class MultiNosConstants:
    TC_NUM = 7
    PG_NUM = 8
    PG = 'pg'
    TC = 'tc'
    OCC_AVG = 'occAvg'
    OCC_99 = 'occ99'
    OCC_MAX = 'occMax'
    MAX_WATERMARK = 'maxWatermark'
    PORT = 'port'
    TX_RATE = 'txRate'
    RX_RATE = 'rxRate'
    TC_OCC_MAX_BY_PORT = 'occMaxByPort'
    BW_STATS = 'bw_stats'
    TX_MIN_BW_PERCENTAGE = 'min_tx_bw'
    TX_MIN_BW_PORT = 'min_tx_bw_port'
    TX_MAX_BW_PERCENTAGE = 'max_tx_bw'
    TX_MAX_BW_PORT = 'max_tx_bw_port'
    TX_BW_DIFF = 'tx_diff'
    RX_MIN_BW_PERCENTAGE = 'min_rx_bw'
    RX_MIN_BW_PORT = 'min_rx_bw_port'
    RX_MAX_BW_PERCENTAGE = 'max_rx_bw'
    RX_MAX_BW_PORT = 'max_rx_bw_port'
    RX_BW_DIFF = 'rx_diff'
    TX_BW_AVG = 'tx_avg'
    RX_BW_AVG = 'rx_avg'
    SAMPLE_DURATION_ENV_VAR = "SAMPLE_DURATION"
    BW_SAMPLE_DELAY_ENV_VAR = "BW_SAMPLE_DELAY"
    TC_SAMPLE_DELAY_ENV_VAR = "TC_SAMPLE_DELAY"
    COUNTERS_SAMPLE_DELAY_ENV_VAR = "COUNTERS_SAMPLE_DELAY"
    SAMPLE_DURATION_DEFAULT = 60
    BW_SAMPLE_DELAY_DEFAULT = 5
    TC_SAMPLE_DELAY_DEFAULT = 1
    COUNTERS_SAMPLE_DELAY_DEFAULT = 1
    BW_SAMPLE_COUNT = 1
    TC_PG_SAMPLE_COUNT = 1000
    TC_LATENCY_SAMPLE_COUNT = 1
    COUNTERS_SAMPLE_COUNT = 1
    BW_SAMPLES = "Bandwidth_samples"
    PERF_COUNTERS_SAMPLES = "perf_counters_samples"
    TC_PG_SAMPLES = "TC_PG_samples"
    TC_LATENCY_SAMPLES = "TC_latency_samples"
    COUNTERS_SAMPLES = "Counters_samples"
    PACKET_SIZE = 1024
    BW_DATAFRAME = "bandwidth_dataframe"
    TC_DATAFRAME = "tc_dataframe"
    PG_DATAFRAME = "pg_dataframe"
    TC_LATENCY_DATAFRAME = "tc_latency_dataframe"
    TC_AVG_LATENCY = "tcAvgLatency"
    TC_MAX_LATENCY = "tcMaxLatency"
    TC_99_LATENCY = "tc99Latency"
    COUNTERS_DATAFRAME = "counters_dataframe"
    DISCARDS_COUNTER = 'if_out_discards'
    SAMPLE_DURATION_PARAM = "duration"
    DELAY_BETWEEN_SAMPLES_PARAM = "delay_between_samples"
    SAMPLE_COUNT = "sample_count"
    SAMPLE_RATE_PARAM = "rate"
    SAMPLE_PARAMS = "sample_params"
    BUFFER_AUTO_MODE = "BUFFER_AUTO_MODE"
    CONGESTION_TH_LO = "CONGESTION_TH_LO"
    DVS_CONF_FW_LATENCY_OPT = "/root/sys_sdk/sx_sdk_py_tests/tools/multi_nos/dqs_to_glc.py"
    SHAPER_VALUE_ENV_VAR = "SHAPER_VALUE"
    SHAPER_VALUE_DEFAULT = 0.975
    CLEAR_COUNTERS_ENV_VAR = "CLEAR_COUNTERS"
    CLEAR_COUNTERS_DEFAULT = "True"
    LATENCY_BIN_SIZE_RESOLUTION = 2
    LATENCY_MIN_BOUNDARY = 1
    LATENCY_SAMPLE_TIME = 11
    PERFORMANCE_COUNTERS_DATAFRAME = "performanceCountersDataframe"
    SDK_GENERATION_TIME_WITH_PERF_COUNTERS = "sdkGenerationTimeWithPerfCounters"
    SDK_GENERATION_TIME_WITHOUT_PERF_COUNTERS = "sdkGenerationTimeWithoutPerfCounters"
    PERFORMANCE_COUNTER_NAME = "performanceCounterName"
    PERFORMANCE_COUNTER_VALUE = "performanceCounterValue"
    COLLECTORS_LIST = [BW_SAMPLES, COUNTERS_SAMPLES, TC_PG_SAMPLES, TC_LATENCY_SAMPLES, PERF_COUNTERS_SAMPLES,
                       PowerTempConsts.POWER_SAMPLES, PowerTempConsts.TEMPERATURE_SAMPLES]


class MultiNosSharedData:
    DEFAULT_SHARED_JSON = "shared_communication.json"
    ALIBABA_ACL_DUMP_PATH = 'alibaba_acl_path'
    ALIBABA_ACL_DUMP_NAME = 'alibaba_acl_name'

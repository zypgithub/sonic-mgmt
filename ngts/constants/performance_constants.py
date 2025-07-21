import os
from ngts.constants.constants import NvosCliTypes, DVSCliTypes, BugHandlerConst
from infra.tools.redmine.redmine_api import is_redmine_issue_active


class Cl_Consts:
    CL_LOG_PORT_FILE_PATH = os.path.join(BugHandlerConst.NGTS_PATH, 'scripts/')
    CL_LOG_PORT_FILE = 'log_port_cumulus.py'
    BONUS_PORTS = {
        'Spectrum-3': [],
        'Spectrum-4': ['swp65'],
        'Spectrum-5': ['swp65', 'swp66']
    }
    CL_HOME_DIR = "/home/cumulus"
    CL_PYTHON_PATH = "/home/cumulus/sdk_env/bin/python3.11"
    CL_GRUB_PATH = 'boot'
    CL_GA_IMAGE = "/auto/sw_system_project/NVOS_INFRA/cumulus_images/GA/5.10/cumulus-linux-mlx-amd64.bin.devsigned"
    COMMON_IP_PREFIX_LEFT = "130"
    COMMON_IP_PREFIX_RIGHT = "110"


class ValidationConsts:
    TC_DATAFRAME = "tc_dataframe"
    TC_SAMPLES = "TC_samples"
    TC_NAME = "tc"
    TC_OCC_AVG = "occAvg"
    TC_OCC_99 = "occ99"
    TC_OCC_MAX = "occMax"
    TC_MAX_WATERMARK = "maxWatermark"
    TX_RATE = "txRate"
    RX_RATE = "rxRate"
    COUNTERS_SAMPLES = "Counters_samples"
    SAMPLES_PARAMS = "sample_params"
    COUNTERS_DATAFRAME = "counters_dataframe"
    BW_SAMPLES = "Bandwidth_samples"
    BW_DATAFRAME = "bandwidth_dataframe"
    BW_STATS = 'bw_stats'
    TX_BW_AVG = 'tx_avg'
    RX_BW_AVG = 'rx_avg'
    TX_RATE_MIN = 'min_tx_bw'
    RX_RATE_MIN = 'min_rx_bw'
    PORT = "port"
    OS_PORT_NAME = "osPortName"
    OS_PORTS_NAME_MAPPING_DATAFRAME = "osPortsNameMappingDataframe"
    UNTRIMMED_PRECENTAGE = "untrimmedPrecentage"
    TRIMMING_PRECENTAGE = "trimmingPrecentage"
    DROPPED_WITHOUT_TRIMMING_PRECENTAGE = "droppedWithoutTrimmingPrecentage"
    UNTRIMMED_BYTES_PRECENTAGE = "untrimmedBytesPrecentage"
    TRIMMING_BYTES_PRECENTAGE = "trimmingBytesPrecentage"
    POWER_SAMPLES = "Power_samples"
    TEMPERATURE_SAMPLES = "Temperature_samples"
    TEMPERATURE = "temperature"
    SENSORS_OUTPUT = 'sensors_output'


class PerfConsts:
    # Performance Setup Aliases
    LEFT_TG_ALIAS = "left_tg"
    RIGHT_TG_ALIAS = "right_tg"
    DUT_ALIAS = "dut"
    PERF_SETUP_PLAYERS_ALIASES = [LEFT_TG_ALIAS, DUT_ALIAS, RIGHT_TG_ALIAS]
    PERF_SETUP_TG_ALIASES = [LEFT_TG_ALIAS, RIGHT_TG_ALIAS]
    PERF_SETUP_DUT_ALIASES = [DUT_ALIAS]
    ECN_CAPABLE_TRANSPORT = 1
    # Sample Parameters
    SAMPLES_PARAMS = {
        "SAMPLE_DURATION": 30,
        "BW_SAMPLE_DELAY": 5,
        "TC_SAMPLE_DELAY": 5,
        "COUNTERS_SAMPLE_DELAY": 5,
        "CLEAR_COUNTERS": "True"
    }
    CLEAR_COUNTERS_ENV_VAR = "CLEAR_COUNTERS"
    SHAPER_VALUE_ENV_VAR = "SHAPER_VALUE"
    SHAPER_VALUE = 0.99
    OCC_AVG_TH = 400
    TC_NUM = 6 if is_redmine_issue_active([4393276])[0] else 7
    # Thresholds
    OCC_TH_DICT = {ValidationConsts.TC_OCC_AVG: OCC_AVG_TH}
    TEMPERATURE_TH = 105
    LOW_AR_THRESHOLD = 190
    MED_AR_THRESHOLD = 800
    HIGH_AR_THRESHOLD = 2000

    # CLI Types
    NON_SONIC_CLI_TYPE = NvosCliTypes.NvueCliTypes + DVSCliTypes.DVSCliTypes

    # Paths and Directories
    DVS_RUN_TEST_PATH = "/root/sys_sdk/sx_sdk_py_tests/tests/run_tests.py"
    DEFAULT_PERF_TEMPLATES_DIR = "performance_config_templates"
    CONFIG_FILES_DIR = os.path.join(BugHandlerConst.NGTS_PATH, 'tests/performance/config_files')
    REQUIRMENTS_DIR = os.path.join(BugHandlerConst.NGTS_PATH, 'performance_tests/')
    SDK_DEB_DIR_TEMPLATE = "/auto/sw_system_release/sx_sdk_eth/sx_sdk_eth-{SDK_VERSION}/DEBS/6.1.0-11-2-amd64/"
    SDK_VERSION_PATH = "/auto/sw_system_release/sx_sdk_eth/"
    SDK_INSTALL_PATH = "/auto/mswg/projects/sx_mlnx_os/sx_fit_regression/libs/scripts/install_sdk_wrapper.py"
    CLEAN_SWITCH_PATH = "/auto/mswg/projects/sx_mlnx_os/sx_fit_regression/libs/scripts/sx_sdk_clean_logs.py"
    FW_BURN_PATH = "/auto/mswg/projects/sx_mlnx_os/sx_fit_regression/libs/scripts/sdk_fw_burn.py"
    LATEST_SDK_DEB_DIR_TEMPLATE = "/auto/sw_system_release/sx_sdk_eth/lastrc_{SDK_BRANCH}/DEBS/"

    # File Names
    REQUIRMENTS_FILE = 'requirements.txt'
    FW_VERSION_FILE = "FW.txt"

    # Export Python Path
    EXPORT_PYTHONPATH = (
        'export PYTHONPATH=/root/sys_sdk/sx_sdk_py_tests/:'
        '/root/sys_sdk/sx_sdk_py_tests/tests/:'
        '/root/sys_sdk/sx_sdk_py_tests/tools/bpf_api_tracer/:'
        '/root/sys_sdk/sx_sdk_py_tests/libs/swig/:'
        '/root/sys_sdk/sx_sdk_py_tests/tests/traffic_tests/vlan_bridge/'
    )

    # Traffic Generator and Validator Constants
    DVS_TG_NAME = "GenericTrafficGenerator"
    DVS_TG_VALIDATOR_NAME = "TrafficValidator"
    DVS_TG_MLOOP_CONFIGURATION = "ConfigureMloopOnTG"
    DVS_TG_REMOVE_MLOOP_CONFIGURATION = "RemoveMloopOnTG"
    DVS_GET_PORTS = "GetPorts"
    DVS_UNSPLIT_ALL_PORTS = "UnsplitAllPorts"
    DVS_DYNAMIC_CONF_PREFIX = "DynamicConfiguration"

    # Traffic Generator Aliases
    LEFT_TG_ALIAS = "left_tg"
    RIGHT_TG_ALIAS = "right_tg"
    TG_ALIAS_LIST = [LEFT_TG_ALIAS, RIGHT_TG_ALIAS]
    CL_ROCE_LOSSLESS_DEFAULT_TC = 96
    DVS_LOSSLESS_TC = 26
    DVS_LOSSY_TC = 34
    DVS_CONTROL_TC = 48
    PORT_GROUPS = "port_groups"

    # Configuration Files
    AR_PERF_CONFIG_FOLDER = 'config_files'
    SDK_TEST_CONF = "sdk_test_conf"
    CUSTOM_IBM_PROFILE_JSON = 'ibm_profile.json'
    IBM_CUSTOM_PROFILE_NAME = 'ibm_profile'
    DISABLE_MAC_SCRIPT = "disable_mac_learn.py"
    LB_FILTER_SCRIPT = "api_for_filter.py"
    LB_SCRIPT_TG = "run_lb_script.sh"
    IP_NEIGH_SCRIPT = "config_ip_neigh.sh"
    TRAFFIC_SENDER_SCRIPT_TG = "traffic_generator.py"
    PACKETS_AGING_SCRIPT = "packets_aging.py"
    CONFIG_FILES_LIST_LEFT_TG = [DISABLE_MAC_SCRIPT, LB_FILTER_SCRIPT, LB_SCRIPT_TG]
    CONFIG_FILES_LIST_RIGHT_TG = [DISABLE_MAC_SCRIPT, LB_FILTER_SCRIPT, LB_SCRIPT_TG]
    CONFIG_FILES_DICT = {
        LEFT_TG_ALIAS: CONFIG_FILES_LIST_LEFT_TG,
        RIGHT_TG_ALIAS: CONFIG_FILES_LIST_RIGHT_TG
    }

    # Sample Times
    DEFAULT_SAMPLE_TIME_IN_SEC = 20
    EXTENDED_SAMPLE_TIME_IN_SEC = 60
    PACKET_SIZE_4K = 4096
    # Packet Sizes and Utilization Thresholds
    PACKET_SIZE_LIST = [PACKET_SIZE_4K]
    TG_TX_UTIL_TH = 95
    ROCE_ACK_SIZE = 64
    RTT_PROB_SIZE = 138
    RTT_PROB_RESPONSE_SIZE = 118
    CNP_SIZE = 116
    NACK_SIZE = 102
    SACK_SIZE = 170
    GFP_CONTROL_SIZE = 138

    # Indexes
    VALUE_INDEX = 0
    TIMESTAMP_INDEX = 1

    # Log Ports
    HEX_BASE = 16
    LOG_PORT_LEFT_TG = 0x10001
    LOG_PORT_RIGHT_TG = 0x10081
    LOG_PORTS_DICT = {LEFT_TG_ALIAS: LOG_PORT_LEFT_TG, RIGHT_TG_ALIAS: LOG_PORT_RIGHT_TG}

    # IP Neighbors
    L_IP_NEIGH = "10.10.10.10"
    R_IP_NEIGH = "20.20.20.20"

    # Supported Reboot Types
    PERF_SUPPORTED_REBOOT_TYPES = ['reboot', 'config reload -y']

    # Sleep Time
    SLEEP_TIME_BEFORE_SAMPLE = 15

    # Images and Grub Paths
    SONIC_GA_IMAGE = "/auto/sw_system_release/sonic/202311/202311/dev/sonic-mellanox.bin"
    DVS_GA_IMAGE = ("/auto/sw/release/sw_system/sx_mlnx_evb/dvs-os-sonic_4.7.3106_DEV_x86-64-0/"
                    "dvs-os-sonic_4.7.3106_DEV_LK6.1.38_x86-64_installer.bin")
    SONIC_DVS_GRUB_PATH = 'host'
    GRUB_PATH_DICT = {
        "SONiC": SONIC_DVS_GRUB_PATH,
        "Cumulus": Cl_Consts.CL_GRUB_PATH,
        "DVS": SONIC_DVS_GRUB_PATH
    }
    SDK_DEB_FILE_TEMPLATE = "sys-sdk-git_1.mlnx.{SDK_VERSION}_amd64.deb"
    LATEST_SDK_DEB_FILE_TEMPLATE = "sys-sdk-git_1.mlnx.*_amd64.deb"

    # Miscellaneous
    USED_SITE = "MTL"
    DVS_CLI_TYPE = "DVS"
    DVS_WELCOME_MESSAGE = "Welcome to the NVIDIA Switch Development System"
    ROCE_PORT = 4791
    UDP_SOURCE_PORT = 2001
    TCP_SOURCE_PORT = 2001
    UDP_DOURCE_PORT = 80
    TCP_DOURCE_PORT = 80
    ADAPTIVE_ROUTING_ENABLED = 1
    IP_PROTOCOL_UDP = "UDP"
    IP_PROTOCOL_TCP = "TCP"

    # Counters
    COUNTERS = [
        "if_out_discards",
        "a_mac_control_frames_transmitted",
        "a_mac_control_frames_received",
        "a_pause_mac_ctrl_frames_transmitted",
        "a_pause_mac_ctrl_frames_received"
    ]
    ECN_COUNTERS = [f'tx_ecn_marked_tc_{tc}' for tc in range(TC_NUM)]
    TC_BUFFER_DISCARDS_COUNTERS = [f'tx_no_buffer_discard_uc_tc_{tc}' for tc in range(TC_NUM)]
    TC_WRED_DISCARDS_COUNTERS = [f'tx_wred_discard_tc_{tc}' for tc in range(TC_NUM)]
    TOTAL_COUNTERS = [
        'ingress_policy_engine',
        'ingress_vlan_membership',
        'ingress_tag_frame_type',
        'egress_vlan_membership',
        'loopback_filter',
        'egress_general',
        'egress_hoq',
        'port_isolation',
        'egress_policy_engine',
        'ingress_tx_link_down',
        'egress_stp_filter',
        'egress_hoq_stall',
        'egress_sll',
        'ingress_discard_all',
        'a_alignment_errors',
        'a_frame_check_sequence_errors',
        'a_frame_too_long_errors',
        'a_in_range_length_errors',
        'a_symbol_error_during_carrier',
        'a_unsupported_opcodes_received',
        'a_in_range_length_errors',
        'a_mac_control_frames_transmitted',
        'a_mac_control_frames_received',
        'a_pause_mac_ctrl_frames_transmitted',
        'a_pause_mac_ctrl_frames_received',
        'if_in_discards',
        'if_in_errors',
        'if_out_discards',
        'if_out_errors',
        'ether_stats_crc_align_errors',
        'ether_stats_drop_events',
        'dot3stats_alignment_errors',
        'dot3stats_carrier_sense_errors',
        'dot3stats_fcs_errors',
        'dot3stats_frame_too_longs',
        'dot3stats_sqe_test_errors',
        'dot3stats_symbol_errors',
        'dot3stats_internal_mac_transmit_errors',
        'dot3stats_internal_mac_receive_errors',
        'port_rx_fcs_errors',
        'port_rx_no_buffer',
        'port_rx_other_errors',
        'port_tx_errors',
    ] + ECN_COUNTERS + TC_BUFFER_DISCARDS_COUNTERS + TC_WRED_DISCARDS_COUNTERS

    # Timeouts
    TIMEOUT_FOR_NEXTHOP_RESOLUTION = 180
    TIMEOUT_FOR_UNINSTALL_MODE = {
        "SPC3": 900,
        "SPC4": 900,
        "SPC5": 480
    }
    TIMEOUT_FOR_INSTALL_MODE = 120


class SPCXRAConsts:
    DUT_TX_UTIL_AUTO_TH_DICT = {4096: 0.92}
    DUT_TX_UTIL_IBM_TH_DICT = {4096: 0.96}
    PACKET_NUM_400G_x2 = 8
    PACKET_NUM_800G_x1 = 16


class MongoDbConsts:
    PERF_MONGO_DB_FILENAME = "perf_res.db"
    PERF_MONGO_DB_RESULTS_PATH = os.path.join(PerfConsts.REQUIRMENTS_DIR, PERF_MONGO_DB_FILENAME)
    PORT_GROUP_NAME = "portGroupName"
    PORT_GROUP_DF = "portGroupDataframe"
    BW_COUTERS_DATA = "bandwidthCountersData"
    TC_DATA = "tcData"
    TEMP_DATA = "temperatureData"
    TEST_NAME = "testName"
    TEST_WORKLOAD = "testWorkload"
    TEST_TRAFFIC_TYPE = "testTrafficType"
    INGRESS_PORT_SEQUENCE = "ingressPortSequence"
    TIME_STAMP = "timeStamp"
    TIME_REGEX_FORMAT = "%d-%m-%Y %H:%M:%S"
    TIME_REGEX_FORMAT_FOR_MONGO_DB = "%d-%m-%Y_%H-%M-%S"

    POWER_TOTAL = "powerTotal"
    POWER_BY_COLLECTORS = "powerByCollectors"
    ALLURE_URL = "allureUrl"
    TEST_RESULT = "result"
    VALIDATOR_RESULTS = "validatorResults"
    CONF_NAME = "configurationName"
    COLLECTION = ":COLLECTION:SwitchPerformanceCollection\n"
    CRITERIA = ":CRITERIA_FIELD:testType\n"
    MONGO_DB_DICT_PATH = "/auto/sw/projects/performance/results/mongodb/"
    MONGO_DB_UPLOADS = os.path.join(MONGO_DB_DICT_PATH, "for_upload/")
    MONGO_DB_ERRORS = os.path.join(MONGO_DB_DICT_PATH, "errors/")
    MONGO_DB_SANDBOX_TESTS = os.path.join(MONGO_DB_DICT_PATH, "Sandbox_testing/")
    MONGO_DB_SANDBOX_TESTING_COMMAND = f"{MONGO_DB_DICT_PATH}./initiate_sandbox"
    MONGO_DB_SANDBOX_TESTING_TIMEOUT = 30


class MRCConsts:
    MIN_INGRESS_PORTS_NUM = 4
    MAX_INGRESS_PORTS_NUM = 5
    INGRESS_PORT_NUMBER_LIST = list(range(MIN_INGRESS_PORTS_NUM, MAX_INGRESS_PORTS_NUM))
    HWSKU_BY_CHIP_TYPE = {
        "SPC4": {"leaf": "Mellanox-SN5600-C256S1",
                 "spine": "Mellanox-SN5600-C224O8"},
        "SPC5": {"leaf": "Mellanox-SN5640-C512S2",
                 "spine": "Mellanox-SN5640-C448O16"}
    }
    HWSKU_SWITCH_TYPE = {
        "Mellanox-SN5600-C256S1": 'ToRRouter',
        "Mellanox-SN5600-C224O8": 'LeafRouter',
        "Mellanox-SN5640-C512S2": 'ToRRouter',
        "Mellanox-SN5640-C448O16": 'LeafRouter'
    }
    UPSTREAM_DOWNSTREAM_NUM_OF_PORTS_BY_CHIP_TYPE = {
        "SPC4": 128,
        "SPC5": 180
    }
    VICTIM_PORTS_NUM = 90
    LEAF_ROUND_ROBIN_PORTS_NUM_BY_CHIP_TYPE = {
        "SPC4": {'group_size': 16, 'group_num': 8},
        "SPC5": {'group_size': 10, 'group_num': 18}
    }
    SPINE_ROUND_ROBIN_PORTS_NUM_BY_CHIP_TYPE = {
        "SPC4": {'group_size': 16, 'group_num': 7},
        "SPC5": {'group_size': 14, 'group_num': 16}
    }
    TRAFFIC_TYPE_IPV6 = "IPv6"
    TRAFFIC_TYPE_SRV6 = "SRv6"
    WEEKEND_TRAFFIC_TYPE_LIST = [TRAFFIC_TYPE_IPV6, TRAFFIC_TYPE_SRV6]
    WEEKDAY_TRAFFIC_TYPE_LIST = [TRAFFIC_TYPE_SRV6]
    # In case of running weekend regression, this list can be changed with 'if' statement checking os.environ.get('SKIP_WEEKEND_CASES') == 'yes'
    REGRESSION_TRAFFIC_TYPE_LIST = WEEKEND_TRAFFIC_TYPE_LIST
    INGRESS_PORT_SEQUENCE_CONSECUTIVE = 'consecutive'
    INGRESS_PORT_SEQUENCE_NON_CONSECUTIVE = 'non_consecutive'
    INGRESS_PORT_SEQUENCE = [INGRESS_PORT_SEQUENCE_NON_CONSECUTIVE]
    DUT_TX_UTIL_TH = 0.98
    BUFFER_CELL_SIZE = 192
    HALF_MRC_DATA_PACKET_SIZE = 11
    FULL_MRC_DATA_PACKET_SIZE = 22
    MAX_QUEUE_BUILDUP = 260
    MANY_TO_ONE_TRAFFIC_TC_OCC_TH = {ValidationConsts.TC_MAX_WATERMARK: HALF_MRC_DATA_PACKET_SIZE * MAX_QUEUE_BUILDUP}
    SPINE_MANY_TO_FEW_TRAFFIC_TC_OCC_TH = {ValidationConsts.TC_MAX_WATERMARK: HALF_MRC_DATA_PACKET_SIZE * 60}
    LEAF_MANY_TO_FEW_TRAFFIC_TC_OCC_TH = {ValidationConsts.TC_MAX_WATERMARK: HALF_MRC_DATA_PACKET_SIZE * 72}
    OCC_TH_DICT = {ValidationConsts.TC_OCC_AVG: HALF_MRC_DATA_PACKET_SIZE,
                   ValidationConsts.TC_OCC_99: FULL_MRC_DATA_PACKET_SIZE}
    ECN_COUNTERS = [f'tx_ecn_marked_tc_{tc}' for tc in range(PerfConsts.TC_NUM)]
    COUNTERS_WITH_ECN = PerfConsts.COUNTERS + ECN_COUNTERS
    MRC1_DSCP = 1
    MRC1_RTT_DSCP = 2
    MRC2_DSCP = 3
    MRC2_RTT_DSCP = 4
    MRC1_RETRANSMISSION_DSCP = 5
    MRC2_RETRANSMISSION_DSCP = 6
    CNP_DSCP = 32
    SACK_DSCP = 36
    NACK_DSCP = 33
    PROBE_ACK_DSCP = 31
    ROCE_ACK_DSCP = 30
    MRC_TRIMMED_DSCP = 11
    GFP_CONTROL_DSCP = 17
    GFP_DATA_DSCP = 41
    MRC_TRIMMED_TC = 4
    OPT_TS = 'OPT_TS'
    OPT_TS_DEFAULT = 256
    MINIMAL_TRIM_SIZE = 256
    MAX_TRIM_SIZE_CHECKING_RANGE = 512
    TRIMMING_TC = '4'
    MRC1_DATA_TC = '1'
    MRC2_DATA_TC = '2'
    MRC_RETRANSMISSION_TC = '3'
    TRIMMING_ELEGABLE_QUEUE_NUM = [MRC1_DATA_TC, MRC2_DATA_TC, MRC_RETRANSMISSION_TC]
    MRC_CONTROL_TC = '4'
    GFP_DATA_TC = '5'
    WORKLOAD_1_TC_LIST = [int(MRC1_DATA_TC), int(MRC2_DATA_TC), int(MRC_RETRANSMISSION_TC), int(TRIMMING_TC)]
    WORKLOAD_2_TC_LIST = [int(MRC1_DATA_TC), int(MRC2_DATA_TC), int(MRC_RETRANSMISSION_TC), int(TRIMMING_TC), int(GFP_DATA_TC)]
    MRC_DATA_ONLY_WORKLOAD_TC_LIST = [int(MRC2_DATA_TC)]
    WORKLOAD1_NAME = 'workload_1'
    WORKLOAD2_NAME = 'workload_2'
    MRC1_DATA_ONLY_WORKLOAD_NAME = 'mrc1_data_only'
    MRC2_DATA_ONLY_WORKLOAD_NAME = 'mrc2_data_only'
    MRC_REGRESSION_WORKLOADS_LIST = [WORKLOAD1_NAME]
    SHAPER_VALUE = 0.975
    SHAPER_VALUE_AFTER_TEST = 1.0


class PowerConsts:
    POWER_TH_PER_ASIC = {
        "SPC3": None,
        "SPC4": {
            r"VCORE TILES \d & \d \(VDD_Tx\)": 17,
            r"DVDD TILES \d & \d \(DVDD_Tx\)": 18.13,
            r"HVDD TILES \(HVDD_T\d+\)": 118,
            r"VDDSCC": 46,
            r"VCORE MAIN \(VDD_M\)": 345,
            "TOTAL": 754
        },
        "SPC5": {
            r"VCORE TILES \d & \d \(VDD_Tx\)": 28.5,
            r"DVDD TILES \d & \d \(DVDD_Tx\)": 30.75,
            r"HVDD TILES \(HVDD_T\d+\)": 222,
            r"VDDSCC": 42,
            r"VCORE MAIN \(VDD_M\)": 310,
            "TOTAL": 811
        }
    }
    CONTROLLER_REGEX = r'\w*\d*-i2c-\d*-\d*\w*'
    POWER_SUPPLY = "powerSupply"
    POWER_SUPPLY_ADDRESS = "address"
    POWER_VOLTAGE = "voltage"
    POWER_CURRENT = "currentAmp"
    POWER_WATT = "powerWatt"
    TOTAL_POWER = "Total Power"


class SPCControllers:
    SPCControllers_DICT = {
        "SPC3": {
            "0x62": "VCORE MAIN",
            "0x64": "1.8V_MAIN & 1.2V_MAIN",
            "0x66": "VCORE & 1.8V_Tile",
            "0x68": "VCORE & 1.8V_Tile",
            "0x6a": "VCORE & 1.8V_Tile",
            "0x6c": "VCORE & 1.8V_Tile",
            "0x6e": "VCORE & 1.8V_Tile",
        },
        "SPC4": {
            "0x61": "HVDD TILES (HVDD_T47)",
            "0x62": "VCORE MAIN (VDD_M)",
            "0x63": "VCORE TILES 0 & 1 (VDD_Tx)",
            "0x64": "VCORE TILES 2 & 3 (VDD_Tx)",
            "0x65": "VCORE TILES 4 & 5 (VDD_Tx)",
            "0x66": "VCORE TILES 6 & 7 (VDD_Tx)",
            "0x67": "DVDD TILES 0 & 1 (DVDD_Tx)",
            "0x68": "DVDD TILES 2 & 3 (DVDD_Tx)",
            "0x69": "DVDD TILES 4 & 5 (DVDD_Tx)",
            "0x6a": "DVDD TILES 6 & 7 (DVDD_Tx)",
            "0x6c": "HVDD TILES (HVDD_T03)",
            "0x6e": "VDDSCC",
        },
        "SPC5": {
            "0x62": "VCORE MAIN (VDD_M)",
            "0x63": "VCORE TILES 0 & 1 (VDD_Tx)",
            "0x64": "VCORE TILES 2 & 3 (VDD_Tx)",
            "0x65": "VCORE TILES 4 & 5 (VDD_Tx)",
            "0x66": "VCORE TILES 6 & 7 (VDD_Tx)",
            "0x67": "DVDD TILES 0 & 1 (DVDD_Tx)",
            "0x68": "DVDD TILES 2 & 3 (DVDD_Tx)",
            "0x69": "DVDD TILES 4 & 5 (DVDD_Tx)",
            "0x6a": "DVDD TILES 6 & 7 (DVDD_Tx)",
            "0x6c": "HVDD TILES (HVDD_T03)",
            "0x6e": "VDDSCC",
        }
    }

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
    LOW_AR_THRESHOLD = 400
    MED_AR_THRESHOLD = 800
    HIGH_AR_THRESHOLD = 2000


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
    BW_MIN = 'min_bw'
    PORT = "port"
    POWER_SAMPLES = "Power_samples"
    TEMPERATURE_SAMPLES = "Temperature_samples"
    TEMPERATURE = "temperature"
    SENSORS_OUTPUT = 'sensors_output'


class PerfConsts:
    # Performance Setup Aliases
    PERF_SETUP_PLAYERS_ALIASES = ['left_tg', 'dut', 'right_tg']
    PERF_SETUP_TG_ALIASES = ['left_tg', 'right_tg']
    PERF_SETUP_DUT_ALIASES = ['dut']

    # Sample Parameters
    SAMPLES_PARAMS = {
        "SAMPLE_DURATION": 60,
        "BW_SAMPLE_DELAY": 5,
        "TC_SAMPLE_DELAY": 1,
        "COUNTERS_SAMPLE_DELAY": 1
    }
    OCC_AVG_TH = 400
    TC_NUM = 6 if is_redmine_issue_active([4393276])[0] else 7
    # Thresholds
    OCC_TH_DICT = {ValidationConsts.TC_OCC_AVG: OCC_AVG_TH}
    TEMPERATURE_TH = 105

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
    LATEST_SDK_DEB_DIR_TEMPLATE = "/auto/sw_system_release/sx_sdk_eth/lastrc_sx_sdk_{SDK_BRANCH}/DEBS/"

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

    # Traffic Generator Aliases
    LEFT_TG_ALIAS = "left_tg"
    RIGHT_TG_ALIAS = "right_tg"
    TG_ALIAS_LIST = [LEFT_TG_ALIAS, RIGHT_TG_ALIAS]
    CL_ROCE_LOSSLESS_DEFAULT_TC = 96

    # Configuration Files
    AR_PERF_CONFIG_FOLDER = 'config_files'
    CUSTOM_IBM_PROFILE_JSON = 'ibm_profile.json'
    IBM_CUSTOM_PROFILE_NAME = 'ibm_profile'
    DISABLE_MAC_SCRIPT = "disable_mac_learn.py"
    LB_FILTER_SCRIPT = "api_for_filter.py"
    LB_SCRIPT_TG = "run_lb_script.sh"
    IP_NEIGH_SCRIPT = "config_ip_neigh.sh"
    TRAFFIC_SENDER_SCRIPT_TG = "traffic_generator.py"
    CONFIG_FILES_LIST_LEFT_TG = [DISABLE_MAC_SCRIPT, LB_FILTER_SCRIPT, LB_SCRIPT_TG]
    CONFIG_FILES_LIST_RIGHT_TG = [DISABLE_MAC_SCRIPT, LB_FILTER_SCRIPT, LB_SCRIPT_TG]
    CONFIG_FILES_DICT = {
        LEFT_TG_ALIAS: CONFIG_FILES_LIST_LEFT_TG,
        RIGHT_TG_ALIAS: CONFIG_FILES_LIST_RIGHT_TG
    }

    # Sample Times
    DEFAULT_SAMPLE_TIME_IN_SEC = 20
    EXTENDED_SAMPLE_TIME_IN_SEC = 60

    # Packet Sizes and Utilization Thresholds
    PACKET_SIZE_LIST = [4096]
    TG_TX_UTIL_TH = 95

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
    ADAPTIVE_ROUTING_ENABLED = 1

    # Counters
    COUNTERS = [
        "if_out_discards",
        "a_mac_control_frames_transmitted",
        "a_mac_control_frames_received",
        "a_pause_mac_ctrl_frames_transmitted",
        "a_pause_mac_ctrl_frames_received"
    ]

    # Timeouts
    TIMEOUT_FOR_NEXTHOP_RESOLUTION = 180
    TIMEOUT_FOR_UNINSTALL_MODE = {
        "SPC3": 900,
        "SPC4": 900,
        "SPC5": 480
    }


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
    TIME_STAMP = "timeStamp"
    TIME_REGEX_FORMAT = "%d-%m-%Y %H:%M:%S"
    TIME_REGEX_FORMAT_FOR_MONGO_DB = "%d-%m-%Y_%H:%M:%S"
    IF_OUT_DISCARDS = "ifOutDiscards"
    MAC_CONTROL_FRAMES_TRANSMITTED = "aMacControlFramesTransmitted"
    MAC_CONTROL_FRAMES_RECEIVED = "aMacControlFramesReceived"
    PAUSE_MAC_CONTROL_FRAMES_TRANSMITTED = "aPauseMacCtrlFramesTransmitted"
    PAUSE_MAC_CONTROL_FRAMES_RECEIVED = "aPauseMacCtrlFramesReceived"
    MONGO_DB_ECN_COUNTERS = [f'txEcnMarkedTc{tc}' for tc in range(PerfConsts.TC_NUM)]
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


class MRCConsts:
    HWSKU_BY_CHIP_TYPE = {
        "SPC4": {"leaf": "Mellanox-SN5600-C256S1",
                 "spine": "Mellanox-SN5600-C224O8"},
        "SPC5": {"leaf": "Mellanox-SN5640-C512S2",
                 "spine": "Mellanox-SN5640-C448O16"}
    }
    DUT_TX_UTIL_TH = 0.98
    BUFFER_CELL_SIZE = 192
    OCC_TH_DICT = {ValidationConsts.TC_OCC_AVG: 11,
                   ValidationConsts.TC_OCC_99: 22}
    ECN_COUNTERS = [f'tx_ecn_marked_tc_{tc}' for tc in range(PerfConsts.TC_NUM)]
    COUNTERS_WITH_ECN = PerfConsts.COUNTERS + ECN_COUNTERS


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

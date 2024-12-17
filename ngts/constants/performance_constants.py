import os

from ngts.constants.constants import NvosCliTypes, DVSCliTypes, BugHandlerConst


class PerfConsts:
    PERF_SETUP_PLAYERS_ALIASES = ['left_tg', 'dut', 'right_tg']
    PERF_SETUP_TG_ALIASES = ['left_tg', 'right_tg']
    # TODO: remove DUT_PKT_INFO / TG_ALIASES_PKT_INFO once traffic generator is not static
    DUT_PKT_INFO = {
        "MAC": '00:01:02:03:04:05',
        "IP": '4.4.4.4',
        "IPv6": '192:168:0:0:0:0:0:1'
    }
    TG_ALIASES_PKT_INFO = {
        "MAC": {'left_tg': '00:01:02:03:04:06', 'right_tg': '00:00:00:00:10:60'},
        "IP": {'left_tg': '10.0.1.0', 'right_tg': '192.168.1.0'},
        "IPv6": {'left_tg': '192:168:5:1:1:1:2:0', 'right_tg': '192:168:5:1:1:2:2:0'}
    }
    SAMPLES_PARAMS = {
        "SAMPLE_DURATION": 60,
        "BW_SAMPLE_INTERVAL": 5,
        "TC_SAMPLE_INTERVAL": 1,
        "COUNTERS_SAMPLE_INTERVAL": 1
    }
    OCC_AVG_TH = 400
    CL_HOME_DIR = "/home/cumulus"
    CL_PYTHON_PATH = "/home/cumulus/sdk_env/bin/python3.11"
    NON_SONIC_CLI_TYPE = NvosCliTypes.NvueCliTypes + DVSCliTypes.DVSCliTypes
    DVS_RUN_TEST_PATH = "/auto/mtrsysgwork/slutati/sys_sdk/sx_sdk_py_tests/tests/run_tests.py"
    DEFAULT_PERF_TEMPLATES_DIR = "performance_config_templates"
    DVS_TG_NAME = "GenericTrafficGenerator"
    DVS_TG_VALIDATOR_NAME = "TrafficValidator"
    DVS_TG_MLOOP_CONFIGURATION = "ConfigureMloopOnFan"
    DVS_TG_REMOVE_MLOOP_CONFIGURATION = "RemoveMloopOnFan"
    DVS_GET_TG_PORTS = "GetFanPorts"
    CONFIG_FILES_DIR = os.path.join(BugHandlerConst.NGTS_PATH, 'tests/performance/config_files')
    REQUIRMENTS_DIR = os.path.join(BugHandlerConst.NGTS_PATH, 'performance_tests/')
    REQUIRMENTS_FILE = 'requirements.txt'
    SDK_DEB_DIR_TEMPLATE = "/auto/sw_system_release/sx_sdk_eth/sx_sdk_eth-{SDK_VERSION}/DEBS/6.1.0-11-2-amd64/"
    SDK_DEB_FILE_TEMPLATE = "sys-sdk-git_1.mlnx.{SDK_VERSION}_amd64.deb"
    EXPORT_PYTHONPATH = 'export PYTHONPATH=/root/sys_sdk/sx_sdk_py_tests/:/root/sys_sdk/sx_sdk_py_tests/tests/:' \
                        '/root/sys_sdk/sx_sdk_py_tests/tools/bpf_api_tracer/:/root/sys_sdk/sx_sdk_py_tests/libs/swig/:' \
                        '/root/sys_sdk/sx_sdk_py_tests/tests/traffic_tests/vlan_bridge/'
    LEFT_TG_ALIAS = "left_tg"
    RIGHT_TG_ALIAS = "right_tg"
    TG_ALIAS_LIST = [LEFT_TG_ALIAS, RIGHT_TG_ALIAS]
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
    CONFIG_FILES_DICT = {LEFT_TG_ALIAS: CONFIG_FILES_LIST_LEFT_TG, RIGHT_TG_ALIAS: CONFIG_FILES_LIST_RIGHT_TG}
    DEFAULT_SAMPLE_TIME_IN_SEC = 20
    EXTENDED_SAMPLE_TIME_IN_SEC = 60
    PACKET_SIZE_LIST = [1536, 2048, 4096]
    PACKET_SIZE_TO_PACKET_NUM_DICT = {1536: 32, 2048: 16, 4096: 8}
    TG_TX_UTIL_TH = 95
    DUT_TX_UTIL_TH_DICT = {1536: 64, 2048: 80, 4096: 92}
    DUT_TX_UTIL_W_IBM_TH_DICT = {1536: 64, 2048: 80, 4096: 96}
    VALUE_INDEX = 0
    TIMESTAMP_INDEX = 1
    LOG_PORT_LEFT_TG = 0x10001
    LOG_PORT_RIGHT_TG = 0x10081
    LOG_PORTS_DICT = {LEFT_TG_ALIAS: LOG_PORT_LEFT_TG, RIGHT_TG_ALIAS: LOG_PORT_RIGHT_TG}
    L_IP_NEIGH = "10.10.10.10"
    R_IP_NEIGH = "20.20.20.20"
    PERF_SUPPORTED_REBOOT_TYPES = ['reboot', 'config reload -y']
    SLEEP_TIME_BEFORE_SAMPLE = 15
    SONIC_GA_IMAGE = "/auto/sw_system_release/sonic/202311/202311/dev/sonic-mellanox.bin"
    CL_GA_IMAGE = "/auto/sw_system_project/NVOS_INFRA/cumulus_images/GA/5.10/cumulus-linux-mlx-amd64.bin.devsigned"
    DVS_GA_IMAGE = ("/auto/sw/release/sw_system/sx_mlnx_evb/dvs-os-sonic_4.7.1920_DEV_x86-64-0/dvs-os-sonic"
                    "_4.7.1920_DEV_LK6.1.38_x86-64_installer.bin")
    CL_GRUB_PATH = 'boot'
    SONIC_DVS_GRUB_PATH = 'host'
    GRUB_PATH_DICT = {"SONiC": SONIC_DVS_GRUB_PATH, "Cumulus": CL_GRUB_PATH, "DVS": SONIC_DVS_GRUB_PATH}
    SDK_VERSION_PATH = "/auto/sw_system_release/sx_sdk_eth/"
    FW_VERSION_FILE = "FW.txt"
    USED_SITE = "MTL"
    SDK_INSTALL_PATH = "/auto/mswg/projects/sx_mlnx_os/sx_fit_regression/libs/scripts/install_sdk_wrapper.py"
    CLEAN_SWITCH_PATH = "/auto/mswg/projects/sx_mlnx_os/sx_fit_regression/libs/scripts/sx_sdk_clean_logs.py"
    FW_BURN_PATH = "/auto/mswg/projects/sx_mlnx_os/sx_fit_regression/libs/scripts/sdk_fw_burn.py"
    DVS_CLI_TYPE = "DVS"
    DVS_WELCOME_MESSAGE = "Welcome to the NVIDIA Switch Development System"

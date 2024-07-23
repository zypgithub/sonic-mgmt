import copy
import os


class PytestConst:
    run_config_only_arg = '--run_config_only'
    run_test_only_arg = '--run_test_only'
    run_cleanup_only_arg = '--run_cleanup_only'
    alluredir_arg = '--alluredir'
    disable_loganalyzer = '--disable_loganalyzer'
    disable_export_mars_cases_result = '--disable_exporting_results_to_mars_db'
    CUSTOM_SKIP_IF_DICT = 'custom_skip_if_dict'
    CUSTOM_TEST_SKIP_PLATFORM_TYPE = 'dynamic_tests_skip_platform_type'
    CUSTOM_TEST_SKIP_BRANCH_NAME = 'dynamic_tests_skip_branch_name'
    CUSTOM_TEST_SKIP_IMAGE_TYPE = "dynamic_tests_skip_image_type"
    LA_DYNAMIC_IGNORES_LIST = 'LA_DYNAMIC_IGNORES_LIST'
    GET_DUMP_AT_TEST_FALIURE = "GET_DUMP"
    IS_SANITIZER_IMAGE = 'IS_SANITIZER_IMAGE'
    DEPLOY_TEST_FILE_NAME = 'test_deploy_and_upgrade.py'


class SonicConst:
    PORT_SPLIT_NUM_1 = 1
    PORT_SPLIT_NUM_2 = 2
    PORT_SPLIT_NUM_4 = 4
    PORT_SPLIT_NUM_8 = 8
    PORT_LANE_NUM_1 = 1
    PORT_LANE_NUM_2 = 2
    PORT_LANE_NUM_4 = 4
    PORT_LANE_NUM_8 = 8
    FEC_RS_MODE = 'rs'
    FEC_FC_MODE = 'fc'
    FEC_NONE_MODE = 'none'
    FEC_AUTO_MODE = 'auto'
    FEC_MODE_LIST = [FEC_RS_MODE, FEC_FC_MODE, FEC_NONE_MODE]
    DOCKERS_LIST = ['swss', 'syncd', 'bgp', 'teamd', 'pmon', 'lldp', 'dhcp_relay',
                    'radv', 'eventd', 'database', 'snmp']
    DOCKERS_LIST_BF = ['swss', 'syncd', 'bgp', 'pmon', 'lldp', 'gnmi', 'eventd', 'database']
    DOCKERS_LIST_TOR = DOCKERS_LIST
    DOCKERS_LIST_LEAF = ['swss', 'syncd', 'bgp', 'teamd', 'pmon', 'lldp', 'radv', 'eventd', 'database', 'snmp']
    DAEMONS_DICT = {'swss': [], 'syncd': [], 'bgp': [],
                    'teamd': [], 'pmon': [], 'lldp': [], 'dhcp_relay': []}
    DAEMONS_DICT_BF = {'swss': [],
                       'syncd': [],
                       'bgp': [],
                       'pmon': ['pcied', 'rsyslogd', 'supervisor-proc-exit-listener', 'syseepromd', 'thermalctld',
                                'xcvrd'],
                       'lldp': []}

    SONIC_CONFIG_FOLDER = '/etc/sonic/'
    PORT_CONFIG_INI = 'port_config.ini'
    CONFIG_DB_JSON = 'config_db.json'
    CONFIG_DB_GNMI_JSON = 'config_db_gnmi.json'
    EXTENDED_CONFIG_DB_PATH = "extended_config_db.json"
    CONFIG_DB_JSON_PATH = SONIC_CONFIG_FOLDER + CONFIG_DB_JSON
    PLATFORM_JSON_PATH = "/usr/share/sonic/device/{PLATFORM}/platform.json"
    PMON_DAEMON_CONTROL_JSON_PATH = "/usr/share/sonic/device/{PLATFORM}/pmon_daemon_control.json"
    SAI_PROFILE_FILE_PATH = "/usr/share/sonic/device/{PLATFORM}/{HWSKU}/sai.profile"
    COPP_CONFIG = 'copp_cfg.json'

    BREAKOUT_MODE_WITH_DIFF_LANE_SUPPORTED_SPEEDS_REGEX = r"\dx\d+G\(\d\)\+\dx\d+G\(\d\)"  # i.e, 2x25G(2)+1x50G(2)

    # 1x100G[50G,25G,1G]
    BREAKOUT_MODE_WITH_ADDITIONAL_SUPPORTED_SPEEDS_REGEX = r"(\dx\d+G\[[\d+G,]+\]|\dx\d+\[[\d,]+\])"
    BREAKOUT_MODE_WITHOUT_ADDITIONAL_SUPPORTED_SPEEDS_REGEX = r"\dx\d+G"  # 2x50G

    BREAKOUT_MODES_REGEX = "{}|{}|{}".format(BREAKOUT_MODE_WITH_DIFF_LANE_SUPPORTED_SPEEDS_REGEX,
                                             BREAKOUT_MODE_WITH_ADDITIONAL_SUPPORTED_SPEEDS_REGEX,
                                             BREAKOUT_MODE_WITHOUT_ADDITIONAL_SUPPORTED_SPEEDS_REGEX)

    MINIGRAPH_XML = 'minigraph.xml'
    MINIGRAPH_XML_PATH = SONIC_CONFIG_FOLDER + MINIGRAPH_XML
    SANITIZER_FOLDER_PATH = "/var/log/asan"
    CONFIG = '/usr/local/bin/config'
    SHOW = '/usr/local/bin/show'

    TELEMETRY_PATH = "/etc/sonic/telemetry"
    TELEMETRY_SERVER_KEY = "/etc/sonic/telemetry/streamingtelemetryserver.key"
    TELEMETRY_SERVER_CER = "/etc/sonic/telemetry/streamingtelemetryserver.cer"
    TELEMETRY_DSMSROOT_KEY = "/etc/sonic/telemetry/dsmsroot.key"
    TELEMETRY_DSMSROOT_CER = "/etc/sonic/telemetry/dsmsroot.cer"

    RESOLV_CONF_NAME = 'resolv.conf'
    RESOLV_CONF_PATH = '/etc/' + RESOLV_CONF_NAME

    NVIDIA_LAB_DNS_FIRST = '10.211.0.124'
    NVIDIA_LAB_DNS_SECOND = '10.211.0.121'
    NVIDIA_LAB_DNS_THIRD = '10.7.77.135'
    NVIDIA_LAB_DNS_SEARCH = 'mtr.labs.mlnx labs.mlnx mlnx lab.mtl.com mtl.com'
    NVIDIA_AIR_DNS_FIRST = '8.8.8.8'
    NVIDIA_AIR_DNS_SECOND = '192.168.200.1'
    MIN_SHAPER_RATE_BPS = 25000000
    MAX_SHAPER_RATE_BPS = 0

    CONFIG_RELOAD_CMD = 'config reload -y'
    SONIC_CANONICAL_NOGA_GROUP = "SONiC_Canonical"
    SONIC_COMMUNITY_NOGA_GROUP = "SONiC_Community"
    SONIC_NOGA_GROUPS = [SONIC_CANONICAL_NOGA_GROUP, SONIC_COMMUNITY_NOGA_GROUP]


class CliType:
    NVUE = 'NVUE'
    SONIC = 'Sonic'
    SHELL = 'SHELL'
    MLNX_OS = 'MLNX_OS'
    SKYNET = 'skynet'


class DbConstants:
    METADATA_PATH = "/.autodirect/sw_regression/system/SONIC/MARS/metadata/"
    METADATA_PATH_NVOS = "/auto/sw_system_project/MLNX_OS_INFRA/NVOS-SONIC/MARS/metadata/"

    CLI_TYPE_PATH_MAPPING = {CliType.SONIC: METADATA_PATH,
                             CliType.NVUE: METADATA_PATH_NVOS,
                             CliType.SHELL: METADATA_PATH,
                             CliType.MLNX_OS: METADATA_PATH_NVOS,
                             CliType.SKYNET: METADATA_PATH}
    CREDENTIALS = {CliType.SONIC: {'server': 'YOKNVSQLDB.nvidia.com', 'database': 'sonic_mars',
                                   'username': os.getenv("SONIC_SERVER_USER"),
                                   'password': os.getenv("SONIC_SERVER_PASSWORD")},
                   CliType.NVUE: {'server': 'YOKNVSQLDB.nvidia.com', 'database': "NVOS",
                                  'username': os.getenv("NVUE_SERVER_USER"),
                                  'password': os.getenv("NVUE_SERVER_PASSWORD")},
                   CliType.SKYNET: {'server': 'YOKNVSQLDB.nvidia.com', 'database': 'skynet',
                                    'username': os.getenv("SKYNET_SERVER_USER"),
                                    'password': os.getenv("SKYNET_SERVER_PASSWORD")}}


class InfraConst:
    NVIDIA_MAIL_SERVER = 'mail.nvidia.com'
    HTTP_SERVER = 'http://fit69'
    HTTTP_SERVER_FIT16 = 'http://r-fit16-clone.mtr.labs.mlnx'
    MARS_TOPO_FOLDER_PATH = '/auto/sw_regression/system/SONIC/MARS/conf/topo/'
    MARS_CMIS_FOLDER_PATH = '/auto/sw_regression/system/SONIC/MARS/conf/cmis/'
    NVOS_REGRESSION_SHARED_RESULTS_DIR = '/auto/sw_regression/system/NVOS/MARS/results'
    REGRESSION_SHARED_RESULTS_DIR = '/auto/sw_regression/system/SONIC/MARS/results'
    RELEASE_RESULTS_DIR = '/auto/sw_regression/system/SONIC/release_results'
    HTTP_SERVER_MARS_TOPO_FOLDER_PATH = '{}{}'.format(HTTP_SERVER, MARS_TOPO_FOLDER_PATH)
    MYSQL_SERVER = '10.208.1.11'
    MYSQL_USER = 'sonic'
    MYSQL_PASSWORD = 'sonic11'
    MYSQL_DB = 'sonic'
    RC_SUCCESS = 0
    NGTS_PATH_PYTEST = '/ngts_venv/bin/pytest'
    SLEEP_BEFORE_RRBOOT = 5
    SLEEP_AFTER_RRBOOT = 35
    SLEEP_AFTER_WJH_INSTALLATION = 100
    IP = 'ip'
    MASK = 'mask'

    ALLURE_SERVER_IP = 'allure.nvidia.com'
    ALLURE_SERVER_PORT = ''
    ALLURE_SERVER_URL = 'https://{}'.format(ALLURE_SERVER_IP)
    ALLURE_REPORT_DIR = '/tmp/allure-results'
    ENV_SESSION_ID = 'SESSION_ID'
    ENV_LOG_FOLDER = 'LOG_FOLDER'
    CASES_DUMPS_DIR = 'cases_dumps'
    CASES_SYSLOG_DIR = 'cases_syslog'
    STM_IP = "10.209.104.53"


class LinuxConsts:
    CONF_FEC = "Configured FEC encodings"
    ACTIVE_FEC = "Active FEC encoding"
    FEC_AUTO_MODE = 'auto'
    error_exit_code = 1
    linux = 'linux'
    JERUSALEM_TIMEZONE = 'Asia/Jerusalem'
    ETC_UTC_TIMEZONE = 'Etc/UTC'


class TopologyConsts:
    engine = 'engine'
    players = 'players'
    ports = 'ports'
    interconnects = 'interconnects'
    ports_names = 'ports_names'


class ConfigDbJsonConst:
    PORT = 'PORT'
    ALIAS = 'alias'
    FEATURE = 'FEATURE'
    LLDP = 'lldp'
    STATUS = 'status'
    STATE = 'state'
    ENABLED = 'enabled'
    DEVICE_METADATA = "DEVICE_METADATA"
    MGMT_INTERFACE = "MGMT_INTERFACE"
    MGMT_INTERFACE_VALUE = '''{"eth0|%s/%s": {"gwaddr": "%s"}}'''
    MGMT_PORT = "MGMT_PORT"
    MGMT_PORT_VALUE = '''{"eth0":{"admin_status": "up", "alias": "eth0"}}'''
    LOCALHOST = "localhost"
    TYPE = 'type'
    TOR_ROUTER = 'ToRRouter'
    SONIC_HOST = 'SonicHost'
    HOSTNAME = "hostname"
    MAC = "mac"
    HWSKU = "hwsku"
    ADMIN_STATUS = "admin_status"
    DOCKER_ROUTING_CONFIG_MODE = "docker_routing_config_mode"
    SPLIT = "split"


class IpIfaceAddrConst:
    IPV4_ADDR_MASK_KEY = 'IPv4 address/mask'
    IPV6_ADDR_MASK_KEY = 'IPv6 address/mask'
    IPV4_MASK_24 = '24'


class AutonegCommandConstants:
    INTERFACE = "Interface"
    AUTONEG_MODE = "Auto-Neg Mode"
    SPEED = "Speed"
    ADV_SPEED = "Adv Speeds"
    TYPE = "Type"
    ADV_TYPES = "Adv Types"
    OPER = "Oper"
    ADMIN = "Admin"
    FEC = "FEC"
    FEC_OPER = "FEC Oper"
    FEC_ADMIN = "FEC Admin"
    WIDTH = "Width"
    CABLE_SPEED = "Supported Cable Speed"
    REGEX_PARSE_EXPRESSION_FOR_MLXLINK = {
        ADMIN: (r"State\s*:\s*(\w*)", "Active", "up", "down", None),
        OPER: (r"Physical state\s*:\s*(.*)", "LinkUp|ENABLE", "up", "down", None),
        SPEED: (r"Speed\s*:\s*(?:BaseT|BaseTx)?(\d*M|\d*G)", None, None, None, None),
        WIDTH: (r"Width\s*:\s*(\d+)x", None, None, None, None),
        FEC: (r"FEC\s*:\s*(.*)", "No FEC", "none", None, None),
        AUTONEG_MODE: (r"Auto Negotiation\s*:\s*(\w*\s*-*\s*\d*\w_*\d*X*|ON)",
                       r"FORCE\s+-\s+\d+\w_*\d*X*|ON", "enabled", "disabled", "Force"),
        CABLE_SPEED: (r"Supported Cable Speed (?:\(Ext.\))?\s+:\s+0x[0-9a-z]+\s+\(([\w.,]+)\)",
                      None, None, None, None)
    }
    PAM4_MIN_LANE_SPEED_MB = 50000


class DefaultCredentialConstants:
    OTHER_SONIC_USER = "admin"
    OTHER_SONIC_PASSWORD_LIST = ["password"]


class PlatformTypesConstants:
    FILTERED_PLATFORM_BULLDOG = 'SN2100'
    FILTERED_PLATFORM_ALLIGATOR = 'SN2201'
    FILTERED_PLATFORM_PANTHER = 'MSN2700'
    FILTERED_PLATFORM_ANACONDA = "MSN3700"
    FILTERED_PLATFORM_ANACONDA_C = "MSN3700C"
    FILTERED_PLATFORM_LIONFISH = "MSN3420"
    FILTERED_PLATFORM_TIGRIS = "MSN3800"
    FILTERED_PLATFORM_BOBCAT = "SN4280"
    FILTERED_PLATFORM_LIGER = "MSN4600"
    FILTERED_PLATFORM_LEOPARD = "MSN4700"
    FILTERED_PLATFORM_TIGON = "MSN4600C"
    FILTERED_PLATFORM_OCELOT = "MSN4410"
    FILTERED_PLATFORM_HIPPO = "SN5400"
    FILTERED_PLATFORM_MOOSE = "SN5600"

    PLATFORM_BULLDOG = 'x86_64-mlnx_msn2100-r0'
    PLATFORM_ALLIGATOR = 'x86_64-nvidia_sn2201-r0'
    PLATFORM_ANACONDA = 'x86_64-mlnx_msn3700-r0'
    PLATFORM_ANACONDA_C = 'x86_64-mlnx_msn3700c-r0'
    PLATFORM_BOXER = 'x86_64-mlnx_msn2010-r0'
    PLATFORM_LEOPARD = 'x86_64-mlnx_msn4700-r0'
    PLATFORM_LIGER = 'x86_64-mlnx_msn4600-r0'
    PLATFORM_LIONFISH = 'x86_64-mlnx_msn3420-r0'
    PLATFORM_OCELOT = 'x86_64-mlnx_msn4410-r0'
    PLATFORM_PANTHER = 'x86_64-mlnx_msn2700-r0'
    PLATFORM_SPIDER = 'x86_64-mlnx_msn2410-r0'
    PLATFORM_TIGON = 'x86_64-mlnx_msn4600c-r0'
    PLATFORM_TIGRIS = 'x86_64-mlnx_msn3800-r0'
    PLATFORM_HIPPO = 'x86_64-nvidia_sn5400-r0'
    PLATFORM_MOOSE = 'x86_64-nvidia_sn5600-r0'

    LOGS_ON_TMPFS_PLATFORMS = [PLATFORM_PANTHER, PLATFORM_BULLDOG]


class InterfacesTypeConstants:
    RJ45 = 'RJ45'

    INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC = {
        PlatformTypesConstants.FILTERED_PLATFORM_ALLIGATOR: {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['10M', '100M', '1000M', '1G', '10G', '25G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G']}
        },
        PlatformTypesConstants.FILTERED_PLATFORM_PANTHER: {
            "PANTHER_AOC": {
                SonicConst.PORT_LANE_NUM_1: {'SR': ['1G', '10G', '25G']},
                SonicConst.PORT_LANE_NUM_2: {'SR2': ['50G']},
                SonicConst.PORT_LANE_NUM_4: {'SR4': ['40G', '100G']}}
        },
        'default': {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G']},
        }
    }
    INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC2 = {
        PlatformTypesConstants.FILTERED_PLATFORM_LIONFISH: {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G']}
        },
        PlatformTypesConstants.FILTERED_PLATFORM_ANACONDA_C: {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G']}
        },
        PlatformTypesConstants.FILTERED_PLATFORM_TIGRIS: {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G']}
        },
        PlatformTypesConstants.FILTERED_PLATFORM_ANACONDA: {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G', '50G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G', '100G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G', '200G']}
        }
    }
    INTERFACE_TYPE_SUPPORTED_SPEEDS_SPC3 = {
        PlatformTypesConstants.FILTERED_PLATFORM_OCELOT: {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G', '50G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G', '100G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G', '200G', '400G']}
        },
        PlatformTypesConstants.FILTERED_PLATFORM_BOBCAT: {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G', '50G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G', '100G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G', '200G', '400G']}
        },
        PlatformTypesConstants.FILTERED_PLATFORM_LEOPARD: {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G', '50G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G', '100G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G', '200G', '400G']}
        },
        PlatformTypesConstants.FILTERED_PLATFORM_LIGER: {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G', '50G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G', '100G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G', '200G']}
        },
        PlatformTypesConstants.FILTERED_PLATFORM_TIGON: {
            SonicConst.PORT_LANE_NUM_1: {'CR': ['1G', '10G', '25G']},
            SonicConst.PORT_LANE_NUM_2: {'CR2': ['50G']},
            SonicConst.PORT_LANE_NUM_4: {'CR4': ['40G', '100G']}
        }

    }


class FecConstants:
    FEC_MODES_SPC_SPEED_SUPPORT = {
        SonicConst.FEC_FC_MODE: {
            SonicConst.PORT_SPLIT_NUM_1: {'10G': ['CR'],
                                          '25G': ['CR'],
                                          '40G': ['CR4'],
                                          '50G': ['CR2']
                                          },
            SonicConst.PORT_SPLIT_NUM_2: {'10G': ['CR'],
                                          '25G': ['CR'],
                                          '50G': ['CR2']
                                          },
            SonicConst.PORT_SPLIT_NUM_4: {'10G': ['CR'],
                                          '25G': ['CR'],
                                          '50G': ['CR2']
                                          }
        },
        SonicConst.FEC_RS_MODE: {
            SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                          '50G': ['CR2'],
                                          '100G': ['CR4']
                                          },
            SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                          '50G': ['CR2'],
                                          '100G': ['CR4']
                                          },
            SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                          '50G': ['CR2'],
                                          '100G': ['CR4']
                                          },
        },
        SonicConst.FEC_NONE_MODE: {
            SonicConst.PORT_SPLIT_NUM_1: {'1000M': ['CR'],
                                          '10G': ['CR'],
                                          '25G': ['CR'],
                                          '40G': ['CR4'],
                                          '50G': ['CR2'],
                                          '100G': ['CR4']
                                          },
            SonicConst.PORT_SPLIT_NUM_2: {'1000M': ['CR'],
                                          '10G': ['CR'],
                                          '25G': ['CR'],
                                          '50G': ['CR2'],
                                          '100G': ['CR4']
                                          },
            SonicConst.PORT_SPLIT_NUM_4: {'1000M': ['CR'],
                                          '10G': ['CR'],
                                          '25G': ['CR'],
                                          '50G': ['CR2'],
                                          '100G': ['CR4']
                                          }
        }
    }
    FEC_MODES_SPC2_SPEED_SUPPORT = {
        PlatformTypesConstants.FILTERED_PLATFORM_LIONFISH: {
            SonicConst.FEC_FC_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR']
                                              }
            },
            SonicConst.FEC_RS_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR']
                                              }
            },
            SonicConst.FEC_NONE_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR']
                                              }
            }
        },
        PlatformTypesConstants.FILTERED_PLATFORM_ANACONDA_C: {
            SonicConst.FEC_FC_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              },
            },
            SonicConst.FEC_RS_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4'],
                                              '200G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR'],
                                              },
            },
            SonicConst.FEC_NONE_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR']
                                              }
            }
        },
        PlatformTypesConstants.FILTERED_PLATFORM_TIGRIS: {
            SonicConst.FEC_FC_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {
                    '25G': ['CR'],
                    '50G': ['CR2']
                }
            },
            SonicConst.FEC_RS_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR'],
                                              },
            },
            SonicConst.FEC_NONE_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'10G': ['CR'],
                                              '25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR']
                                              }
            }
        }
    }

    FEC_MODES_SPC2_SPEED_SUPPORT[PlatformTypesConstants.FILTERED_PLATFORM_ANACONDA] = \
        copy.deepcopy(FEC_MODES_SPC2_SPEED_SUPPORT[PlatformTypesConstants.FILTERED_PLATFORM_ANACONDA_C])

    FEC_MODES_SPC3_SPEED_SUPPORT = {
        PlatformTypesConstants.FILTERED_PLATFORM_LEOPARD: {
            SonicConst.FEC_FC_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              }
            },
            SonicConst.FEC_RS_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR'],
                                              '100G': ['CR2'],
                                              '200G': ['CR4'],
                                              '400G': ['CR8']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR'],
                                              '100G': ['CR2'],
                                              '200G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR'],
                                              '100G': ['CR2']
                                              },
            },
            SonicConst.FEC_NONE_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'10G': ['CR'],
                                              '25G': ['CR'],
                                              '50G': ['CR2']
                                              }
            }
        },
        PlatformTypesConstants.FILTERED_PLATFORM_BOBCAT: {
            SonicConst.FEC_FC_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              }
            },
            SonicConst.FEC_RS_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR'],
                                              '100G': ['CR2'],
                                              '200G': ['CR4'],
                                              '400G': ['CR8']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR'],
                                              '100G': ['CR2'],
                                              '200G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR'],
                                              '100G': ['CR2']
                                              },
            },
            SonicConst.FEC_NONE_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'10G': ['CR'],
                                              '25G': ['CR'],
                                              '50G': ['CR2']
                                              }
            }
        },
        PlatformTypesConstants.FILTERED_PLATFORM_OCELOT: {
            SonicConst.FEC_FC_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              }
            },
            SonicConst.FEC_RS_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR', 'CR2'],
                                              '100G': ['CR2', 'CR4'],
                                              '200G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR', 'CR2'],
                                              '100G': ['CR2', 'CR4'],
                                              '200G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR', 'CR2'],
                                              '100G': ['CR2']
                                              }
            },
            SonicConst.FEC_NONE_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '50G': ['CR2']
                                              }
            }
        },
        PlatformTypesConstants.FILTERED_PLATFORM_LIGER: {
            SonicConst.FEC_FC_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR']
                                              }
            },
            SonicConst.FEC_RS_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4'],
                                              '200G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR']
                                              }
            },
            SonicConst.FEC_NONE_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR']
                                              }
            }
        },
        PlatformTypesConstants.FILTERED_PLATFORM_TIGON: {
            SonicConst.FEC_FC_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR']
                                              }
            },
            SonicConst.FEC_RS_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4'],
                                              '200G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR']
                                              }
            },
            SonicConst.FEC_NONE_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR']
                                              }
            }
        }
    }

    FEC_MODES_SPC4_SPEED_SUPPORT = {
        PlatformTypesConstants.FILTERED_PLATFORM_MOOSE: {
            SonicConst.FEC_FC_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {
                    '25G': ['CR'],
                    '50G': ['CR2']
                },
                SonicConst.PORT_SPLIT_NUM_2: {
                    '25G': ['CR'],
                    '50G': ['CR2']
                },
                SonicConst.PORT_SPLIT_NUM_4: {
                    '25G': ['CR'],
                    '50G': ['CR2']
                },
                SonicConst.PORT_SPLIT_NUM_8: {
                    '10G': ['CR'],
                    '25G': ['CR']
                }
            },
            SonicConst.FEC_RS_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR'],
                                              '200G': ['CR4'],
                                              '400G': ['CR4'],
                                              '800G': ['CR8'],
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR'],
                                              '200G': ['CR4'],
                                              '400G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR'],
                                              '200G': ['CR2'],
                                              },
                SonicConst.PORT_SPLIT_NUM_8: {'25G': ['CR'],
                                              '50G': ['CR'],
                                              '100G': ['CR']
                                              }
            },
            SonicConst.FEC_NONE_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_8: {'10G': ['CR'],
                                              '25G': ['CR']
                                              }
            }
        },
        PlatformTypesConstants.FILTERED_PLATFORM_HIPPO: {
            SonicConst.FEC_FC_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {
                    '25G': ['CR'],
                    '50G': ['CR2']
                },
                SonicConst.PORT_SPLIT_NUM_2: {
                    '25G': ['CR'],
                    '50G': ['CR2']
                },
                SonicConst.PORT_SPLIT_NUM_4: {
                    '25G': ['CR'],
                    '50G': ['CR2']
                },
                SonicConst.PORT_SPLIT_NUM_8: {
                    '10G': ['CR'],
                    '25G': ['CR']
                }
            },
            SonicConst.FEC_RS_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR2'],
                                              '200G': ['CR4'],
                                              '400G': ['CR8'],
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR2'],
                                              '200G': ['CR4'],
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'25G': ['CR'],
                                              '50G': ['CR2'],
                                              '100G': ['CR2'],
                                              },
                SonicConst.PORT_SPLIT_NUM_8: {'25G': ['CR'],
                                              '50G': ['CR'],
                                              }
            },
            SonicConst.FEC_NONE_MODE: {
                SonicConst.PORT_SPLIT_NUM_1: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_2: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2'],
                                              '100G': ['CR4']
                                              },
                SonicConst.PORT_SPLIT_NUM_4: {'1G': ['CR'],
                                              '10G': ['CR'],
                                              '25G': ['CR'],
                                              '40G': ['CR4'],
                                              '50G': ['CR2']
                                              },
                SonicConst.PORT_SPLIT_NUM_8: {'10G': ['CR'],
                                              '25G': ['CR']
                                              }
            }
        }
    }
    COPPER_TYPE_PREFIX = 'CR'
    OPTIC_TYPE_PREFIX = 'SR'


FEC_MODES_TO_ETHTOOL = {
    SonicConst.FEC_FC_MODE: "baser",
    SonicConst.FEC_RS_MODE: SonicConst.FEC_RS_MODE,
    SonicConst.FEC_NONE_MODE: "off",
    LinuxConsts.FEC_AUTO_MODE: LinuxConsts.FEC_AUTO_MODE
}


class P4SamplingEntryConsts:
    ENTRY_PRIORITY_HEADERS = ['PRIO']
    COUNTER_PACKETS_HEADERS = ['Packets']
    COUNTER_BYTES_HEADERS = ['Bytes']
    FLOW_ENTRY_KEY_HEADERS = ['Key SIP', 'Key DIP', 'Key PROTO', 'Key L4 SPORT', 'Key L4 DPORT',
                              'Key Checksum Value/Mask']
    PORT_ENTRY_KEY_HEADERS = ['Key Port', 'Key Checksum Value/Mask']
    FLOW_ENTRY_ACTION_HEADERS = [
        'Action',
        'Action Mirror Port',
        'Action SMAC',
        'Action DMAC',
        'Action SIP',
        'Action DIP',
        'Action VLAN',
        'Action Is Trunc',
        'Action Trunc Size']

    PORT_ENTRY_ACTION_HEADERS = [
        'Action',
        'Action Mirror Port',
        'Action SMAC',
        'Action DMAC',
        'Action SIP',
        'Action DIP',
        'Action VLAN',
        'Action Is Trunc',
        'Action Trunc Size']
    dutha1_ip = '10.0.0.1'
    duthb1_ip = '50.0.0.1'
    dutha2_ip = '10.0.1.1'
    duthb2_ip = '50.0.1.1'

    hadut1_ip = "10.0.0.2"
    hbdut1_ip = "50.0.0.2"
    hadut2_ip = '10.0.1.2'
    hbdut2_ip = '50.0.1.2'

    hadut1_network = "10.0.0.0"
    hbdut1_network = "50.0.0.0"
    hadut2_network = '10.0.0.0'
    hbdut2_network = '50.0.1.0'


class P4SamplingConsts:
    APP_NAME = 'p4-sampling'
    REPOSITORY = 'urm.nvidia.com/sw-nbu-sws-sonic-docker/p4-sampling'
    VERSION = '0.2.0-012'
    UPGRADE_TARGET_VERSION = '0.2.0-19'
    CONTTROL_IN_PORT = 'control_in_port'
    PORT_TABLE_NAME = 'table_port_sampling'
    FLOW_TABLE_NAME = 'table_flow_sampling'
    ACTION_NAME = 'DoMirror'
    TRAFFIC_INTERVAL = 0.2
    COUNTER_REFRESH_INTERVAL = 10


class LoganalyzerConsts:
    LOG_FILE_NAME = "syslog"


class P4ExamplesConsts:
    REPO_NAME = "urm.nvidia.com/sw-nbu-sws-sonic-docker/p4-examples"
    APP_NAME = 'p4-examples'
    APP_VERSION = '0.5.0'
    NO_EXAMPLE = "NO_EXAMPLE"
    VXLAN_BM_FEATURE_NAME = "VXLAN_BM"
    VXLAN_BM_ENCAP_TABLE = "p4-vxlan-bm-overlay-router"
    VXLAN_BM_DECAP_TABLE = "p4-vxlan-bm-tenant-forward"
    GTP_PARSER_TABLE = "p4-gtp"
    GTP_PARSER_P4NSPECT_TABLE = "match_gtpv1"
    GTP_PARSER_FEATURE_NAME = "GTP"


class SflowConsts:
    SFLOW_FEATURE_NAME = "sflow"
    DEFAULT_UDP = 6343
    UDP_1 = 6555
    COLLECTOR_0 = "collector0"
    COLLECTOR_1 = "collector1"
    COLLECTOR_F = "collector2"
    COLLECTOR = {
        COLLECTOR_0: {
            'name': COLLECTOR_0,
            'ip': '50.0.0.2',
            'ipv6': '5000::2',
            'port': DEFAULT_UDP,
            'sample_file': "/tmp/collector_0.json"
        },
        COLLECTOR_1: {
            'name': COLLECTOR_1,
            'ip': '60.0.0.2',
            'ipv6': '6000::2',
            'port': UDP_1,
            'sample_file': "/tmp/collector_1.json"
        },
        COLLECTOR_F: {
            'name': COLLECTOR_F,
            'ip': '70.1.1.2'
        }
    }

    LOOPBACK_0 = "Loopback0"
    LOOPBACK_0_IP = "1000:aaaa:bbbb:cccc:dddd:eeee:2000:3000"
    HSFLOWD_AUTOGEN_FILE = '/etc/hsflowd.auto'
    VRF_DEFAULT = "default"
    AGENT_ID_DEFAULT = "default"
    SFLOW_UP = "up"
    SFLOW_DOWN = "down"
    SFLOW_TOOL_PRETTY = "/usr/local/bin/sflowtool -J -p "
    POLLING_INTERVAL_DEVIATION_TOLERANCE = 2
    SAMPLE_RATE_1 = 500
    SAMPLE_RATE_2 = 300
    SAMPLE_RATE_3 = 1000
    SEND_PACKET_NUM = 1024

    DUT_HA_1_IP = "30.0.0.1"
    DUT_HA_2_IP = "40.0.0.1"
    HA_DUT_1_IP = "30.0.0.2"
    HA_DUT_2_IP = "40.0.0.2"

    DUT_HB_1_IP = "50.0.0.1"
    DUT_HB_2_IP = "60.0.0.1"
    DUT_HB_1_IP_V6 = "5000::1"
    DUT_HB_2_IP_V6 = "6000::1"
    HB_DUT_1_IP = "50.0.0.2"
    HB_DUT_2_IP = "60.0.0.2"
    HB_DUT_1_IP_V6 = "5000::2"
    HB_DUT_2_IP_V6 = "6000::2"
    COLLECTOR_0_IP = HB_DUT_1_IP
    COLLECTOR_1_IP = HB_DUT_2_IP
    COLLECTOR_0_IP_V6 = HB_DUT_1_IP_V6
    COLLECTOR_1_IP_V6 = HB_DUT_2_IP_V6
    COLLECTOR_LIST = [COLLECTOR_0, COLLECTOR_1]
    MGMT_INTF = 'eth0'
    POLLING_INTERVAL_0 = 0
    POLLING_INTERVAL_1 = 5
    POLLING_INTERVAL_2 = 10
    POLLING_INTF_0_WAIT_TIME = 10
    DUMMY_SOURCE_LOOPBACK_IP = "1.1.1.6"
    LOOPBACK_DEST_PORT_IP = "2.2.2.1"
    DUMMY_SOURCE_LOOPBACK_MAC = "00:11:22:33:44:55"


class CounterpollConstants:
    COUNTERPOLL_SHOW = 'sudo counterpoll show'
    COUNTERPOLL_DISABLE = 'sudo counterpoll {} disable'
    COUNTERPOLL_ENABLE = 'sudo counterpoll {} enable'
    COUNTERPOLL_RESTORE = 'sudo counterpoll {} {}'
    COUNTERPOLL_INTERVAL_STR = 'sudo counterpoll {} interval {}'
    COUNTERPOLL_QUEST = 'sudo counterpoll --help'
    EXCLUDE_COUNTER_SUB_COMMAND = ['show', 'config-db', "flowcnt-trap", "flowcnt-route", "tunnel"]
    INTERVAL = 'Interval (in ms)'
    TYPE = 'Type'
    STATUS = 'Status'
    STDOUT = 'stdout'
    PG_DROP = 'pg-drop'
    PG_DROP_STAT_TYPE = 'PG_DROP_STAT'
    QUEUE_STAT_TYPE = 'QUEUE_STAT'
    QUEUE = 'queue'
    PORT_STAT_TYPE = 'PORT_STAT'
    PORT = 'port'
    PORT_BUFFER_DROP_TYPE = 'PORT_BUFFER_DROP'
    PORT_BUFFER_DROP = 'port-buffer-drop'
    RIF_STAT_TYPE = 'RIF_STAT'
    RIF = 'rif'
    WATERMARK = 'watermark'
    QUEUE_WATERMARK_STAT_TYPE = 'QUEUE_WATERMARK_STAT'
    PG_WATERMARK_STAT_TYPE = 'PG_WATERMARK_STAT'
    BUFFER_POOL_WATERMARK_STAT_TYPE = 'BUFFER_POOL_WATERMARK_STAT'
    ACL = 'acl'
    ACL_TYPE = 'ACL'
    TUNNEL_STAT = 'tunnel'
    TUNNEL_STAT_TYPE = 'TUNNEL_STAT'
    FLOW_CNT_TRAP_STAT = 'flowcnt-trap'
    FLOW_CNT_TRAP_STAT_TYPE = 'FLOW_CNT_TRAP_STAT'
    FLOW_CNT_ROUTE_STAT = 'flowcnt-route'
    FLOW_CNT_ROUTE_STAT_TYPE = 'FLOW_CNT_ROUTE_STAT'

    COUNTERPOLL_MAPPING = {PG_DROP_STAT_TYPE: PG_DROP,
                           QUEUE_STAT_TYPE: QUEUE,
                           PORT_STAT_TYPE: PORT,
                           PORT_BUFFER_DROP_TYPE: PORT_BUFFER_DROP,
                           RIF_STAT_TYPE: RIF,
                           BUFFER_POOL_WATERMARK_STAT_TYPE: WATERMARK,
                           QUEUE_WATERMARK_STAT_TYPE: WATERMARK,
                           PG_WATERMARK_STAT_TYPE: WATERMARK,
                           ACL_TYPE: ACL,
                           TUNNEL_STAT_TYPE: TUNNEL_STAT,
                           FLOW_CNT_TRAP_STAT_TYPE: FLOW_CNT_TRAP_STAT,
                           FLOW_CNT_ROUTE_STAT_TYPE: FLOW_CNT_ROUTE_STAT}
    COUNTERPOLL_INTERVAL = {WATERMARK: 10000,
                            PORT: 10000,
                            RIF: 10000,
                            PG_DROP: 10000,
                            QUEUE: 10000,
                            PORT_BUFFER_DROP: 10000,
                            ACL: 10000,
                            TUNNEL_STAT: 10000}
    SX_SDK = 'sx_sdk'
    COUNTERPOLL_CPU_USAGE_THRESHOLD = 10
    WATERMARK_INTERVAL_1 = 10000
    WATERMARK_INTERVAL_DEFAULT = 60000

    CPU_THRESHOLD_FOR_ORDINARY_PROCESS = 50
    CPU_THRESHOLD_FOR_HIGH_CONSUME_PROCESS = 90
    MEMORY_THRESHOLD = 50
    MEMORY_THRESHOLD_ASAN = 90
    CPU_HIGH_CONSUME_PERSIST_TIME_THRESHOLD = 8

    CPU_MEMORY_SAMPLE_INTERVAL_1 = 5
    CPU_MEMORY_SAMPLE_ITERATION_1 = 24
    CPU_MEMORY_SAMPLE_INTERVAL_2 = 1
    CPU_MEMORY_SAMPLE_ITERATION_2 = 60


class AppExtensionInstallationConstants:
    WJH_APP_NAME = 'what-just-happened'
    WJH_REPOSITORY = 'harbor.mellanox.com/sonic-wjh/docker-wjh'
    LC_MANAGER = 'line-card-manager'
    DOAI = 'doai'
    LC_MANAGER_REPOSITORY = 'harbor.mellanox.com/sonic-lc-manager/line-card-manager'
    CMD_GET_SDK_VERSION = "docker exec -i {} bash -c 'sx_sdk --version'"
    SYNCD_DOCKER = 'syncd'
    APPLICATION_LIST = [
        P4SamplingConsts.APP_NAME,
        WJH_APP_NAME,
        LC_MANAGER,
        P4ExamplesConsts.APP_NAME,
        DOAI
    ]
    APP_EXTENSION_PROJECT_MAPPING = {'sonic-wjh': WJH_APP_NAME,
                                     'p4-sampling': P4SamplingConsts.APP_NAME,
                                     'sonic-lc-manager': LC_MANAGER,
                                     'p4-examples': P4ExamplesConsts.APP_NAME,
                                     'doai': DOAI}
    APPS_WHERE_SX_SDK_NOT_PRESENT = [P4SamplingConsts.APP_NAME, P4ExamplesConsts.APP_NAME, DOAI]


class MarsConstants:
    SONIC_MARS_BASE_PATH = "/.autodirect/sw_regression/system/SONIC/MARS"

    SONIC_MGMT_DEVICE_ID = "SONIC_MGMT"
    NGTS_PATH_PYTEST = "/ngts_venv/bin/pytest"
    NGTS_PATH_PYTHON = "/ngts_venv/bin/python"
    TEST_SERVER_DEVICE_ID = "TEST_SERVER"
    NGTS_DEVICE_ID = "NGTS"
    DUT_DEVICE_ID = "DUT"
    FANOUT_DEVICE_ID = "FANOUT"
    SONIC_MGMT_DIR = '/root/mars/workspace/sonic-mgmt/'
    UPDATED_FW_TAR_PATH = 'tests/platform_tests/fwutil/firmware.json'
    HTTP_SERVER_NBU_NFS = 'http://nbu-mtr-nfs.nvidia.com'

    DOCKER_SONIC_MGMT_IMAGE_NAME = "docker-sonic-mgmt"
    DOCKER_NGTS_IMAGE_NAME = "docker-ngts"

    SONIC_MGMT_REPO_URL = "http://10.7.77.140:8080/switchx/sonic/sonic-mgmt"
    SONIC_MGMT_MOUNTPOINTS = {
        '/.autodirect/mswg/projects': '/.autodirect/mswg/projects',
        '/auto/sw_system_project': '/auto/sw_system_project',
        '/auto/sw_system_release': '/auto/sw_system_release',
        '/.autodirect/sw_system_release/': '/.autodirect/sw_system_release/',
        '/auto/sw_regression/system/SONIC': '/auto/sw_regression/system/SONIC/',
        '/.autodirect/sw_regression/system/SONIC': '/.autodirect/sw_regression/system/SONIC',
        '/workspace': '/workspace',
        '/.autodirect/LIT/SCRIPTS': '/.autodirect/LIT/SCRIPTS',
        '/.autodirect/sw/release/': '/.autodirect/sw/release/'
    }

    VER_SDK_PATH = "/opt/ver_sdk"
    EXTRA_PACKAGE_PATH_LIST = ["/usr/lib64/python2.7/site-packages"]

    TOPO_ARRAY = ("t0-56-po2vlan", "t0", "t1-lag", "t1-28-lag", "ptf32",
                  "t0-64", "t1-64-lag", "t0-56", "t0-56-o8v48", "t0-120", "t1-56-lag", "t0-28")
    TOPO_ARRAY_DUALTOR = ("dualtor", "dualtor-64", "dualtor-aa")
    REBOOT_TYPES = {
        "reboot": "reboot",
        "fast-reboot": "fast-reboot",
        "warm-reboot": "warm-reboot"
    }

    DOCKER_REGISTRY = "harbor.mellanox.com/sonic"

    DUT_LOG_BACKUP_PATH = "/.autodirect/sw_system_project/sonic/dut_logs"

    BRANCH_PTF_MAPPING = {'master': '558858',
                          '202012': '42007',
                          '202106': '42007'
                          }


class PlayersAliases:
    Aliases_list = ['sl']
    SL = 'sl'
    duts_list = ['dut', 'dut-b', 'dut-dpu-1', 'dut-dpu-2', 'dut-dpu-3', 'dut-dpu-4', 'left_tg', 'right_tg']


class NvosCliTypes:
    NvueCliTypes = ["NVUE", "MLNX_OS"]
    CumulusCliType = "CUMULUS_SWITCH"


class BluefieldConstants:
    BMC_USER = os.getenv("BMC_USER")
    BMC_PASS = os.getenv("BMC_PASSWORD")

    PXE_SERVER = 'r-fit16-clone'
    PXE_SERVER_CONFIGS_PATH = '/tftpboot/uefiboot/grub/'
    BF2_HWSKU = 'Nvidia-MBF2H536C'
    BF3_HWSKU = 'Nvidia-9009d3b600CVAA'
    BF2_GRUB_CFG = 'bluefield-2.grub.cfg'
    BF3_GRUB_CFG = 'bluefield-3.grub.cfg'
    GRUB_CFG_FILE_MAP = {BF2_HWSKU: BF2_GRUB_CFG, BF3_HWSKU: BF3_GRUB_CFG}

    BLUEFIELD_HWSKUS_LIST = [BF2_HWSKU, '{}-C2'.format(BF2_HWSKU),
                             "Nvidia-9009d3b600CVAA",
                             "Nvidia-9009d3b600CVAA-C1",
                             "Nvidia-9009d3b600CVAA-C2",
                             "Nvidia-9009d3b600SVAA",
                             "Nvidia-9009d3b600SVAA-C1",
                             "Nvidia-9009d3b600SVAA-C2"]
    BLUEFIELD_PORTS_LIST = ['Ethernet0', 'Ethernet4']


class PerformanceSetupConstants:
    HWSKU = 'Mellanox-SN5600-O128'


class SonicDeployConstants:
    UN_SUPPORT_BRANCH_MAP = {"r-alligator-04": ["201911", "202012"]}


class RebootTestConstants:
    DATAPLANE_TRAFFIC_RESULTS_FILE = '/tmp/reboot_dataplane_result.json'
    CONTROLPLANE_TRAFFIC_RESULTS_FILE = '/tmp/reboot_controlplane_result.json'
    IFACES_STATUS_FILE = '/tmp/reboot_ifaces_status.json'


class VxlanConstants:
    HOST_HA = 'ha'
    HOST_HB = 'hb'
    PACKET_NUM_500 = 500
    PACKET_NUM_400 = 400
    PACKET_NUM_200 = 200
    PACKET_NUM_100 = 100
    PACKET_NUM_10 = 10
    PACKET_NUM_3 = 3
    PACKET_NUM_0 = 0
    STATIC_MAC_OPERATION_SET = 'SET'
    STATIC_MAC_OPERATION_DEL = 'DEL'
    MTU_1500 = '1500'
    MTU_9100 = '9100'
    MTU_1000 = '1000'
    JUMBO_PACKET_LEN = 9000
    NORMAL_PACKET_LEN = 1000
    PCAP_PATH = '/tmp/evpn_ecmp_{}.pcap'
    INTF_CNT_STAT_ITEMS = ['RX_DRP', 'RX_ERR', 'RX_OK', 'RX_OVR', 'TX_DRP', 'TX_ERR', 'TX_OK', 'TX_OVR']

    DUT_VNI_INTF_ADDRESS_TEMPLATE = '200.{}.0.1'
    VM_VNI_INTF_ADDRESS_TEMPLATE = '200.{}.0.2'
    BR_500100_IP = '100.0.0.2'
    BR_500200_IP = '200.0.0.2'
    IP_GENERATE_SEED = 201

    VETH_NAME_1 = 'tap_3333_1'
    VETH_PEER_NAME_1 = 'tap_3333_2'
    VETH_NAME_100 = 'tap_100_1'
    VETH_PEER_NAME_100 = 'tap_100_2'
    VETH_NAME_101 = 'tap_101_1'
    VETH_PEER_NAME_101 = 'tap_101_2'
    NAME_SPACE_1 = 'ns1'
    NAME_SPACE_100 = 'ns100'
    NAME_SPACE_101 = 'ns101'
    VETH_IP = '3.3.3.10'
    VETH_IP_ADDR_1 = '100.0.0.200'
    DST_IP_101_0_0_3 = '101.0.0.3'
    UNKNOWN_SRC_IP = '1.0.0.3'
    UNKNOWN_DST_IP = '101.0.0.100'

    BGP_SESSION_ID = 65000
    PREFIX_LENGTH = 24
    EVPN_ROUTE_MAP = 'EVPN-OUT'
    DENY = 'deny'
    PERMIT = 'permit'
    RD_20 = '20'
    RD_100 = '100'
    RD_101 = '101'
    RD_200 = '200'
    RD_3333 = '3333'
    VLAN_3 = 3
    VLAN_10 = 10
    VLAN_20 = 20
    VLAN_100 = 100
    VLAN_101 = 101
    VLAN_200 = 200
    VNI_12345 = 12345
    VNI_54321 = 54321
    VNI_50020 = 50020
    VNI_500100 = 500100
    VNI_500101 = 500101
    VNI_500200 = 500200
    VNI_3333 = 3333
    VNI_3333_IFACE = 'br_{}'.format(VNI_3333)
    HA_VXLAN_54321_IFACE = 'vtep_{}'.format(VNI_54321)
    VNI_50020_IFACE = 'br_{}'.format(VNI_50020)
    VNI_500100_IFACE = 'br_{}'.format(VNI_500100)
    VNI_500101_IFACE = 'br_{}'.format(VNI_500101)
    VNI_500200_IFACE = 'br_{}'.format(VNI_500200)

    EVPN_NVO = 'my-nvo'
    VTEP_NAME_DUT = 'vtep101032'
    VTEP_INTERFACE = 'Loopback0'
    SIMPLE_PACKET = 'Ether(src="{}",dst="{}")/IP(src="{}",dst="{}")/UDP()'
    SIMPLE_DOT1Q_PACKET = 'Ether(src="{}",dst="{}")/Dot1Q(vlan={})/IP(src="{}",dst="{}")/UDP()'
    ECMP_SIMPLE_PACKET = 'Ether(src="{}",dst="{}")/IP(src={},dst="{}")/UDP()'
    ECMP_SIMPLE_PACKET_V6 = 'Ether(src="{}",dst="{}")/IPv6(src={},dst="{}")/UDP()'
    ECMP_VARIABLE_LENGTH_PACKET = 'Ether(src="{}",dst="{}")/IP(src={},dst="{}")/UDP()/Raw(RandString(size={}))'
    ECMP_VARIABLE_LENGTH_PACKET_V6 = \
        'Ether(src="{}",dst="{}")/IPv6(src={},dst="{}")/UDP()/Raw(RandString(size={}))'
    SIMPLE_PACKET_FILTER = 'udp and dst host {}'
    # filter VXLAN packet with vni and encapsulated src IP
    TCPDUMP_VXLAN_SRC_IP_FILTER = 'port 4789 and ether[46:4]={} and ether[76:4]={}'
    # filter VXLAN packet with vni and encapsulated dst IP
    TCPDUMP_VXLAN_DST_IP_FILTER = 'port 4789 and ether[46:4]={} and ether[80:4]={}'
    TCPDUMP_VXLAN_DST_IPV6_FILTER = 'port 4789 and ether[46:4]={} and ether[88:4]={}'
    HEX_UNKNOWN_SRC_IP = '0x01000003'
    HEX_5_5_5_1 = '0x05050501'
    HEX_20_0_0_3 = '0x14000003'  # hex value for 20.0.0.3
    HEX_100_0_0_2 = '0x64000002'  # hex value for 100.0.0.2
    HEX_100_0_0_3 = '0x64000003'  # hex value for 100.0.0.3
    HEX_101_0_0_2 = '0x65000002'  # hex value for 101.0.0.2
    HEX_101_0_0_3 = '0x65000003'  # hex value for 101.0.0.3
    HEX_200_0_0_2 = '0xc8000002'  # hex value for 200.0.0.2
    HEX_255_255_255_255 = '0xffffffff'  # hex value for 255.255.255.255
    HEX_5000_2 = '0x50000000'  # hex value for 5000::2, scapy only support 4 byte size data matching
    HEX_500100 = '0x7a18400'
    HEX_500101 = '0x7a18500'
    HEX_500200 = '0x7a1e800'
    IP_HEX_MAP = {BR_500100_IP: HEX_100_0_0_2, BR_500200_IP: HEX_200_0_0_2}
    VNI_HEX_MAP = {VNI_500100: HEX_500100, VNI_500200: HEX_500200}
    STATIC_MAC_ADDR = '00-00-00-11-22-33'
    SOURCE_MAC_ADDR_1 = '00:11:22:33:44:55'
    UNKNOWN_UNICAST_MAC = '00:00:00:00:00:aa'
    UNKNOWN_UNICAST_MAC_1 = '00:00:00:99:99:99'
    BROADCAST_MAC = 'ff:ff:ff:ff:ff:ff'
    BROADCAST_IP = '255.255.255.255'
    ECMP_TRAFFIC_SRC_IP_LIST = ['3.3.3.3', '3.3.3.4', '3.3.3.5', '3.3.3.6']
    ECMP_TRAFFIC_SRC_IPV6_LIST = ['2000::3', '2000::4', '2000::5', '2000::6']
    BULK_ECMP_TRAFFIC_SRC_IP_LIST = eval("['3.3.3.' + str(i+1) for i in range(100)]")
    BULK_ECMP_TRAFFIC_SRC_IPV6_LIST = eval("['2000::' + str(i+1) for i in range(100)]")


class SanitizerConst:
    SENDER_MAIL = 'noreply@sanitizer.com'
    ASAN_APPS = ["what-just-happened"]

    NVOS_MAIL = 'nbu-system-sw-mlnxos20-ext@exchange.nvidia.com'
    SONIC_MAIL = "nbu-system-sw-sonic-ver@exchange.nvidia.com"
    CLI_TYPE_MAIL = \
        {"MLNX_OS": NVOS_MAIL,
         "NVUE": NVOS_MAIL,
         "Sonic": SONIC_MAIL}


class ResultUploaderConst:
    SONIC_CANONICAL_NOGA_GROUP = "SONiC_Canonical"
    SONIC_COMMUNITY_NOGA_GROUP = "SONiC_Community"
    SONIC_NOGA_GROUPS = [SONIC_CANONICAL_NOGA_GROUP, SONIC_COMMUNITY_NOGA_GROUP]
    XLSX_HEADER = ["session_id", "mars_key_id", "testbed", "test name", "start", "end", "result", "message",
                   "topology", "host", "asic", "platform", "hwsku", "os_version", "xml_path",
                   "was_xml_updated", "modify_xml", "sanitized_testname"]
    MSFT_XLSX_HEADER = ["testbed", "test name", "start", "end", "result", "message",
                        "topology", "host", "asic", "platform", "hwsku",
                        "os_version", "xml_path", "sanitized_testname"]
    SANITIZED_HOSTNAME = "switch-hostname"
    REMOVE_FAILED_TESTCASE = "REMOVE_FAILED_TESTCASE"
    DATABASE_NAME = "NvidiaTestData"
    UPLOADER_SCRIPT_RELATIVE_PATH = "test_reporting/report_uploader.py"
    COMMUNITY_DBS_RELATIVE_PATH = "sonic-tool/mars/dbs/community"
    MSFT_PLATFORMS = ["4600C", "4700", "2700", "3800"]
    MARS_RELEASE = "/auto/sw_tools/Internal/MARS/mars_apps/RELEASE/4_3_3/bin/"
    QUERY_SESSIONS_SCRIPT = os.path.join(MARS_RELEASE, "save_delete_sessions_query.py")
    SAVE_SESSIONS_SCRIPT = os.path.join(MARS_RELEASE, "save_delete_sessions.py")
    SESSION_STARTED_BY_REGEX = ["mars_orch_sw-mars-orch@friday_canonical_full_regression_main_branch",
                                "mars_orch_sw-mars-orch@canonical_full_regression_main_branch",
                                "mars_orch_sw-mars-orch@Comex_Friday_Set",
                                "mars_orch_sw-mars-orch@Community_Comex_Regression",
                                "mars_orch_sw-mars-orch@Community_Regression_Dual_Tor",
                                "mars_orch_sw-mars-orch@Community_Regression",
                                "mars_orch_sw-mars-orch@Friday_Community_Regression"]
    HOST_INTERNAL_NAMES_LIST = ["boxer", "bulldog", "spider", "panther",
                                "lionfish", "anaconda", "tigris", "ocelot",
                                "liger", "tigon", "leopard", "moose"]


class BugHandlerConst:
    NGTS_PATH, path_suffix = os.path.abspath(__file__).split('constants/')
    CLI_TYPE_REDMINE_PROJECT = \
        {"MLNX_OS": "mlnxOS-Eth",
         "NVUE": "'NVOS - Design'",
         "Sonic": "SONiC-Design"}
    BUG_HANDLER_CONF_FILE = {"SONiC-Design": os.path.join(NGTS_PATH, "helpers/bug_handler/sonic_bug_handler.conf"),
                             "'NVOS - Design'": "nvos_design.cfg"}
    BUG_HANDLER_PYTHON_PATH = "/mswg/projects/swvt/MARS/scripts/python37_wrapper.sh"
    BUG_HANDLER_PATH = "/auto/sw_tools/Internal/BugHandling/RELEASES/1_2_1/bin/"
    BUG_HANDLER_SCRIPT = BUG_HANDLER_PATH + "handle_bug.py"
    BUG_HANDLER_UPLOAD_ATTACHMENT_SCRIPT = BUG_HANDLER_PATH + "upload_attachment_to_bug.py"
    BUG_HANDLER_SANITIZER_USER = "asan"
    BUG_HANDLER_LOG_ANALYZER_USER = "log_analyzer"
    SANITIZER_PARSED_DUMPS_FOLDER = "/tmp/parsed_sanitizer_dumps/"
    BUG_HANDLER_DECISION_UPDATE = "update"
    BUG_HANDLER_DECISION_SKIP = "skip"
    BUG_HANDLER_DECISION_CREATE = "create"
    BUG_HANDLER_DECISION_ABORT = "abort"
    BUG_HANDLER_DECISION_REOPEN = "reopen"
    NO_ACTION_MODE = "no action"
    UPDATE_ONLY = "update only"
    RC_ABORT = 2
    DECISION = "decision"
    NEW_BUGS = "new_bugs"
    EXISTING_BUGS = "existing_bugs"
    UPDATE_BUG = "update_bug"
    SKIP_UPDATE_BUG = "skip_update_bug"
    LA_ERROR = "la_error"
    BUG_HANDLER_FAILURE = "bug_handler_failure"
    LOG_ERRORS_DIR_PATH = "/tmp/loganalyzer/{hostname}"
    BUG_HANDLER_RC = "rc"
    BUG_HANDLER_STATUS = "status"
    BUG_HANDLER_ACTION = "action"
    BUG_HANDLER_BUG_ID = "bug_id"
    BUG_HANDLER_MESSAGES = "messages"
    LA_RM_ISSUES_DICT = "la_rm_issues_dict"
    BUG_HANDLER_FAILURE_EXCEPTION = "The log analyzer bug handler has failed"
    BUG_HANDLER_SUCCESS_ACTIONS_LIST = [BUG_HANDLER_DECISION_CREATE, BUG_HANDLER_DECISION_UPDATE,
                                        BUG_HANDLER_DECISION_SKIP]
    BUG_TITLE_LIMIT = 230
    BUG_HANDLER_SKIP_BRNACH = ['202305']


class SerialLoggerConst:
    LOG_DIR = os.path.join(os.path.sep, ".autodirect", "sw_regression", "system", "NVOS", "MARS", "results",
                           "{setup_name}", "{session_id}", "serial_logs")
    # CLEAN_DIRS_SCRIPT = os.sep.join([os.environ['REGRESSION_BASE_DIR'],
    #                                  'sx_fit_regression',
    #                                  'libs',
    #                                  'scripts',
    #                                  'clean_unmodified_dirs_and_files'])
    UNMODIFIED_FILES_DAYS_TH = 14
    ALL_PERM = 0o777
    DATETIME_FORMAT = "%b %d %H:%M:%S"
    START_SERIAL_LOGGING = "Start Session Logging"


class DebugKernelConsts:
    KMEMLEAK_PATH = '/sys/kernel/debug/kmemleak'
    KMEMLEAK = 'kmemleak'


class GnmiConsts:
    GNMI_DOCKER = 'gnmi-server'
    GNMI_STATE_FIELD = 'state'
    GNMI_STATE_ENABLED = 'enabled'
    GNMI_STATE_DISABLED = 'disabled'
    GNMI_IS_RUNNING_FIELD = 'is-running'
    GNMI_IS_RUNNING = 'yes'
    GNMI_IS_NOT_RUNNING = 'no'
    GNMI_VERSION_FIELD = 'version'
    GNMI_DEFAULT_PORT = '9339'
    SLEEP_TIME_FOR_UPDATE = 35
    REDIS_CMD_KEY = 'redis_cmd'
    XPATH_KEY = 'xpath_gnmi_cmd'
    COMPARISON_KEY = 'comparison_dict'
    REDIS_CMD_DB_NAME = "redis_cmd_db_num"
    REDIS_CMD_TABLE_NAME = "redis_cmd_table"
    REDIS_CMD_PARAM = "redis_cmd_param"


class CableComplianceConst:
    EXTENDED_SPEC_COMPLIANCE_PREFIX = "Extended Specification Compliance"
    SPEC_COMPLIANCE_PREFIX = "Specification compliance"
    SFP_COMPLIANCE = "SFP+CableTechnology"
    UNDETECTED_EEPROM_MSG = "SFP EEPROM Not detected"
    UNDETECTED_RJ45_EEPROM_MSG = "SFP EEPROM is not applicable for RJ45 port"
    SUPPORTED_CABLE_DEFAULT = "Cable Always Supports Auto-Neg"
    DEFAULT_CABLE_COMPLIANCE_TUPLE = (SUPPORTED_CABLE_DEFAULT, SUPPORTED_CABLE_DEFAULT)
    SUPPORTED_SPECIFICATION_COMPLIANCE = {SPEC_COMPLIANCE_PREFIX: ["passive_copper_media_interface"],
                                          SFP_COMPLIANCE: ["Passive Cable"],
                                          # This following regex will match the pattern iff it
                                          # contains a iGBASE-?R and for each iGBASE-?R, ?=C
                                          EXTENDED_SPEC_COMPLIANCE_PREFIX: [r"^(?=.*\d+GBASE-CR)(?!\d+GBASE-[^C]R).*$"],
                                          SUPPORTED_CABLE_DEFAULT: [".*"]  # which match anything
                                          }
    UNSUPPORTED_SPECIFICATION_COMPLIANCE = {
        SPEC_COMPLIANCE_PREFIX: ["active_cable_media_interface", "sm_media_interface",
                                 "nm_850_media_interface"],
        EXTENDED_SPEC_COMPLIANCE_PREFIX: [r"\d+GBASE-DR", r"\d+GBASE-SR", r"AOC", r"Active Optical Cable"]}


class IndependentModuleConst:
    IM_SAI_ATTRIBUTE_NAME = "SAI_INDEPENDENT_MODULE_MODE"
    IM_CONTROL_FILE_PATH = "/sys/module/sx_core/asic0/module{PORT_NUMBER}/control"
    MEDIA_SETTINGS_FILE_NAME = "media_settings.json"
    OPTICS_SI_SETTINGS_FILE_NAME = "optics_si_settings.json"
    IM_INTERFACE_SETTINGS_FILE_PATH = "/usr/share/sonic/device/{PLATFORM}"
    MS_HWSKU = ['Mellanox-SN4700-O8C48', 'Mellanox-SN4700-O8V48', 'ACS-SN5600', 'ACS-MSN4700']
    DUTS_SUPPORTING_IM = ['r-leopard-32', 'r-leopard-41', 'r-leopard-56', 'r-leopard-01', 'r-leopard-58',
                          'r-leopard-70', 'r-leopard-72', 'r-moose-01', 'r-moose-02', 'mtvr-moose-04']


class PerfConsts:
    CONFIG_FILES_DIR = os.path.join(BugHandlerConst.NGTS_PATH, 'tests/performance/config_files')
    LEFT_TG_ALIAS = "left_tg"
    RIGHT_TG_ALIAS = "right_tg"
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
    PACKET_SIZE_LIST = [1500, 2000, 4000, 8000]
    PACKET_SIZE_TO_PACKET_NUM_DICT = {1500: 32, 2000: 16, 4000: 8, 8000: 8}
    TG_TX_UTIL_TH = 95
    DUT_TX_UTIL_TH_DICT = {1500: 64, 2000: 80, 4000: 92, 8000: 93}
    DUT_TX_UTIL_W_IBM_TH_DICT = {1500: 64, 2000: 80, 4000: 96, 8000: 95}
    EXPECTED_EGRESS_PORTS = 64
    EXPECTED_MLOOP_PORTS = 64
    EXPECTED_AR_PORTS = 128
    EXPECTED_PORTS_BY_TYPE = {"egress": EXPECTED_EGRESS_PORTS,
                              "mloop": EXPECTED_MLOOP_PORTS,
                              "ar": EXPECTED_AR_PORTS}
    VALUE_INDEX = 0
    TIMESTAMP_INDEX = 1
    LOG_PORT_LEFT_TG = 0x10001
    LOG_PORT_RIGHT_TG = 0x10081
    LOG_PORTS_DICT = {LEFT_TG_ALIAS: LOG_PORT_LEFT_TG, RIGHT_TG_ALIAS: LOG_PORT_RIGHT_TG}
    L_IP_NEIGH = "10.10.10.10"
    R_IP_NEIGH = "20.20.20.20"
    PERF_SUPPORTED_REBOOT_TYPES = ['reboot', 'config reload -y']
    SLEEP_TIME_BEFORE_SAMPLE = 15


SETUPS_WITH_NON_DEFAULT_PTF = ['r-panther-40', 'r-panther-42', 'r-bobcat-01']

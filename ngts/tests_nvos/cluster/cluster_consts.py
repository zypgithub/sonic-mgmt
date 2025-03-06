from ngts.nvos_constants.constants_nvos import ClusterAppsLogLevels, NvosConst
import re


class ClusterConsts:
    NMX_CONTROLLER = 'nmx-controller'
    NMX_TELEMETRY = 'nmx-telemetry'
    INITIAL_EXPECTED_APPS = [NMX_CONTROLLER, NMX_TELEMETRY]
    START_APP_WHILE_CLUSTER_DISABLED_ERR_MSG = 'Output was expected to contain:\nAction succeeded\nBut the output is:\nAction executing ...\nError: Action failed with the following issue:\n  cluster is not enabled'
    TELEMETRY_SERVICES = ['nmx-telemetry']
    CONTROLLER_SERVICES = ['nmxc-rel', 'redis']
    ClusterAppsLogLevelsList = [ClusterAppsLogLevels.DEBUG, ClusterAppsLogLevels.INFO, ClusterAppsLogLevels.NOTICE, ClusterAppsLogLevels.WARNING, ClusterAppsLogLevels.ERROR, ClusterAppsLogLevels.CRITICAL]
    NMX_CONTROLLER_CONFIG_FILE_TYPES = ['fm_config', 'sm_config', 'rdm_config', 'chassis_mapping']
    NMX_CONTROLLER_STATE_FILE_TYPES = ['topology']
    NMX_TELEMETRY_CONFIG_FILE_TYPES = ['telemetry']  # Once added make sure to adjust CONFIG_FILES_CHANGE
    NMX_TELEMETRY_STATE_FILE_TYPES = []
    CONTROLLER_AND_TELEMETRY_CONFIG_FILES = NMX_CONTROLLER_CONFIG_FILE_TYPES + NMX_TELEMETRY_CONFIG_FILE_TYPES
    CONTROLLER_AND_TELEMETRY_STATE_FILES = NMX_CONTROLLER_STATE_FILE_TYPES + NMX_TELEMETRY_STATE_FILE_TYPES
    MAP_CONFIG_FILE_TYPE_TO_APP = {}
    MAP_CONFIG_FILE_TYPE_TO_APP.update({file_type: 'nmx-controller' for file_type in ['fm_config', 'sm_config', 'rdm_config', 'chassis_mapping']})
    MAP_CONFIG_FILE_TYPE_TO_APP.update({file_type: 'nmx-telemetry' for file_type in ['telemetry']})
    MAP_STATE_FILE_TYPE_TO_APP = {}
    MAP_STATE_FILE_TYPE_TO_APP.update({file_type: 'nmx-controller' for file_type in ['topology']})
    MAP_STATE_FILE_TYPE_TO_APP.update({file_type: 'nmx-telemetry' for file_type in []})
    NMX_LOG_MESSAGES_TAGS = ['nmxc-sm', 'nmxc-fm', 'nmxc-fib', 'nmxc-gw_api', 'nmxc-rest', 'nmxc-config_daemon']
    INITIAL_CONFIGURATIONS_PATH = '/auto/sw_system_project/NVOS_INFRA/verification_files/cluster/uploaded_control_plane_files'
    UNDEFINED_STATE = 'undefined'
    UNDEFINED_STATE_ERR_MSG_NVUE = 'Error: At state: \'undefined\' is not one of ["enabled", "disabled"]'
    UNDEFINED_STATE_ERR_MSG_OPENAPI = 'Error: Request failed. Details: Error: \'undefined\' is not one of [\'enabled\', \'disabled\', None]'
    UNDEFINED_STATE_DICT = {'NVUE': UNDEFINED_STATE_ERR_MSG_NVUE, 'OpenApi': UNDEFINED_STATE_ERR_MSG_OPENAPI}
    RESET_FACTORY_CLUSTER_DISABLED_NVUE = 'Error: Action failed with the following issue:\n  cluster is not enabled'

    RESET_FACTORY_NMX_CONN_DISABLED_NVUE = 'Error: Action failed with the following issue:\n  gRPC connection is down'

    RESET_FACTORY_CLUSTER_DISABLED_OPENAPI = 'action_error: cluster is not enabled'

    RESET_FACTORY_NMX_CONN_DISABLED_OPENAPI = 'action_error: gRPC connection is down'

    RESET_FACTORY_CLUSTER_DISABLED = {'NVUE': RESET_FACTORY_CLUSTER_DISABLED_NVUE, 'OpenApi': RESET_FACTORY_CLUSTER_DISABLED_OPENAPI}
    RESET_FACTORY_NMX_CONN_DISABLED = {'NVUE': RESET_FACTORY_NMX_CONN_DISABLED_NVUE, 'OpenApi': RESET_FACTORY_NMX_CONN_DISABLED_OPENAPI}

    NMXC_CONN = 'nmxc-conn'
    NMXC_CONN_STATE_PER_CLUSTER_STATE = {NvosConst.ENABLED: 'up', NvosConst.DISABLED: 'down'}
    WAIT_FOR_APPS_RUNNING = 50  # Reduce to 15 once bug is fixed [NVOS - Design] Bug SW #4099507: [Non-Functional ] [NVL5 - JULIET - NMX] | nmxc-conn takes too long to be in "up" state | Assignee: Or Farfara | Status: Opened on other team
    UNDEFINED_STATE_ERR_MSG = 'Error: At state: \'undefined\' is not one of [\'enabled\', \'disabled\']'
    DEFAULT_LOG_LEVEL = 'notice'
    UNDEFINED_LOG_LEVEL = "'undefined' is not one of ['critical', 'error', 'warn', 'notice', 'info', 'debug']"
    SLEEP_AFTER_LOG_ROTATE = 20
    PARTITIONS_NAMES = ['test_partition1', 'test_partition2', 'test_partition3']
    RESILIENCY_MODES = ['adaptive_bandwidth', 'full_bandwidth', 'user_action']
    CONFIDENTIAL_COMPUTE = [True, False]
    DEFAULT_PARTITION = 1
    APP_VERSION = 'app-ver'
    APP_NAME = 'app-name'
    NMX_CONTROLLER_PREFIX = 'nmx-c'
    NMX_TELEMETRY_PREFIX = 'nmx-t'
    INITIAL_APPS_PATH = '/usr/local/cluster_pkgfiles/'
    INFRA_PACKAGES_PATH = '/host/cluster_infra/packages/'
    CONFIG_FILES_CHANGE = {'sm_config': "sudo sed -i \"/^max_op_vls /c\\max_op_vls 2\" {file_path}",
                           'fm_config': "sudo sed -i \"/^LOG_FILE_MAX_SIZE=/c\\LOG_FILE_MAX_SIZE=1023\" {file_path}",
                           'rdm_config': "true",
                           'chassis_mapping': "true",
                           'telemetry': "true"}
    EXPECTED_LINE_TO_BE_PRESERVED_AFTER_UPGRADE = {'sm_config': "max_op_vls 2",
                                                   'fm_config': "LOG_FILE_MAX_SIZE=1023",
                                                   'rdm_config': "",
                                                   'chassis_mapping': "",
                                                   'telemetry': ""}
    CONFIG_FILES_CONTENT_CHANGE = {
        'sm_config': lambda content: re.sub(r'^max_op_vls.*$', 'max_op_vls 2', content, flags=re.MULTILINE),
        'fm_config': lambda content: re.sub(r'^LOG_FILE_MAX_SIZE=.*$', 'LOG_FILE_MAX_SIZE=1023', content, flags=re.MULTILINE),
        'rdm_config': lambda content: content,
        'chassis_mapping': lambda content: content,
        'telemetry': lambda content: content
    }
    NMX_CONTROLLER_CONFIG_CHASSIS_MAPPING = 'chassis_mapping'
    PARTITION_TYPES = ['location_based', 'gpuuid_based']
    EMPTY_PARTITION_ID = '10'
    EMPTY_PARTITION_NAME = "empty_partition"
    CREATED_PARTITION_NAME = "user_partition"
    MIN_MCAST = 0
    MAX_MCAST = 0  # Change to 1024 once bug is closed.
    PROTOCOL_RSYSLOG = "rsyslog"
    PROTOCOL_ELK = "elk"
    PROTOCOL_SPLUNK = "splunk"
    # NMXC_LOG_STREAM_PROTOCOLS = [PROTOCOL_RSYSLOG, PROTOCOL_ELK, PROTOCOL_SPLUNK]
    NMXC_LOG_STREAM_PROTOCOLS = [PROTOCOL_RSYSLOG]
    NMXC_LOG_STREAM_DEFAULT_PORT = "514"

from ngts.nvos_constants.constants_nvos import ClusterAppsLogLevels, NvosConst


class ClusterConsts:
    NMX_CONTROLLER = 'nmx-controller'
    NMX_TELEMETRY = 'nmx-telemetry'
    INITIAL_EXPECTED_APPS = [NMX_CONTROLLER, NMX_TELEMETRY]
    START_APP_WHILE_CLUSTER_DISABLED_ERR_MSG = 'Output was expected to contain:\nAction succeeded\nBut the output is:\nAction executing ...\nError: Action failed with the following issue:\n  cluster is not enabled'
    TELEMETRY_SERVICES = ['nmx-connector', 'ib-telemetry', 'nmx-syslog-aggregator']
    CONTROLLER_SERVICES = ['nmxc-sdn', 'nmxc-fib', 'redis']
    ClusterAppsLogLevelsList = [ClusterAppsLogLevels.DEBUG, ClusterAppsLogLevels.INFO, ClusterAppsLogLevels.NOTICE, ClusterAppsLogLevels.WARNING, ClusterAppsLogLevels.ERROR, ClusterAppsLogLevels.CRITICAL]
    NMX_CONTROLLER_CONFIG_FILE_TYPES = ['fm_config', 'sm_config', 'rdm_config', 'chassis_mapping']
    NMX_CONTROLLER_STATE_FILE_TYPES = ['sm_dump', 'topology']
    NMX_LOG_MESSAGES_TAGS = ['nmxc-sm', 'nmxc-fm', 'nmxc-fib', 'nmxc-gw_api', 'nmxc-rest', 'nmxc-config_daemon']
    INITIAL_CONFIGURATIONS_PATH = '/auto/sw_system_project/NVOS_INFRA/verification_files/cluster/uploaded_control_plane_files'
    UNDEFINED_STATE = 'undefined'
    UNDEFINED_STATE_ERR_MSG_NVUE = 'Error: At state: \'undefined\' is not one of [\'enabled\', \'disabled\']'
    UNDEFINED_STATE_ERR_MSG_OPENAPI = 'Error: Request failed. Details: Error: \'undefined\' is not one of [\'enabled\', \'disabled\', None]'
    UNDEFINED_STATE_DICT = {'NVUE': UNDEFINED_STATE_ERR_MSG_NVUE, 'OpenApi': UNDEFINED_STATE_ERR_MSG_OPENAPI}
    NMXC_CONN = 'nmxc-conn'
    NMXC_CONN_STATE_PER_CLUSTER_STATE = {NvosConst.ENABLED: 'up', NvosConst.DISABLED: 'down'}
    WAIT_FOR_APPS_RUNNING = 70  # Reduce to 15 once bug is fixed [NVOS - Design] Bug SW #4099507: [Non-Functional ] [NVL5 - JULIET - NMX] | nmxc-conn takes too long to be in "up" state | Assignee: Or Farfara | Status: Opened on other team
    UNDEFINED_STATE_ERR_MSG = 'Error: At state: \'undefined\' is not one of [\'enabled\', \'disabled\']'
    DEFAULT_LOG_LEVEL = 'notice'
    UNDEFINED_LOG_LEVEL = '''Output was expected to contain:
    Action succeeded
    But the output is:
    Error: 'undefined' is not one of ['critical', 'error', 'warn', 'notice', 'info', 'debug', None]'''
    SLEEP_AFTER_LOG_ROTATE = 20
    PARTITIONS_NAMES = ['test_partition1', 'test_partition2', 'test_partition3']
    RESILIENCY_MODES = ['ADAPTIVE_BANDWIDTH', 'FULL_BANDWIDTH', 'USER_ACTION']
    CONFIDENTIAL_COMPUTE = [True, False]
    DEFAULT_PARTITION = 1
    APP_VERSION = 'app-ver'
    APP_NAME = 'app-name'
    NMX_CONTROLLER_PREFIX = 'nmx-c'
    NMX_TELEMETRY_PREFIX = 'nmx-t'
    INITIAL_APPS_PATH = '/usr/local/cluster_pkgfiles/'
    INFRA_PACKAGES_PATH = '/host/cluster_infra/packages/'

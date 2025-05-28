import os
from ngts.constants.constants import InfraConst
from enum import Enum


class SharedConsts:
    ENV_COVERAGE_FILE = 'COVERAGE_FILE'
    GCOV_DIR = '/sonic'
    SONIC_SOURCES_PATH = ['/src/sonic_src_cov.tar.gz']
    C_DIR = "/c_coverage/"
    PYTHON_DIR = "/python_coverage/"


class NvosConsts:
    NVOS_EXCLUDE_PATHS = ['/sonic/src/nvos-sairedis/meta', '/sonic/src/nvos-sairedis/SAI']
    NVOS_SOURCE_FILES = ['sonic/src/nvos-swss/cfgmgr/portmgr', 'sonic/src/nvos-swss/orchagent/response_publisher',
                         'sonic/src/nvos-swss/lib/subintf', 'sonic/src/nvos-swss/cfgmgr/portmgrd',
                         'sonic/src/nvos-swss/cfgmgr/intfmgrd', 'sonic/src/nvos-swss/orchagent/request_parser',
                         'sonic/src/nvos-swss/orchagent/response_publisher',
                         'sonic/src/nvos-swss/orchagent/request_parser', 'sonic/src/nvos-swss/orchagent/request_parser',
                         'sonic/src/nvos-swss/orchagent/orch', 'sonic/src/nvos-swss/cfgmgr/intfmgr',
                         'sonic/src/nvos-swss/orchagent/flex_counter/flex_counter_manager',
                         'sonic/src/nvos-swss/orchagent/request_parser',
                         'sonic/src/nvos-swss/orchagent/response_publisher',
                         'sonic/src/nvos-swss/orchagent/portsorch', 'sonic/src/nvos-swss/orchagent/notifications',
                         'sonic/src/nvos-swss/orchagent/orchdaemon', 'sonic/src/nvos-swss/orchagent/saiattr',
                         'sonic/src/nvos-swss/orchagent/flexcounterorch', 'sonic/src/nvos-swss/orchagent/saihelper',
                         'sonic/src/nvos-swss/orchagent/switchorch', 'sonic/src/nvos-swss/orchagent/orch',
                         'sonic/src/nvos-swss/orchagent/main', 'sonic/src/nvos-swss/swssconfig/swssconfi',
                         'sonic/src/nvos-swss/portsyncd/linksync', 'sonic/src/nvos-swss/lib/gearboxutils',
                         'sonic/src/nvos-swss/portsyncd/portsyncd', 'sonic/src/nvos-sairedis/lib/ClientSai',
                         'sonic/src/nvos-sairedis/lib/ContextConfigContainer',
                         'sonic/src/nvos-sairedis/lib/RedisVidIndexGenerator',
                         'sonic/src/nvos-sairedis/lib/SwitchConfig', 'sonic/src/nvos-sairedis/lib/ServerConfig',
                         'sonic/src/nvos-sairedis/lib/SwitchConfigContainer',
                         'sonic/src/nvos-sairedis/lib/ContextConfig', 'sonic/src/nvos-sairedis/lib/Context',
                         'sonic/src/nvos-sairedis/lib/VirtualObjectIdManager',
                         'sonic/src/nvos-sairedis/syncd/TimerWatchdog', 'sonic/src/nvos-sairedis/lib/Switch',
                         'sonic/src/nvos-sairedis/syncd/NotificationHandler', 'sonic/src/nvos-sairedis/syncd/SaiSwitch',
                         'sonic/src/nvos-sairedis/syncd/SwitchNotifications', 'sonic/src/nvos-sairedis/syncd/Workaround', 'sonic/src/nvos-sairedis/syncd/AsicOperation', 'sonic/src/nvos-sairedis/syncd/GlobalSwitchId', 'sonic/src/nvos-sairedis/syncd/BestCandidateFinder',
                         'sonic/src/nvos-sairedis/syncd/SaiDiscovery', 'sonic/src/nvos-sairedis/lib/ClientServerSai',
                         'sonic/src/nvos-sairedis/syncd/CommandLineOptionsParser',
                         'sonic/src/nvos-sairedis/lib/ClientConfig', 'sonic/src/nvos-sairedis/lib/ClientConfig',
                         'sonic/src/nvos-sairedis/syncd/RequestShutdownCommandLineOptions',
                         'sonic/src/nvos-sairedis/syncd/FlexCounter', 'sonic/src/nvos-sairedis/syncd/MetadataLogger',
                         'sonic/src/nvos-sairedis/syncd/ZeroMQNotificationProducer',
                         'sonic/src/nvos-sairedis/syncd/MdioIpcServer', 'sonic/src/nvos-sairedis/syncd/SaiObj',
                         'sonic/src/nvos-sairedis/syncd/ComparisonLogic', 'sonic/src/nvos-sairedis/syncd/SaiAttr',
                         'sonic/src/nvos-sairedis/syncd/AsicView', 'sonic/src/nvos-sairedis/syncd/FlexCounterManager',
                         'sonic/src/nvos-sairedis/syncd/RedisNotificationProducer',
                         'sonic/src/nvos-sairedis/syncd/WarmRestartTable', 'sonic/src/nvos-sairedis/syncd/gcovpreload',
                         'sonic/src/nvos-sairedis/syncd/CommandLineOptions',
                         'sonic/src/nvos-sairedis/syncd/VirtualOidTranslator', 'sonic/src/nvos-sairedis/syncd/Syncd',
                         'sonic/src/nvos-sairedis/syncd/NotificationProcessor',
                         'sonic/src/nvos-sairedis/syncd/RedisClient', 'sonic/src/nvos-sairedis/syncd/BreakConfig',
                         'sonic/src/nvos-sairedis/syncd/SingleReiniter', 'sonic/src/nvos-sairedis/lib/Utils',
                         'sonic/src/nvos-sairedis/syncd/SaiSwitchInterface',
                         'sonic/src/nvos-sairedis/syncd/WatchdogScope', 'sonic/src/nvos-sairedis/lib/ZeroMQChannel',
                         'sonic/src/nvos-sairedis/syncd/ServiceMethodTable', 'sonic/src/nvos-sairedis/syncd/VidManager',
                         'sonic/src/nvos-sairedis/syncd/NotificationQueue', 'sonic/src/nvos-sairedis/syncd/syncd_main',
                         'sonic/src/nvos-sairedis/syncd/BreakConfigParser', 'sonic/src/nvos-sairedis/syncd/HardReiniter',
                         'sonic/src/nvos-sairedis/syncd/VendorSai', 'sonic/src/nvos-sairedis/syncd/main',
                         'sonic/src/nvos-sairedis/meta/MetaKeyHasher',
                         'sonic/src/nvos-sairedis/meta/NotificationFactory', 'sonic/src/nvos-sairedis/meta/AttrKeyMap',
                         'sonic/src/nvos-sairedis/meta/NotificationModulePlugEvent',
                         'sonic/src/nvos-sairedis/meta/Notification',
                         'sonic/src/nvos-sairedis/meta/RedisSelectableChannel', 'sonic/src/nvos-sairedis/lib/Channel',
                         'sonic/src/nvos-sairedis/meta/OidRefCounter',
                         'sonic/src/nvos-sairedis/meta/NotificationSwitchStateChange',
                         'sonic/src/nvos-sairedis/meta/SaiObjectCollection',
                         'sonic/src/nvos-sairedis/meta/PortRelatedSet', 'sonic/src/nvos-sairedis/meta/SelectableChannel',
                         'sonic/src/nvos-sairedis/meta/NotificationSwitchShutdownRequest',
                         'sonic/src/nvos-sairedis/meta/SaiSerialize', 'sonic/src/nvos-sairedis/meta/Globals',
                         'sonic/src/nvos-sairedis/meta/SaiObject', 'sonic/src/nvos-sairedis/lib/RedisRemoteSaiInterface',
                         'sonic/src/nvos-sairedis/meta/ZeroMQSelectableChannel',
                         'sonic/src/nvos-sairedis/meta/NotificationBfdSessionStateChange',
                         'sonic/src/nvos-sairedis/meta/NotificationPortStateChange',
                         'sonic/src/nvos-sairedis/meta/NotificationFdbEvent',
                         'sonic/src/nvos-sairedis/meta/NotificationQueuePfcDeadlock',
                         'sonic/src/nvos-sairedis/meta/SaiInterface',
                         'sonic/src/nvos-sairedis/meta/PerformanceIntervalTimer',
                         'sonic/src/nvos-sairedis/meta/NumberOidIndexGenerator',
                         'sonic/src/nvos-sairedis/meta/Meta', 'sonic/src/nvos-sairedis/meta/SaiAttributeList',
                         'sonic/src/nvos-sairedis/lib/sai_redis_nexthopgroup',
                         'sonic/src/nvos-sairedis/lib/sai_redis_rpfgroup', 'sonic/src/nvos-sairedis/lib/sai_redis_bfd',
                         'sonic/src/nvos-sairedis/lib/sai_redis_dtel', 'sonic/src/nvos-sairedis/lib/sai_redis_nat',
                         'sonic/src/nvos-sairedis/lib/sai_redis_macsec',
                         'sonic/src/nvos-sairedis/lib/sai_redis_router_interface',
                         'sonic/src/nvos-sairedis/lib/sai_redis_bmtor',
                         'sonic/src/nvos-sairedis/lib/sai_redis_interfacequery']
    NVOS_SOURCE_PATH = '/src'
    GCOV_CONTAINERS_SOURCES_PATH = {'swss-ibv00': '/src/sonic_swss_src_cov.tar.gz',
                                    'syncd-ibv00': '/src/sonic_syncd_src_cov.tar.gz',
                                    'swss-ibv01': '/src/sonic_swss_src_cov.tar.gz',
                                    'syncd-ibv01': '/src/sonic_syncd_src_cov.tar.gz'}
    DEST_PATH = "/auto/sw_system_project/NVOS_INFRA/coverage/"


class SonicConsts:
    GCOV_CONTAINERS_SONIC = ['swss', 'syncd']

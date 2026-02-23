
class IbRouterConsts:
    # consts that define XDR router topology
    SWID_NUM = 4
    ALL_HOSTS_NICKNAMES = ['ha', 'hb', 'hc', 'hd', 'he', 'hf', 'hg', 'hh']
    SM_HOSTS_NICKNAMES = ['ha', 'hc', 'he', 'hg']
    CROC_SWITCHES_NICKNAMES = ['dut2', 'dut3']
    SWID_TO_PORTS_DICT = {0: ['sw1p1', 'sw1p2'],
                          1: ['sw2p1', 'sw2p2'],
                          2: ['sw3p1', 'sw3p2'],
                          3: ['sw4p1', 'sw4p2']}
    SWID_TO_SM_NICKNAME = {0: 'ha',
                           1: 'hc',
                           2: 'he',
                           3: 'hg'}
    SWID_TO_HOSTS = {0: ['ha', 'hb'],
                     1: ['hc', 'hd'],
                     2: ['he', 'hf'],
                     3: ['hg', 'hh']}
    HOST_TO_SWID = {'ha': 0, 'hb': 0,
                    'hc': 1, 'hd': 1,
                    'he': 2, 'hf': 2,
                    'hg': 3, 'hh': 3}
    OPERATIONAL_SWIDS = [0, 1, 2, 3]
    ROUTER_PORTS_TO_LEAFS = ['sw1p1', 'sw1p2', 'sw2p1', 'sw2p2', 'sw3p1', 'sw3p2', 'sw4p1', 'sw4p2']

    # general consts
    FNM_SHUTDOWN_COMMANDS = ['sonic-db-cli CONFIG_DB hset "IB_PORT|Infiniband288" "admin_status" "down"',
                             'sonic-db-cli CONFIG_DB hset "IB_PORT|Infiniband290" "admin_status" "down"',
                             'sonic-db-cli CONFIG_DB hset "IB_PORT|Infiniband292" "admin_status" "down"']
    OPENSM_CONF_PATH = "/auto/sw_system_project/NVOS_INFRA/verification_files/xdr_ib_router/"
    OPENSM_CONF_FILE_NAME = "opensm_conf_{}.cfg"
    OPENSM_ROOT_GUID_FILE_NAME = "root_guid_file_{}.cfg"
    ROUTER_POLICY_FILE_NAME = "router_policy.cfg"
    ROUTER_POLICY_MASTER_FILE_NAME = "router_policy_master.cfg"
    OPENSM_BIN_PATH = "/root/reefpoc/usr/sbin/opensm"
    SUBNET_PREFIX = 'subnet-prefix'
    VALID = "valid"
    ROUTING_TABLE = "routing-table"
    DEFAULT_SWID_NAME = 'infiniband-default'
    NON_DEFAULT_SWID_NAME = 'infiniband-{}'
    # the network prefix starts with 0xfecin the openSM config file, for example 0xfec0000002
    SUBNET_PREFIX_INITITAL = '0xfec'
    IBR_DUMP_FILE = 'ib.router'

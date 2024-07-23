class InternalNvosConsts:
    # Output dictionary
    OPERATIONAL_INDEX = 0
    APPLIED_INDEX = 1
    DEFAULT_TIMEOUT = 120   # in MS
    IB_TRAFFIC_SENDER_INTERFACE = "h1p1"
    IB_TRAFFIC_RECEIVER_INTERFACE = "h2p1"
    IB_TRAFFIC_LAT_TYPE = "ib_send_lat"
    IB_TRAFFIC_IPOIB_TYPE = "ping_over_ib"


class NvosConsts:
    LINK_STATE_UP = "up"
    LINK_STATE_DOWN = "down"
    LINK_LOG_STATE_ACTIVE = 'Active'
    LINK_LOG_STATE_INITIALIZE = 'Initialize'


class NvlInterfaceConsts:
    NVL_PORT_TYPE = "nvl"


class InterfaceConsts:
    DESCRIPTION = "description"


class IbInterfaceConsts:
    INTERFACE_NAME = "name"
    DESCRIPTION = "description"
    ARPTIMEOUT = "arp-timeout"
    AUTOCONFIG = "autoconf"
    DHCP_STATE = 'state'
    DHCP_SET_HOSTNAME = 'set-hostname'
    TYPE = "type"
    LINK = "link"
    IP = "ip"
    IFINDEX = "ifindex"
    LINK_LOGICAL_PORT_STATE = "logical-state"
    LINK_LOGICAL_PORT_STATE_ACTIVE = 'Active'
    LINK_LOGICAL_PORT_STATE_INITIALIZE = 'Initialize'
    LINK_LOGICAL_PORT_STATE_UP = 'Up'
    LINK_LOGICAL_PORT_STATE_DOWN = 'Down'
    LINK_PHYSICAL_PORT_STATE = "physical-state"
    LINK_PHYSICAL_PORT_STATE_LINK_UP = 'LinkUp'
    LINK_PHYSICAL_PORT_STATE_DISABLED = 'Disabled'
    LINK_PHYSICAL_PORT_STATE_POLLING = 'Polling'
    LINK_PHYSICAL_PORT_STATE_POLLING_XDR = 'PortConfigurationTraining'
    LINK_STATE = "state"
    LINK_CONNECTION_MODE = "connection-mode"
    XDR = "xdr"
    LINK_DIAGNOSTICS = "diagnostics"
    LINK_DIAGNOSTICS_UNPLUGGED_PORT = {'1024': {'status': 'Cable is unplugged'}}
    LINK_DIAGNOSTICS_CLOSED_BY_COMMAND_PORT = {'1': {'status': 'Closed by command'}}
    LINK_DIAGNOSTICS_WITHOUT_ISSUE_PORT = {'0': {'status': 'No issue was observed'}}
    LINK_DIAGNOSTICS_NEGOTIATION_FAILURE_PORT = {'2': {'status': 'Negotiation failure'}}
    LINK_DIAGNOSTICS_SIGNAL_NOT_DETECTED = {'57': {'status': 'signal not detected'}}
    LINK_BREAKOUT = "breakout"
    LINK_IB_SPEED = "ib-speed"
    LINK_SUPPORTED_IB_SPEEDS = "supported-ib-speed"
    LINK_SPEED = "speed"
    LINK_MAC = "mac"
    LINK_DUPLEX = "duplex"
    LINK_AUTO_NEGOTIATE = "auto-negotiate"
    LINK_SUPPORTED_SPEEDS = "supported-speed"
    LINK_SUPPORTED_LANES = "supported-lanes"
    LINK_LANES = "lanes"
    LINK_MAX_SUPPORTED_MTU = "max-supported-mtu"
    LINK_MTU = "mtu"
    LINK_VL_ADMIN_CAPABILITIES = "vl-capabilities"
    LINK_OPERATIONAL_VLS = "op-vls"
    LINK_IB_SUBNET = "ib-subnet"
    LINK_STATS = "counters"
    LINK_STATS_CARRIER_TRANSITION = "carrier-transitions"
    LINK_STATS_IN_BYTES = "in-bytes"
    LINK_STATS_IN_DROPS = "in-drops"
    LINK_STATS_IN_ERRORS = "in-errors"
    LINK_STATS_IN_SYMBOL_ERRORS = "in-symbol-errors"
    LINK_STATS_IN_PKTS = "in-pkts"
    LINK_STATS_OUT_BYTES = "out-bytes"
    LINK_STATS_OUT_DROPS = "out-drops"
    LINK_STATS_OUT_ERRORS = "out-errors"
    LINK_STATS_OUT_PKTS = "out-pkts"
    LINK_STATS_OUT_WAIT = "out-wait"
    LINK_STATS_RCV_ICRC_ERRORS = 'rcv-icrc-errors'
    LINK_STATS_TX_PARITY_ERRORS = 'tx-parity-errors'
    LINK_STATS_QNT3 = ['link-error-recovery', 'link-downed', 'port-rcv-remote-physical-errors', 'port-rcv-switch-relay-errors',
                       'port-rcv-constraint-errors', 'local-link-integrity-errors', 'qp1-drops', 'buffer-overrun-errors',
                       LINK_STATS_RCV_ICRC_ERRORS, LINK_STATS_TX_PARITY_ERRORS]
    LINK_BREAKOUT_NDR = "2x-ndr"
    LINK_BREAKOUT_HDR = "2x-hdr"
    LINK_BREAKOUT_XDR = "2x-xdr"
    LINK_ROUND_TRIP_LATENCY = "round-trip-latency"
    PRIMARY_ASIC = "primary-asic"
    IP_VRF = "vrf"
    IP_ADDRESS = "address"
    IP_GATEWAY = "gateway"
    IP_DHCP = "dhcp-client"
    IP_DHCP6 = "dhcp-client6"
    NAME = "name"
    IB_PORT_TYPE = "ib"
    FNM_PORT_TYPE = "fnm"
    LOOPBACK_PORT_TYPE = "loopback"
    ETH_PORT_TYPE = "eth"
    MTU_VALUES = [256, 512, 1024, 2048, 4096]
    DEFAULT_MTU = 4096
    SPEED_LIST = {'xdr': '800G', 'ndr': '400G', 'hdr': '200G', 'edr': '100G', 'fdr': '56G', 'qdr': '40G', 'sdr': '10G'}
    SUPPORTED_LANES = ['1X', '1X,2X', '1X,4X', '1X,2X,4X']
    DEFAULT_LANES = '1X,2X,4X'
    SPLIT_PORT_DEFAULT_LANES = '4X'
    SPLIT_PORT_CHILD_DEFAULT_LANES = '2X'
    SPLIT_PORT_DEFAULT_MTU = 4096
    SPLIT_PORT_DEFAULT_VLS = 'VL0-VL3'
    SUPPORTED_VLS = ['VL0', 'VL0-VL1', 'VL0-VL3', 'VL0-VL7']
    DEFAULT_VLS = 'VL0-VL7'
    IB0_LINK_MTU_DEFAULT_VALUE = 2044
    IB0_IP_ARP_DEFAULT_VALUE = 1800
    IB0_IP_AUTOCONF_DEFAULT_VALUE = 'disabled'
    IB0_DHCP_STATE_DEFAULT_VALUE = 'disabled'
    MAX_COUNTERS_AFTER_CLEAR = 700
    PLANARIZED_PORTS = "planarized-ports"


class DataBaseNames:
    CONFIG_DB = "ConfigDb"
    STATE_DB = 'StateDb'

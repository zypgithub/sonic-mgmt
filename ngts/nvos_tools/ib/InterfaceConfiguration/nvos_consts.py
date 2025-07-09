from enum import Enum


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
    LINK_STATE_ALL_TYPES = [LINK_STATE_UP, LINK_STATE_DOWN]
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
    INTERFACE_STATE = 'interface-state'
    UP_ONCE = 'up-once'
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
    LINK_ADMIN_STATUS = "admin-status"
    LINK_OPER_STATUS = "oper-status"
    LINK_STATE = "state"
    LINK_CONNECTION_MODE = "connection-mode"
    XDR = "xdr"
    NDR = "ndr"
    SDR = "sdr"
    LINK_AUTO_NEG_ON = 'on'
    LINK_AUTO_NEG_OFF = 'off'
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
    LINK_STATS_UNICAST_IN_PKTS = "unicast-in-pkts"
    LINK_STATS_MULTICAST_IN_PKTS = "multicast-in-pkts"
    LINK_STATS_OUT_BYTES = "out-bytes"
    LINK_STATS_OUT_DROPS = "out-drops"
    LINK_STATS_OUT_ERRORS = "out-errors"
    LINK_STATS_OUT_PKTS = "out-pkts"
    LINK_STATS_UNICAST_OUT_PKTS = "unicast-out-pkts"
    LINK_STATS_MULTICAST_OUT_PKTS = "multicast-out-pkts"
    LINK_STATS_OUT_WAIT = "out-wait"
    MAX_BYTE_COUNTER_AFTER_CLEAR = 2500
    MAX_PKT_COUNTER_AFTER_CLEAR = 9
    LINK_STATS_RCV_ICRC_ERRORS = 'rcv-icrc-errors'
    LINK_STATS_TX_PARITY_ERRORS = 'tx-parity-errors'
    LINK_PLR_RCV_CODES_ERRORS = 'plr-rcv-codes-err'
    LINK_STATS_QNT3 = ['link-error-recovery',
                       'link-downed',
                       'port-rcv-remote-physical-errors',
                       'port-rcv-switch-relay-errors',
                       'port-rcv-constraint-errors',
                       'local-link-integrity-errors',
                       'qp1-drops',
                       'buffer-overrun-errors',
                       LINK_STATS_RCV_ICRC_ERRORS,
                       LINK_STATS_TX_PARITY_ERRORS,
                       LINK_PLR_RCV_CODES_ERRORS]
    LINK_PHY_RAW_ERRORS = ["phy-raw-errors-lane0",
                           "phy-raw-errors-lane1",
                           "phy-raw-errors-lane2",
                           "phy-raw-errors-lane3",
                           "phy-raw-errors-lane4",
                           "phy-raw-errors-lane5",
                           "phy-raw-errors-lane6",
                           "phy-raw-errors-lane7"]
    LINK_PHY_RAW_BER = ["raw-ber-lane0",
                        "raw-ber-lane1",
                        "raw-ber-lane2",
                        "raw-ber-lane3",
                        "raw-ber-lane4",
                        "raw-ber-lane5",
                        "raw-ber-lane6",
                        "raw-ber-lane7"]
    LINK_BREAKOUT_NDR = "2x-ndr"
    LINK_BREAKOUT_HDR = "2x-hdr"
    LINK_BREAKOUT_XDR = "2x-xdr"
    LINK_ROUND_TRIP_LATENCY = "round-trip-latency"
    ASIC = "asic"
    PRIMARY_ASIC = "primary-asic"
    PRIMARY_ASIC_DEVICE = "primary-asic-device"
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
    XDR_SLOW_SPEED = '200G'
    SPEED_LIST = {'xdr': '800G', 'ndr': '400G', 'hdr': '200G', 'edr': '100G', 'fdr': '56G', 'qdr': '40G', 'sdr': '10G'}
    SUPPORTED_LANES = ['1X', '1X,2X', '1X,4X', '1X,2X,4X']
    DEFAULT_LANES = '1X,2X,4X'
    SPLIT_PORT_DEFAULT_LANES = '4X'
    SPLIT_PORT_CHILD_DEFAULT_LANES = '2X'
    SPLIT_PORT_DEFAULT_MTU = 4096
    SPLIT_PORT_DEFAULT_VLS = 'VL0-VL1'
    SUPPORTED_VLS = ['VL0', 'VL0-VL1', 'VL0-VL3', 'VL0-VL7']
    DEFAULT_VLS = 'VL0-VL7'
    IB0_LINK_MTU_DEFAULT_VALUE = 2044
    IB0_IP_ARP_DEFAULT_VALUE = 1800
    IB0_IP_AUTOCONF_DEFAULT_VALUE = 'disabled'
    IB0_DHCP_STATE_DEFAULT_VALUE = 'disabled'
    MAX_COUNTERS_AFTER_CLEAR = 700
    PLANARIZED_PORTS = "planarized-ports"
    PC_VL15_DROPPED_F = "SAI_PORT_STAT_INFINIBAND_PC_VL15_DROPPED_F"
    RCV_DISCARD_EXTERNAL_CONTAIN = "SAI_PORT_STAT_INFINIBAND_RCV_DISCARD_EXTERNAL_CONTAIN"
    TOTAL_IN_DROPS = "PORT_STAT_INFINIBAND_TOTAL_IN_DROPS"
    PC_XMT_DISCARDS_F = "SAI_PORT_STAT_INFINIBAND_PC_XMT_DISCARDS_F"
    XMT_DISCARD_EXTERNAL_CONTAIN = "SAI_PORT_STAT_INFINIBAND_XMT_DISCARD_EXTERNAL_CONTAIN"
    TOTAL_OUT_DROPS = "PORT_STAT_INFINIBAND_TOTAL_OUT_DROPS"


class FWRecoveryConsts:
    # Define constants for recovery event fields
    TOTAL_SUCCESSFUL_RECOVERY_EVENTS = 'total-successful-recovery-events'
    TIME_IN_LAST_LOGIC_RECOVERY_EVENT = 'time-in-last-logic-recovery-event'
    TIME_IN_LAST_SERDES_EQ_RECOVERY_EVENT = 'time-in-last-serdes-eq-recovery-event'
    TIME_SINCE_LAST_RECOVERY = 'time-since-last-recovery'
    LAST_LOGIC_RECOVERY_ATTEMPTS = 'last-logic-recovery-attempts'
    LAST_SERDES_EQ_RECOVERY_ATTEMPTS = 'last-serdes-eq-recovery-attempts'
    TIME_BETWEEN_LAST_TWO_RECOVERIES = 'time-between-last-two-recoveries'

    ENABLED = 'enabled'
    DISABLED = 'disabled'
    FW_DEFAULT = 'fw-default'

    # Default expected values
    DEFAULT_FW_RECOVERY_COUNTERS = {
        TOTAL_SUCCESSFUL_RECOVERY_EVENTS: 0,
        TIME_IN_LAST_LOGIC_RECOVERY_EVENT: 0,
        TIME_IN_LAST_SERDES_EQ_RECOVERY_EVENT: 0,
        TIME_SINCE_LAST_RECOVERY: 0,
        LAST_LOGIC_RECOVERY_ATTEMPTS: 0,
        LAST_SERDES_EQ_RECOVERY_ATTEMPTS: 0,
        TIME_BETWEEN_LAST_TWO_RECOVERIES: 0,
    }

    class SerdesEQMode(Enum):
        ENABLED = 'enabled'
        DISABLED = 'disabled'
        FW_DEFAULT = 'fw-default'

    class LogicRelockMode(Enum):
        ENABLED = 'enabled'
        DISABLED = 'disabled'
        FW_DEFAULT = 'fw-default'

    class SerdesEQ:
        MODE = "serdes-eq-mode"
        TIMEOUT = "serdes-eq-timeout"
        SETTING_PREFIX = "serdes-eq"

    class LogicRelock:
        MODE = "logic-relock-mode"
        TIMEOUT = "logic-relock-timeout"
        SETTING_PREFIX = "logic-relock"

    DEFAULT_PHY_RECOVERY_DICT = {
        SerdesEQ.MODE: SerdesEQMode.DISABLED.value,
        SerdesEQ.TIMEOUT: str(0),
    }

    MODES = ['disabled', 'fw-default', 'enabled']

    negative_test_cases = {
        SerdesEQ.MODE: {
            "bad_value": "bad-mode",
            "expected_error": "'bad-mode' is not one of"
        },
        SerdesEQ.TIMEOUT: {
            "bad_value": "-1",
            "expected_error": "'-1' is not of type 'integer'"
        },
        LogicRelock.MODE: {
            "bad_value": "bad-mode",
            "expected_error": "'bad-mode' is not one of"
        },
        LogicRelock.TIMEOUT: {
            "bad_value": "100000",
            "expected_error": "logic-relock-timeout must match one of the following:"
        }
    }


class DataBaseNames:
    CONFIG_DB = "ConfigDb"
    STATE_DB = 'StateDb'

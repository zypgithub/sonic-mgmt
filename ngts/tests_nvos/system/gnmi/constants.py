class GnmiMode:
    ONCE = 'once'
    POLL = 'poll'
    STREAM = ''
    ALL_MODES = [ONCE, POLL, STREAM]


GNMI_INSTALLED = 'gnmi-server'

DUT_HOSTNAME_FOR_CERT = 'nvos-dut'
DUT_GNMI_CERTS_DIR = '/tmp/gnmi-certs'
DOCKER_CERTS_DIR = '/etc/netq/cert'

DUT_MOUNT_GNMI_CERT_DIR = '/etc/gnmi/cert'

ETC_HOSTS = '/etc/hosts'

SERVICE_KEY = 'service.key'
SERVICE_PEM = 'service.pem'

MAX_GNMI_SUBSCRIBERS = 10
MAX_GNMI_CONNECTIVITY_TIME = 6

CERTIFICATE = 'certificate'
DEFAULT_CERTIFICATE = 'self-signed'

SERVER_REFLECTION_SUBSCRIBE_RESPONSE = '.gnmi.SubscribeResponse'


class GnmicErr:
    GNMIC_NOT_INSTALLED = 'gnmic: command not found'
    AUTH_FAIL = 'Authentication failed'
    CERT_VERIFY_FAIL = 'failed to verify certificate'
    HANDSHAKE_FAIL = 'authentication handshake failed'
    AUTH_SERVICE_UNAVAILABLE = 'authentication service is unavailable'
    REQUEST_FAILED = 'request failed'
    NO_SUBSCRIBER_SLOT_AVAILABLE = 'no subscriber slot available'
    RCV_ERROR = 'rcv error'
    RPC_ERROR = 'rpc error'
    ALL_ERRS = [GNMIC_NOT_INSTALLED, AUTH_FAIL, HANDSHAKE_FAIL, AUTH_SERVICE_UNAVAILABLE,
                REQUEST_FAILED, NO_SUBSCRIBER_SLOT_AVAILABLE, RCV_ERROR, RPC_ERROR]


class GrpcMsg:
    LIST_SERVICES_FAIL = 'Failed to list services'
    MSG_SERVER_REFLECT = 'service ServerReflection'
    MSG_SUBSCRIBE_RESPONSE = 'message SubscribeResponse'
    ALL_MSGS = {SERVER_REFLECTION_SUBSCRIBE_RESPONSE: MSG_SUBSCRIBE_RESPONSE}

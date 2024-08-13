NA = 'N/A'
STATE = 'state'

ENABLED = 'enabled'
DISABLED = 'disabled'

PORT = 'port'
CERTIFICATE = 'certificate'
CA_CERTIFICATE = 'ca-certificate'
ENCRYPTION = 'encryption'

DEFAULT_NMX_C_MGMT_PORT = 51000

USR_CFG_JSON_PATH = '/etc/cluster_infra/conf/user_config.json'
USR_CFG_JSON = USR_CFG_JSON_PATH.split('/')[-1]

NMX_CERTS_DIR = '/etc/nmx/cert'
NMX_CACERTS_DIR = '/etc/nmx/ca_cert'

FILE_NOT_EXIST_ERR = 'No such file or directory'

FILE_SHOULD_NOT_EXIST = -1


class UserCfgJsonFields:
    CERTIFICATE = 'manager-certificate'
    PRIVATE_KEY = 'manager-private-key'
    CA_CERTIFICATE = 'manager-ca-certificate'
    ENCRYPTION = 'manager-encryption'
    STATE = 'manager-port'


class UserCfgJsonValues:
    CERTIFICATE = f'{NMX_CERTS_DIR}/nmx.csr'
    PRIVATE_KEY = f'{NMX_CERTS_DIR}/nmx.key'
    CA_CERTIFICATE = f'{NMX_CACERTS_DIR}/ca_nmx.crt'


class FieldsInShowOf:
    MANAGER = [STATE, CERTIFICATE, CA_CERTIFICATE, ENCRYPTION]
    CERTIFICATE = [CERTIFICATE]
    CA_CERTIFICATE = [CA_CERTIFICATE]
    ENCRYPTION = [ENCRYPTION]


class EncryptionMode:
    DISABLED = 'disabled'
    TLS = 'tls'
    MTLS = 'mtls'
    ALL_MODES = [DISABLED, TLS, MTLS]


class Defaults:
    STATE = DISABLED
    CERT = ''
    CACERT = ''
    ENCRYPTION = EncryptionMode.DISABLED

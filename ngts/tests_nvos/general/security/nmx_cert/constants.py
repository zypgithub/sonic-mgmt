NA = 'N/A'
STATE = 'state'

ENABLED = 'enabled'
DISABLED = 'disabled'

PORT = 'port'
CERTIFICATE = 'certificate'
CA_CERTIFICATE = 'ca-certificate'
ENCRYPTION = 'encryption'

NMX_C_MGMT_PORT = 50051  # TODO: find out

USR_CFG_JSON_PATH = '/host/cluster_infra/conf/user_config.json'
USR_CFG_JSON = USR_CFG_JSON_PATH.split('/')[-1]

NMX_CERTS_DIR = '/etc/nmx/cert'
NMX_CACERTS_DIR = '/etc/nmx/ca_cert'

FILE_NOT_EXIST_ERR = 'No such file or directory'

FILE_SHOULD_NOT_EXIST = -1


class UserCfgJsonFields:
    CERTIFICATE = 'manager-certificate'
    CA_CERTIFICATE = 'manager-ca-certificate'
    ENCRYPTION = 'manager-encryption'
    STATE = 'manager-port'


class UserCfgJsonValues:
    CERTIFICATE = f'{NMX_CERTS_DIR}/'
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

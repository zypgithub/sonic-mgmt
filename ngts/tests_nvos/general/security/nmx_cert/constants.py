from typing import List, Dict

from ngts.nvos_constants.constants_nvos import ClusterApps

NA = 'N/A'
STATE = 'state'

ENABLED = 'enabled'
DISABLED = 'disabled'

PORT = 'port'
CERTIFICATE = 'certificate'
CA_CERTIFICATE = 'ca-certificate'
ENCRYPTION = 'encryption'

DEFAULT_NMX_C_MGMT_PORT = 9370

USR_CFG_JSON_PATH = '/etc/cluster_infra/conf/user_config.json'
USR_CFG_JSON = USR_CFG_JSON_PATH.split('/')[-1]

NMX_CERTS_DIR = '/etc/nmx/cert'
NMX_CACERTS_DIR = '/etc/nmx/ca_cert'

FILE_NOT_EXIST_ERR = 'No such file or directory'


class UserCfgJsonFields:
    CERTIFICATE = 'manager-certificate'
    PRIVATE_KEY = 'manager-private-key'
    CA_CERTIFICATE = 'manager-ca-certificate'
    ENCRYPTION = 'manager-encryption'
    STATE = 'manager-port'
    ALL_FIELDS = [CERTIFICATE, PRIVATE_KEY, CA_CERTIFICATE, ENCRYPTION, STATE]


class UserCfgJsonValues:
    CERTIFICATE = NMX_CERTS_DIR + '/{filename}.crt'  # f'{NMX_CERTS_DIR}/nmx.csr'
    PRIVATE_KEY = NMX_CERTS_DIR + '/{filename}.key'  # f'{NMX_CERTS_DIR}/nmx.key'
    CA_CERTIFICATE = NMX_CACERTS_DIR + '/{filename}.crt'  # f'{NMX_CACERTS_DIR}/ca_nmx.crt'


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


class ClusterAppConsts:

    def __init__(self):
        # TODO: clarify
        self.user_config_json_path: str = USR_CFG_JSON_PATH
        self.user_config_json_fields: List[str] = UserCfgJsonFields.ALL_FIELDS
        self.fields_that_must_exist_in_user_config_json: dict = {UserCfgJsonFields.STATE: Defaults.STATE}
        self.cert_private_key_path: str = NMX_CERTS_DIR + '/{}.key'
        self.cert_public_key_path: str = NMX_CERTS_DIR + '/{}.crt'
        self.cacert_path: str = NMX_CACERTS_DIR + '/{}.crt'


class NmxControllerConsts(ClusterAppConsts):

    def __init__(self):
        super().__init__()


class NmxTelemetryConsts(ClusterAppConsts):

    def __init__(self):
        super().__init__()


APP_CONSTS: Dict[str, ClusterAppConsts] = {ClusterApps.NMX_CONTROLLER: NmxControllerConsts(), ClusterApps.NMX_TELEMETRY: NmxTelemetryConsts()}

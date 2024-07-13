ENABLED = 'enabled'
DISABLED = 'disabled'

STATE = 'state'  # TODO: is there field state in show cluster manager?
CERTIFICATE = 'certificate'
CA_CERTIFICATE = 'ca-certificate'
ENCRYPTION = 'encryption'
CERT_ID = 'cert-id'
MODE = 'mode'

NMX_C_MGMT_PORT = 50051  # TODO: find out


class FieldsInShowOf:
    MANAGER = [STATE, CERTIFICATE, CA_CERTIFICATE, ENCRYPTION]
    CERTIFICATE = [CERT_ID]
    CA_CERTIFICATE = [CERT_ID]
    ENCRYPTION = [MODE]  # TODO - is there show encryption?


class EncryptionMode:
    NONE = 'none'
    TLS = 'tls'
    MTLS = 'mtls'
    ALL_MODES = [NONE, TLS, MTLS]


class Defaults:     # TODO: verify defaults
    STATE = DISABLED
    CERT = 'self-signed'
    CACERT = 'self-signed'
    ENCRYPTION = EncryptionMode.NONE

from ngts.tests_nvos.general.security.nmx_cert.constants import CA_CERTIFICATE

MTLS = 'mtls'
INSTALLED = 'installed'
API_INSTALLED = 'api'


class ApiConsts:
    fields = [MTLS]

    class Mtls:
        fields = [CA_CERTIFICATE]

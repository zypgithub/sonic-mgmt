from ngts.tests_nvos.general.security.certificate.constants import TestCert

MTLS = 'mtls'
INSTALLED = 'installed'
API_INSTALLED = 'nvue-rest-api'
CA_CERTIFICATE = 'ca-certificate'
CERTIFICATE = 'certificate'


class ApiConsts:
    fields = [MTLS]

    class Mtls:
        fields = [CA_CERTIFICATE]

        class Errors:
            CERT_DONT_EXIST = "certificate `{}` doesn't exist"
            INSTALLED_CA_DELETE_ERR = "Error: The CA certificate `{}` is currently being used by the following applications: ['nvue-rest-api']"
            FAILED_TO_VERIFY_SERVER_ERR = 'curl failed to verify the legitimacy of the server'
            NO_CERT_WAS_SENT_ERR = 'No required SSL certificate was sent'
            SSL_CERT_ERR = 'SSL certificate error'
            MTLS_ERRORS = [FAILED_TO_VERIFY_SERVER_ERR, NO_CERT_WAS_SENT_ERR, SSL_CERT_ERR]


class Errors:
    AUTH_ERROR = '401 Authorization Required'
    ALL_ERRORS = [AUTH_ERROR] + ApiConsts.Mtls.Errors.MTLS_ERRORS


TEST_CERTS = [TestCert.cert_valid_1, TestCert.cert_valid_2, TestCert.cert_valid_3]
TEST_CERTS = [cert.copy(f'api-test-{cert.name}') for cert in TEST_CERTS]
TEST_CACERT_NAMES = [cert.cacert_name for cert in TEST_CERTS]

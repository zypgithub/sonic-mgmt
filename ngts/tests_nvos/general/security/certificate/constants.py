from typing import List

from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo

CERT_MGMT_CERTS = '/auto/sw_system_project/NVOS_INFRA/security/verification/cert_mgmt'
TEST_CERTS = '/auto/sw_system_project/NVOS_INFRA/security/verification/certs/test_certs'
GET_SYSTEM_VERSION_PATH = '/nvue_v1/system/version'

DUT_IMPORTED_CERTS_DIR = '/etc/nvue/certificates'
DUT_IMPORTED_CERTS_PRIVATE_DIR = f'{DUT_IMPORTED_CERTS_DIR}/private'
DUT_IMPORTED_CERTS_PUBLIC_DIR = f'{DUT_IMPORTED_CERTS_DIR}/public'

DUT_IMPORTED_CACERTS_DIR = '/etc/ssl/certs'


class CertMsgs:
    SSL_CERTIFICATE_PROBLEM = 'SSL certificate problem'
    SSL_CERTIFICATE_ERROR = 'SSL certificate error'
    NO_REQUIRED_SSL_CERT_SENT = 'No required SSL certificate was sent'
    ALL_ERRORS = [SSL_CERTIFICATE_PROBLEM, SSL_CERTIFICATE_ERROR, NO_REQUIRED_SSL_CERT_SENT]


class TestCert:
    """ constants describe existing test env certificate """
    cert_mgmt_test_cert = CertInfo(
        name='cert-mgmt-valid-cert-1',
        info='valid certificate for certificate mgmt test',
        private=f'{CERT_MGMT_CERTS}/certificate/certificate_private.pem',
        public=f'{CERT_MGMT_CERTS}/certificate/certificate_public.pem',
        p12_bundle=f'{CERT_MGMT_CERTS}/certificate/certificate_bundle.p12',
        p12_password='Test_2108',
        dn='localhost',
        ip='127.0.0.1',
        cacert=f'{CERT_MGMT_CERTS}/ca-certificate/certificate_public.pem'
    )

    cert_mgmt_test_cacert = CertInfo(
        name='cert-mgmt-valid-cacert-1',
        info='valid ca-certificate for certificate mgmt cacert test',
        private=None,
        public=f'{CERT_MGMT_CERTS}/ca-certificate/ca-certificate.crt',
        p12_bundle=None,
        p12_password=None,
        dn=None,
        ip=None,
        cacert=None
    )

    cert_valid_1 = CertInfo(
        name='valid-cert-1',
        info='valid certificate for test - from ca1',
        private=f'{TEST_CERTS}/cert-from-ca1/service.key',
        public=f'{TEST_CERTS}/cert-from-ca1/service.pem',
        p12_bundle=f'{TEST_CERTS}/cert-from-ca1/service.p12',
        p12_password='secret',
        dn='nvos-dut',
        ip=None,
        cacert=f'{TEST_CERTS}/ca1/ca.crt'
    )

    cert_valid_1_long_passphrase = CertInfo(
        name='valid-cert-1-long-pass',
        info='valid certificate for test with 89-char long passphrase - from ca1',
        private=f'{TEST_CERTS}/cert-from-ca1-long-pass/service.key',
        public=f'{TEST_CERTS}/cert-from-ca1-long-pass/service.pem',
        p12_bundle=f'{TEST_CERTS}/cert-from-ca1-long-pass/service.p12',
        p12_password='6RLTILPOCQKNMOUWC38WWXFHOQR24YN441EM0QB255L1OG53E0QPM94LLA0VV8J17XV20BLKU5X1HWI2UVMCYMVLT',
        dn='nvos-dut',
        ip=None,
        cacert=f'{TEST_CERTS}/ca1/ca.crt'
    )

    cert_valid_1_no_passphrase = CertInfo(
        name='valid-cert-1-no-pass',
        info='valid certificate for test with no passphrase - from ca1',
        private=f'{TEST_CERTS}/cert-from-ca1-no-pass/service.key',
        public=f'{TEST_CERTS}/cert-from-ca1-no-pass/service.pem',
        p12_bundle=f'{TEST_CERTS}/cert-from-ca1-no-pass/service.p12',
        p12_password='',
        dn='nvos-dut',
        ip=None,
        cacert=f'{TEST_CERTS}/ca1/ca.crt'
    )

    cert_valid_2 = CertInfo(
        name='valid-cert-2',
        info='valid certificate for test - from ca2',
        private=f'{TEST_CERTS}/cert-from-ca2/service.key',
        public=f'{TEST_CERTS}/cert-from-ca2/service.pem',
        p12_bundle=f'{TEST_CERTS}/cert-from-ca2/service.p12',
        p12_password='secret',
        dn='nvos-dut',
        ip=None,
        cacert=f'{TEST_CERTS}/ca2/ca.crt'
    )

    cert_valid_3 = CertInfo(
        name='valid-cert-3',
        info='valid certificate for test - from ca3',
        private=f'{TEST_CERTS}/cert-from-ca3/service.key',
        public=f'{TEST_CERTS}/cert-from-ca3/service.pem',
        p12_bundle=f'{TEST_CERTS}/cert-from-ca3/service.p12',
        p12_password='secret',
        dn='nvos-dut',
        ip=None,
        cacert=f'{TEST_CERTS}/ca3/ca.crt'
    )

    cert_private_public_mismatch = CertInfo(
        name='cert-private-public-mismatch',
        info="invalid certificate for test - public and private don't match",
        private=f'{TEST_CERTS}/cert-from-ca1/service.key',
        public=f'{TEST_CERTS}/cert-from-ca2/service.pem',
        p12_bundle=None,
        p12_password=None,
        dn='nvos-dut',
        ip=None,
        cacert=f'{TEST_CERTS}/ca1/ca.crt'
    )

    cert_ca_mismatch = CertInfo(
        name='cert-ca-mismatch',
        info="certificate for test - valid certificate but don't match ca",
        private=f'{TEST_CERTS}/cert-from-ca1/service.key',
        public=f'{TEST_CERTS}/cert-from-ca1/service.pem',
        p12_bundle=f'{TEST_CERTS}/cert-from-ca1/service.p12',
        p12_password='secret',
        dn='nvos-dut',
        ip=None,
        cacert=f'{TEST_CERTS}/ca2/ca.crt'
    )

    all_certs: List[CertInfo] = [cert_valid_1, cert_valid_2, cert_private_public_mismatch, cert_ca_mismatch]


class CertShowFields:
    INSTALLED = 'installed'
    SERIAL_NUMBER = 'serial-number'
    VALID_FROM = 'valid-from'
    VALID_TO = 'valid-to'
    ALL_FIELDS = [INSTALLED, SERIAL_NUMBER, VALID_FROM, VALID_TO]


CERT_PRIVATE_KEY_LOCATION = '/etc/nvue/certificates/private'
CERT_PUBLIC_KEY_LOCATION = '/etc/nvue/certificates/public'


class CaShowFields:
    COUNT = 'count'
    INSTALLED = 'installed'
    SERIAL_NUMBER = 'serial-number'
    VALID_FROM = 'valid-from'
    VALID_TO = 'valid-to'
    TYPE = 'type'
    ALL_FIELDS = [COUNT, INSTALLED, SERIAL_NUMBER, VALID_FROM, VALID_TO, TYPE]


GLOBAL_CA_PEM_FILE_LOCATION = '/etc/ssl/certs'
GLOBAL_CA_CRT_FILE_LOCATION = '/usr/local/share/ca-certificates/nvue'

CA_POOL_FILE = '/etc/ssl/certs/ca-certificates.crt'

EXTERNAL_CA_CRT_FILE_LOCATION = '/usr/local/share/ext/ca-certificates/nvue'

CA_TYPE_EXTERNAL = 'external'
CA_TYPE_GLOBAL = 'global'

from typing import List

from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo

CERT_MGMT_CERTS = '/auto/sw_system_project/NVOS_INFRA/security/verification/cert_mgmt'
TEST_CERTS = '/auto/sw_system_project/NVOS_INFRA/security/verification/certs/test_certs'
GET_SYSTEM_VERSION_PATH = '/nvue_v1/system/version'


class CertMsgs:
    SSL_CERTIFICATE_PROBLEM = 'SSL certificate problem'


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

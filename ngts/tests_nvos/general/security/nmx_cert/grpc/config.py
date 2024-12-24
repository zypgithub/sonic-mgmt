from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.nmx_cert.constants import EncryptionMode, DEFAULT_NMX_C_MGMT_PORT, \
    DEFAULT_NMX_T_MGMT_PORT


class Printable:
    def __str__(self):
        attributes = {name: value.name if isinstance(value, CertInfo) else value for name, value in vars(self).items()
                      if not name.startswith('_')}
        s = '\t' + '\n\t'.join(f'{name}: {value}' for name, value in attributes.items())
        return s


class GrpcPeerConfig(Printable):
    def __init__(self, address: str, tls_mode: str, cert: CertInfo, cacert: CertInfo):
        self.address = address
        self.tls_mode = tls_mode
        self.cert = cert
        self.cacert = cacert


class GrpcServerConfig(GrpcPeerConfig):
    def __init__(self, address: str, port: int, tls_mode: str, cert: CertInfo, cacert: CertInfo, max_workers: int = 10):
        super().__init__(address, tls_mode, cert, cacert)
        self.port = port
        self.max_workers = max_workers


class GrpcClientConfig(GrpcPeerConfig):
    def __init__(self, address: str, tls_mode: str, cert: CertInfo, cacert: CertInfo, num_requests=1,
                 delay_between_requests=1):
        super().__init__(address, tls_mode, cert, cacert)
        self.num_requests = num_requests
        self.delay_between_requests = delay_between_requests


class GrpcConfig:
    def __init__(self, server: GrpcServerConfig, client: GrpcClientConfig):
        super().__init__()
        self.server = server
        self.client = client

    def __str__(self):
        return f'Server Config:\n{self.server}\nClient Config:\n{self.client}'


#######################################################


NMX_C_CONFIG = GrpcConfig(
    server=GrpcServerConfig(
        address='nvos-dut',
        port=DEFAULT_NMX_C_MGMT_PORT,
        tls_mode=EncryptionMode.TLS,
        cert=TestCert.cert_valid_1,
        cacert=TestCert.cert_valid_2,
        max_workers=10
    ),
    client=GrpcClientConfig(
        address='nvos-dut',
        tls_mode=EncryptionMode.TLS,
        cert=TestCert.cert_valid_2,
        cacert=TestCert.cert_valid_1,
        num_requests=3,
        delay_between_requests=1
    )
)

NMX_T_CONFIG = GrpcConfig(
    server=GrpcServerConfig(
        address='nvos-dut',
        port=DEFAULT_NMX_T_MGMT_PORT,
        tls_mode=EncryptionMode.TLS,
        cert=TestCert.cert_valid_1,
        cacert=TestCert.cert_valid_2,
        max_workers=10
    ),
    client=GrpcClientConfig(
        address='nvos-dut',
        tls_mode=EncryptionMode.TLS,
        cert=TestCert.cert_valid_2,
        cacert=TestCert.cert_valid_1,
        num_requests=10,
        delay_between_requests=1
    )
)

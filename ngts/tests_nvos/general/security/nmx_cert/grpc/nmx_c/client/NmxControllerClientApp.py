import time

import grpc

import ngts.tests_nvos.general.security.nmx_cert.grpc.nmx_c.proto.nmx_m_nmx_c_pb2 as pb
import ngts.tests_nvos.general.security.nmx_cert.grpc.nmx_c.proto.nmx_m_nmx_c_pb2_grpc as pb_grpc
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.general.security.helpers import remove_etc_host_mapping_to_dn, add_etc_host_mapping_to_dn
from ngts.tests_nvos.general.security.nmx_cert.constants import EncryptionMode, DEFAULT_NMX_C_MGMT_PORT
from ngts.tests_nvos.general.security.nmx_cert.grpc.config import NMX_C_CONFIG, GrpcConfig, GrpcServerConfig, \
    GrpcClientConfig
from ngts.tests_nvos.general.security.nmx_cert.grpc.utils.logs import standalone_logger


class NmxControllerClientApp:
    def __init__(self, config: GrpcConfig, logger=standalone_logger):
        self.name = 'NMX-C CLIENT'
        self.config = config
        self.logger = logger or standalone_logger

    def run(self) -> str:
        responses = []

        self._log(f'starting client\n{self.config}')
        # Create a channel to the server
        with self._get_channel() as channel:
            self._log('created channel')

            # Create a stub (client)
            client = pb_grpc.NMX_ControllerStub(channel)
            self._log('created grpc client')

            for i in range(self.config.client.num_requests):
                # Create a request message
                request = pb.ClientHello(
                    gatewayId=str(i),
                    major_version=pb.ProtoMsgMajorVersion.PROTO_MSG_MAJOR_VERSION,
                    minor_version=pb.ProtoMsgMinorVersion.PROTO_MSG_MINOR_VERSION
                )
                self._log('created request message')

                # Make the call to the server
                self._log('send grpc request to server: Hello()')
                response = client.Hello(request)
                self._log(f"response from server:\n{response}")
                responses.append(str(response))

                self._log(f'sleep {self.config.client.delay_between_requests} seconds')
                time.sleep(self.config.client.delay_between_requests)

        return '\n'.join(responses)

    def _get_channel(self):
        dial_to = f'{self.config.server.address}:{self.config.server.port}'
        if self.config.client.tls_mode == EncryptionMode.DISABLED:
            return grpc.insecure_channel(dial_to)
        else:
            return grpc.secure_channel(dial_to, self._get_client_ssl_config())

    def _get_client_ssl_config(self):
        with open(self.config.client.cacert.cacert, 'rb') as f:
            cacert = f.read()
        with open(self.config.client.cert.private, 'rb') as f:
            private = f.read()
        with open(self.config.client.cert.public, 'rb') as f:
            public = f.read()

        if self.config.client.tls_mode == EncryptionMode.TLS:
            credentials = grpc.ssl_channel_credentials(
                root_certificates=cacert,
            )
        elif self.config.client.tls_mode == EncryptionMode.MTLS:
            credentials = grpc.ssl_channel_credentials(
                root_certificates=cacert,
                private_key=private,
                certificate_chain=public
            )
        else:
            credentials = None

        return credentials

    def _log(self, msg: str):
        self.logger.info(f'[{self.name}] {msg}')


def run_grpc_client_app(config: GrpcConfig, logger=None) -> str:
    return NmxControllerClientApp(config, logger).run()


def run_nmx_c_grpc_client(config, remote_host_addr='127.0.0.1', logger=None, skip_etc_mapping=False):
    if not skip_etc_mapping:
        remove_etc_host_mapping_to_dn(config.server.address)
        add_etc_host_mapping_to_dn(config.server.address, remote_host_addr)

    return run_grpc_client_app(config, logger)


def local_main():
    run_nmx_c_grpc_client(NMX_C_CONFIG)


def main_with_switch():
    switch_ip = '10.7.148.126'  # TODO: set this to the desired switch ip
    config = GrpcConfig(
        server=GrpcServerConfig(
            address='nvos-dut',
            port=DEFAULT_NMX_C_MGMT_PORT,
            tls_mode=EncryptionMode.MTLS,
            cert=TestCert.cert_valid_1,
            cacert=TestCert.cert_valid_2,
            max_workers=10
        ),
        client=GrpcClientConfig(
            address='nvos-dut',
            tls_mode=EncryptionMode.MTLS,
            cert=TestCert.cert_valid_2,
            cacert=TestCert.cert_valid_1,
            num_requests=2,
            delay_between_requests=1
        )
    )

    run_nmx_c_grpc_client(config, switch_ip)


if __name__ == '__main__':
    # local_main()
    main_with_switch()

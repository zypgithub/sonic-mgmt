from concurrent import futures

import grpc

import ngts.tests_nvos.general.security.nmx_cert.grpc.proto.nmx_m_nmx_c_pb2_grpc as pb_grpc
from ngts.tests_nvos.general.security.nmx_cert.grpc.config import CONFIG, EncryptionMode, GrpcConfig
from ngts.tests_nvos.general.security.nmx_cert.grpc.server.NMX_ControllerServicer import NMX_ControllerServicer
from ngts.tests_nvos.general.security.nmx_cert.grpc.utils.logs import standalone_logger


class ServerApp:
    def __init__(self, config, logger=standalone_logger):
        self.name = 'SERVER'
        self.config = config
        self.logger = logger or standalone_logger

    def run(self):
        self._serve()

    def _serve(self):
        self._log(f'starting server\n{self.config}')

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=self.config.server.max_workers))
        self._log('created grpc server')

        # Add the defined class to the server
        servicer = NMX_ControllerServicer(self.name, self.config, self.logger)
        pb_grpc.add_NMX_ControllerServicer_to_server(servicer, server)
        self._log('added nmx-c servicer to grpc server')

        listening_point = f'[::]:{self.config.server.port}'
        if self.config.server.tls_mode == EncryptionMode.DISABLED:
            server.add_insecure_port(listening_point)
        else:
            server.add_secure_port(listening_point, self._get_server_ssl_config())
        self._log(f'added listening port to server: {listening_point}')

        server.start()
        self._log('server started')

        self._log('waiting for requests/termination')
        server.wait_for_termination()
        self._log('server app terminated')

    def _get_server_ssl_config(self):
        with open(self.config.server.cacert.cacert, 'rb') as f:
            cacert = f.read()
        with open(self.config.server.cert.private, 'rb') as f:
            private = f.read()
        with open(self.config.server.cert.public, 'rb') as f:
            public = f.read()

        if self.config.server.tls_mode == EncryptionMode.TLS:
            server_credentials = grpc.ssl_server_credentials([(private, public)])
        elif self.config.server.tls_mode == EncryptionMode.MTLS:
            server_credentials = grpc.ssl_server_credentials(
                private_key_certificate_chain_pairs=[(private, public)],
                root_certificates=cacert,
                require_client_auth=True
            )
        else:
            server_credentials = None

        return server_credentials

    def _log(self, msg: str):
        self.logger.info(f'[{self.name}] {msg}')


def run_grpc_server_app(config: GrpcConfig, logger=None):
    ServerApp(config, logger).run()


if __name__ == '__main__':
    run_grpc_server_app(CONFIG)

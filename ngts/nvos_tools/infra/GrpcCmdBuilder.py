import json
from typing import Dict


class GrpcCmdBuilder:
    CMD_TEMPLATE = "grpcurl {opts} {host}:{port} {endpoint}"

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.endpoint: str = ''
        self.options: str = ''

    def address(self, address: str) -> 'GrpcCmdBuilder':
        self.host = address
        return self

    def user_creds(self, username: str, password: str) -> 'GrpcCmdBuilder':
        self.options += f" -u {username} -p {password}"
        return self

    def skip_verify(self) -> 'GrpcCmdBuilder':
        self.options += f' -plaintext'
        return self

    def ca(self, cacert_path: str) -> 'GrpcCmdBuilder':
        self.options += f' -cacert {cacert_path}'
        return self

    def cert(self, key_path: str, public_path: str) -> 'GrpcCmdBuilder':
        self.options += f' -key {key_path} -cert {public_path}'
        return self

    def endpoint(self, endpoint: str) -> 'GrpcCmdBuilder':
        self.endpoint = endpoint
        return self

    def payload(self, payload: Dict[str, str]) -> 'GrpcCmdBuilder':
        self.options += f" -d '{json.dumps(payload)}'"
        return self

    def build(self) -> str:
        self.endpoint.strip()
        self.options.strip()
        return GrpcCmdBuilder.CMD_TEMPLATE.format(host=self.host, port=self.port, opts=self.options, endpoint=self.endpoint).strip()

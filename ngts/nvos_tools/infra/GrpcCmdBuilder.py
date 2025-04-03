import json
from typing import Dict, Optional, Union


class GrpcCmdBuilder:
    CMD_TEMPLATE = "grpcurl {opts} {host}:{port} {endpoint}"

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.endpoint_loc: str = ''
        self.options: str = ''

    def address(self, address: str) -> 'GrpcCmdBuilder':
        self.host = address
        return self

    def option(self, key: str, value: Optional[Union[str, int]] = None) -> 'GrpcCmdBuilder':
        """Adds a generic option flag or key-value option. Prefer specific methods where available."""
        self.options += f" -{key}"
        if value is not None:
            self.options += f" {str(value)}"
        return self

    def user_creds(self, username: str, password: str) -> 'GrpcCmdBuilder':
        return self.option("u", username).option("p", password)

    def skip_verify(self) -> 'GrpcCmdBuilder':
        return self.option("plaintext")

    def ca(self, cacert_path: str) -> 'GrpcCmdBuilder':
        return self.option("cacert", cacert_path)

    def cert(self, key_path: str, public_path: str) -> 'GrpcCmdBuilder':
        return self.option("key", key_path).option("cert", public_path)

    def proto(self, proto_path: str) -> 'GrpcCmdBuilder':
        return self.option("proto", proto_path)

    def payload(self, payload: Dict[str, str]) -> 'GrpcCmdBuilder':
        return self.option("d", json.dumps(payload))

    def endpoint(self, endpoint: str) -> 'GrpcCmdBuilder':
        self.endpoint_loc = endpoint
        return self

    def build(self) -> str:
        self.endpoint_loc.strip()
        self.options.strip()
        return GrpcCmdBuilder.CMD_TEMPLATE.format(host=self.host, port=self.port, opts=self.options, endpoint=self.endpoint_loc).strip()

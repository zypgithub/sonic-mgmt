import base64
import json
import os
from typing import Dict, Optional, Union


class GrpcCmdBuilder:
    CMD_TEMPLATE = "grpcurl {rpc_header} {opts} {host}:{port} {endpoint}"

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.endpoint_loc: str = ''
        self.options: str = ''
        self.rpc_header: str = ''

    def address(self, address: str) -> 'GrpcCmdBuilder':
        self.host = address
        return self

    def option(self, key: str, value: Optional[Union[str, int]] = None) -> 'GrpcCmdBuilder':
        """Adds a generic option flag or key-value option. Prefer specific methods where available."""
        self.options += f" -{key}"
        if value is not None:
            self.options += f" {str(value)}"
        return self

    def header(self, value: str) -> 'GrpcCmdBuilder':
        if not self.rpc_header:
            self.rpc_header += f" -rpc-header"
        self.rpc_header += f" '{str(value)}'"
        return self

    def user_creds(self, username: str, password: str) -> 'GrpcCmdBuilder':
        full_creds = f"{username}:{password}"
        encoded_creds = base64.b64encode(full_creds.encode('utf-8')).decode('utf-8')
        return self.header(f"Authorization: Basic {encoded_creds}")

    def skip_verify(self) -> 'GrpcCmdBuilder':
        return self.option("plaintext")

    def ca(self, cacert_path: str) -> 'GrpcCmdBuilder':
        return self.option("cacert", cacert_path)

    def cert(self, key_path: str, public_path: str) -> 'GrpcCmdBuilder':
        return self.option("key", key_path).option("cert", public_path)

    def proto(self, proto_path: str) -> 'GrpcCmdBuilder':
        return self.option("import-path", os.path.dirname(proto_path)).option("proto", proto_path)

    def payload(self, payload: Dict[str, str]) -> 'GrpcCmdBuilder':
        return self.option("d", f"'{json.dumps(payload)}'")

    def endpoint(self, endpoint: str) -> 'GrpcCmdBuilder':
        self.endpoint_loc = endpoint
        return self

    def build(self) -> str:
        self.endpoint_loc.strip()
        self.options.strip()
        self.rpc_header.strip()
        return GrpcCmdBuilder.CMD_TEMPLATE.format(host=self.host, port=self.port, opts=self.options, endpoint=self.endpoint_loc, rpc_header=self.rpc_header).strip()

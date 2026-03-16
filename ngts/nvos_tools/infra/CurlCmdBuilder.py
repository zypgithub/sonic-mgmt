import json

NVUE_RESOURCE_PREFIX = '/nvue_v1'
DEFAULT_PORT = 443


class CurlCmdBuilder:
    CURL_CMD_TEMPLATE = "curl{opts} --request {method} 'https://{host}:{port}{resource}{params}'"

    def __init__(self, method: str, host: str, resource: str, port: int = DEFAULT_PORT, resource_prefix: str = NVUE_RESOURCE_PREFIX):
        self.method: str = method.upper()
        self.host: str = host
        self.port: int = port
        self.resource: str = f'{resource_prefix}{resource}'
        self.options: str = ''
        self.parameters: list = []
        self._is_ipv6: bool = False

    def build(self) -> str:
        self.options.strip()
        params: str = f'?{"&".join(self.parameters)}' if self.parameters else ''
        # IPv6 addresses must be enclosed in square brackets in URLs
        host: str = f'[{self.host}]' if self._is_ipv6 else self.host
        return CurlCmdBuilder.CURL_CMD_TEMPLATE.format(opts=self.options, method=self.method, host=host, port=self.port, resource=self.resource, params=params).strip()

    def ipv6(self) -> 'CurlCmdBuilder':
        """Force curl to use IPv6 and format the host address with brackets."""
        self._is_ipv6 = True
        self.options += ' -6'
        return self

    def insecure(self) -> 'CurlCmdBuilder':
        self.options += ' -k'
        return self

    def user_creds(self, username: str, password: str) -> 'CurlCmdBuilder':
        self.options += f" --user '{username}:{password}'"
        return self

    def resolve(self, dn: str, address: str) -> 'CurlCmdBuilder':
        self.options += f' --resolve {dn}:{self.port}:{address}'
        return self

    def cacert(self, cacert_path: str) -> 'CurlCmdBuilder':
        self.options += f' --cacert {cacert_path}'
        return self

    def client_cert(self, key_path: str, public_path: str) -> 'CurlCmdBuilder':
        self.options += f' --key {key_path} --cert {public_path}'
        return self

    def interface(self, iface: str) -> 'CurlCmdBuilder':
        self.options += f' --interface {iface}'
        return self

    def payload(self, payload: dict) -> 'CurlCmdBuilder':
        self.options += f" -H 'Content-Type: application/json' -d '{json.dumps(payload, separators=(',', ':'))}'"
        return self

    def header(self, header_name: str, header_value: str) -> 'CurlCmdBuilder':
        """Add a custom HTTP header."""
        self.options += f" -H '{header_name}: {header_value}'"
        return self

    def output_file(self, file_path: str) -> 'CurlCmdBuilder':
        """Redirect output body to file using -o option."""
        self.options += f' -o {file_path}'
        return self

    def dump_header(self, file_path: str) -> 'CurlCmdBuilder':
        """Dump protocol headers to file using -D option."""
        self.options += f' -D {file_path}'
        return self

    def param(self, param_name: str, param_val) -> 'CurlCmdBuilder':
        self.parameters.append(f'{param_name}={param_val}')
        return self

    def params(self, params: dict) -> 'CurlCmdBuilder':
        for p, v in params.items():
            self.param(p, v)
        return self

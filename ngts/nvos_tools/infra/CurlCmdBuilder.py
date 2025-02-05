import json

NVUE_RESOURCE_PREFIX = '/nvue_v1'
DEFAULT_PORT = 443


class CurlCmdBuilder:
    CURL_CMD_TEMPLATE = "curl{opts} --request {method} 'https://{host}:{port}{resource}{params}'"

    def __init__(self, method: str, host: str, resource: str, port=DEFAULT_PORT, resource_prefix: str = NVUE_RESOURCE_PREFIX):
        self.method = method.upper()
        self.host = host
        self.port = port
        self.resource = f'{resource_prefix}{resource}'
        self.options: str = ''
        self.parameters: list = []

    def build(self) -> str:
        self.options.strip()
        params = f'?{"&".join(self.parameters)}' if self.parameters else ''
        return CurlCmdBuilder.CURL_CMD_TEMPLATE.format(opts=self.options, method=self.method, host=self.host, port=self.port, resource=self.resource, params=params).strip()

    def insecure(self) -> 'CurlCmdBuilder':
        self.options += f' -k'
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

    def payload(self, payload: dict) -> 'CurlCmdBuilder':
        self.options += f" -H 'Content-Type: application/json' -d '{json.dumps(payload, separators=(',', ':'))}'"
        return self

    def param(self, param_name: str, param_val) -> 'CurlCmdBuilder':
        self.parameters.append(f'{param_name}={param_val}')
        return self

    def params(self, params: dict) -> 'CurlCmdBuilder':
        for p, v in params.items():
            self.param(p, v)
        return self

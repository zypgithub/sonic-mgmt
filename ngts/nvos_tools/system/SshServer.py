from typing import Dict
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
from ngts.nvos_tools.infra.BaseComponent import BaseComponent


class SshServer(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/ssh-server')
        self.trusted_ca_keys = TrustedCaKeys(self)


class TrustedCaKeys(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/trusted-ca-keys')
        self.key_id: Dict[str, TrustedCaKey] = DefaultDict(
            lambda key_id: TrustedCaKey(key_id=key_id, parent=self))


class TrustedCaKey(BaseComponent):
    def __init__(self, key_id: str, parent=None):
        super().__init__(parent=parent, path=f'/{key_id}')

    def set_key_val(self, key: str, apply: bool = False):
        """
        The key value is a string of the public key in PEM format.
        """
        self.set(op_param_name='key', op_param_value=key, apply=apply)

    def set_key_type(self, key_type: str, apply: bool = False):
        """
        The key type is a string of the key type.
        The key type is one of the following:
        - rsa
        - ecdsa
        - ed25519
        - dsa
        - ssh-ed25519
        """
        self.set(op_param_name='type', op_param_value=key_type, apply=apply)

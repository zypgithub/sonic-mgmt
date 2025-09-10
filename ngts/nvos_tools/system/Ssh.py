import logging
from typing import Dict

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DefaultDict import DefaultDict

logger = logging.getLogger()


class Ssh(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/ssh')
        self.authorized_key = AuthorizedKey(self)
        self.cert_auth = CertAuth(self)


class AuthorizedKey(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/authorized-key')
        self.key_id: Dict[str, BaseComponent] = DefaultDict(
            lambda key_id: BaseComponent(parent=self, path=f'/{key_id}'))


class CertAuth(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/cert-auth')
        self.principals: Dict[str, Principal] = DefaultDict(lambda spiffe: Principal(self, spiffe))

    def enable_state(self, apply: bool = False):
        self.set(op_param_name='state', op_param_value='enabled', apply=apply)

    def disable_state(self, apply: bool = False):
        self.set(op_param_name='state', op_param_value='disabled', apply=apply)


class Principal(BaseComponent):
    def __init__(self, parent_obj=None, principal: str = ""):
        super().__init__(parent=parent_obj, path="/principals/" + principal)

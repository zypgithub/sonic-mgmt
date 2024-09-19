from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.system.Authentication import Authentication
from ngts.nvos_tools.system.Ldap import Ldap
from ngts.nvos_tools.system.RemoteAaaResource import RemoteAaaResource
from ngts.nvos_tools.system.Tacacs import Tacacs
from ngts.nvos_tools.system.User import User


class Aaa(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/aaa')
        self.user = User(self)
        self.role = BaseComponent(self, path='/role')
        self.radius = RemoteAaaResource(self, '/radius')
        self.ldap = Ldap(self)
        self.tacacs = Tacacs(self)
        self.authentication = Authentication(self)

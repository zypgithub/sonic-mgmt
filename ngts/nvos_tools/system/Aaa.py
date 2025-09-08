from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.system.Authentication import Authentication
from ngts.nvos_tools.system.Ldap import Ldap
from ngts.nvos_tools.system.RbacClass import RbacClass
from ngts.nvos_tools.system.RemoteAaaResource import RemoteAaaResource
from ngts.nvos_tools.system.Role import Role
from ngts.nvos_tools.system.Tacacs import Tacacs
from ngts.nvos_tools.system.User import User


class Aaa(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/aaa')
        self.user = User(self)
        self.role = Role(self)
        self.class_rbac = RbacClass(self)
        self.radius = RemoteAaaResource(self, '/radius')
        self.ldap = Ldap(self)
        self.tacacs = Tacacs(self)
        self.authentication = Authentication(self)
        self.allow_reset_local_passwords = BaseComponent(self, path='/allow-reset-local-passwords')

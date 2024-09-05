from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.system.CaCertificate import CaCertificate
from ngts.nvos_tools.system.Certificate import Certificate
from ngts.nvos_tools.system.PasswordHardening import PasswordHardening
from ngts.nvos_tools.system.Tpm import Tpm


class Security(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path='/security')
        self.password_hardening = PasswordHardening(self)
        self.certificate = Certificate(self)
        self.ca_certificate = CaCertificate(self)
        self.tpm = Tpm(self)

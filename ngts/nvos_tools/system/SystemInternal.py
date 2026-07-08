"""
System Internal component for nv action update system internal commands.
Handles internal encryption settings for system-wide communications.
"""

import logging

from ngts.nvos_constants.constants_nvos import ActionConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.ResultObj import ResultObj

logger = logging.getLogger(__name__)


class SystemInternal(BaseComponent):
    """System internal encryption settings component."""

    def __init__(self, parent=None):
        super().__init__(parent=parent, path="/internal")
        self.certificate = SystemInternalCertificate(self, "/certificate")
        self.ca_certificate = SystemInternalCertificate(self, "/ca-certificate")
        self.alternate_certificate = SystemInternalCertificate(self, "/alternate-certificate")
        self.encryption = SystemInternalEncryption(self)
        self.crl = SystemInternalCrl(self)
        self.connections = SystemInternalConnections(self)

    def action_restore(self, dut_engine=None) -> ResultObj:
        """Restore system internal to defaults."""
        return self.action(ActionConsts.RESTORE, engine=dut_engine)


class SystemInternalCertificate(BaseComponent):
    """System internal certificate component for action update operations."""

    def __init__(self, parent, path):
        super().__init__(parent=parent, path=path)
        self.is_ca = "ca-certificate" in path

    def action_update(self, cert_id="", dut_engine=None) -> ResultObj:
        """Update system internal certificate."""
        param_name = f"{'ca' if self.is_ca else ''}cert-id"
        return self.action(ActionConsts.UPDATE, main_param=(param_name, cert_id), engine=dut_engine)

    def action_restore(self, dut_engine=None) -> ResultObj:
        """Restore system internal certificate to default."""
        return self.action(ActionConsts.RESTORE, engine=dut_engine)

    def action_rotate(self, dut_engine=None) -> ResultObj:
        """Rotate system internal certificate."""
        return self.action(ActionConsts.ROTATE, engine=dut_engine)


class SystemInternalEncryption(BaseComponent):
    """System internal encryption mode component."""

    def __init__(self, parent):
        super().__init__(parent=parent, path="/encryption")

    def action_update(self, mode="", dut_engine=None) -> ResultObj:
        """Update system internal encryption mode."""
        return self.action(ActionConsts.UPDATE, main_param=('mode', mode), engine=dut_engine)

    def action_restore(self, dut_engine=None) -> ResultObj:
        """Restore system internal encryption to default."""
        return self.action(ActionConsts.RESTORE, engine=dut_engine)


class SystemInternalCrl(BaseComponent):
    """System internal CRL component."""

    def __init__(self, parent):
        super().__init__(parent=parent, path="/crl")

    def action_update(self, crl_id="", dut_engine=None) -> ResultObj:
        """Update system internal CRL."""
        return self.action(ActionConsts.UPDATE, main_param=('crl-id', crl_id), engine=dut_engine)

    def action_restore(self, dut_engine=None) -> ResultObj:
        """Restore system internal CRL."""
        return self.action(ActionConsts.RESTORE, engine=dut_engine)


class SystemInternalConnections(BaseComponent):
    """System internal connections component for reset action."""

    def __init__(self, parent):
        super().__init__(parent=parent, path="/connections")

    def action_reset(self, dut_engine=None) -> ResultObj:
        """Reset system internal connections."""
        return self.action(ActionConsts.RESET, engine=dut_engine)

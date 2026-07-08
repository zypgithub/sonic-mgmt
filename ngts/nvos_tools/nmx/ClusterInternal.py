from ngts.nvos_constants.constants_nvos import ActionConsts
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.ResultObj import ResultObj


class ClusterInternal(BaseComponent):
    def __init__(self, parent=None):
        super().__init__(parent=parent, path="/internal")
        self.certificate = ClusterInternalCertificate(self, "/certificate")
        self.ca_certificate = ClusterInternalCertificate(self, "/ca-certificate")
        self.alternate_certificate = ClusterInternalCertificate(self, "/alternate-certificate")
        self.encryption = ClusterInternalEncryption(self)
        self.crl = ClusterInternalCrl(self)
        self.connections = ClusterInternalConnections(self)

    def action_update(self, state: str = "", dut_engine=None) -> ResultObj:
        return self.action(ActionConsts.UPDATE, main_param=('state', state), engine=dut_engine)

    def action_restore(self, dut_engine=None) -> ResultObj:
        return self.action(ActionConsts.RESTORE, engine=dut_engine)


class ClusterInternalCertificate(BaseComponent):
    def __init__(self, parent, path):
        super().__init__(parent=parent, path=path)
        self.is_ca = "ca-certificate" in path

    def action_update(self, cert_id="", dut_engine=None) -> ResultObj:
        param_name = f"{'ca' if self.is_ca else ''}cert-id"
        return self.action(ActionConsts.UPDATE, main_param=(param_name, cert_id), engine=dut_engine)

    def action_restore(self, dut_engine=None) -> ResultObj:
        return self.action(ActionConsts.RESTORE, engine=dut_engine)

    def action_rotate(self, dut_engine=None) -> ResultObj:
        return self.action(ActionConsts.ROTATE, engine=dut_engine)


class ClusterInternalEncryption(BaseComponent):
    def __init__(self, parent):
        super().__init__(parent=parent, path="/encryption")

    def action_update(self, mode="", dut_engine=None) -> ResultObj:
        return self.action(ActionConsts.UPDATE, main_param=('mode', mode), engine=dut_engine)

    def action_restore(self, dut_engine=None) -> ResultObj:
        return self.action(ActionConsts.RESTORE, engine=dut_engine)


class ClusterInternalCrl(BaseComponent):
    def __init__(self, parent):
        super().__init__(parent=parent, path="/crl")

    def action_update(self, crl_id="", dut_engine=None) -> ResultObj:
        return self.action(ActionConsts.UPDATE, main_param=('crl-id', crl_id), engine=dut_engine)

    def action_restore(self, dut_engine=None) -> ResultObj:
        return self.action(ActionConsts.RESTORE, engine=dut_engine)


class ClusterInternalConnections(BaseComponent):
    """Cluster app internal connections component for reset action."""

    def __init__(self, parent):
        super().__init__(parent=parent, path="/connections")

    def action_reset(self, dut_engine=None) -> ResultObj:
        """Reset cluster app internal connections."""
        return self.action(ActionConsts.RESET, engine=dut_engine)

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool


class ClusterInternal(BaseComponent):
    def __init__(self, parent=None):
        super().__init__(parent=parent, path="/internal")
        self.certificate = ClusterInternalCertificate(self, "/certificate")
        self.ca_certificate = ClusterInternalCertificate(self, "/ca-certificate")
        self.alternate_certificate = ClusterInternalCertificate(self, "/alternate-certificate")
        self.encryption = ClusterInternalEncryption(self)
        self.connections = ClusterInternalConnections(self)

    def action_update(self, state: str = "", dut_engine=None) -> ResultObj:
        with allure.step(f"Execute action update for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            res = SendCommandTool.execute_command(
                self._cli_wrapper.action_update_cluster_manager_property,
                engine,
                self.get_resource_path(),
                "state",
                state,
            )
            return res

    def action_restore(self, dut_engine=None) -> ResultObj:
        with allure.step(f"Execute action restore for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_restore_cluster_manager_property,
                engine,
                self.get_resource_path(),
            )


class ClusterInternalCertificate(BaseComponent):
    def __init__(self, parent, path):
        super().__init__(parent=parent, path=path)
        self.is_ca = "ca-certificate" in path

    def action_update(self, cert_id="", dut_engine=None) -> ResultObj:
        with allure.step(f"Execute action update for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_update_cluster_manager_property,
                engine,
                self.get_resource_path(),
                f"{'ca' if self.is_ca else ''}cert-id",
                cert_id,
            )

    def action_restore(self, dut_engine=None) -> ResultObj:
        with allure.step(f"Execute action restore for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_restore_cluster_manager_property,
                engine,
                self.get_resource_path(),
            )

    def action_rotate(self, dut_engine=None) -> ResultObj:
        with allure.step(f"Execute action rotate for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_rotate_cluster_manager_property,
                engine,
                self.get_resource_path(),
            )


class ClusterInternalEncryption(BaseComponent):
    def __init__(self, parent):
        super().__init__(parent=parent, path="/encryption")

    def action_update(self, mode="", dut_engine=None) -> ResultObj:
        with allure.step(f"Execute action update for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_update_cluster_manager_property,
                engine,
                self.get_resource_path(),
                "mode",
                mode,
            )

    def action_restore(self, dut_engine=None) -> ResultObj:
        with allure.step(f"Execute action restore for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_restore_cluster_manager_property,
                engine,
                self.get_resource_path(),
            )


class ClusterInternalConnections(BaseComponent):
    """Cluster app internal connections component for reset action."""

    def __init__(self, parent):
        super().__init__(parent=parent, path="/connections")

    def action_reset(self, dut_engine=None) -> ResultObj:
        """Reset cluster app internal connections."""
        with allure.step(f"Execute action reset for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(self._cli_wrapper.action_reset, engine, self.get_resource_path())

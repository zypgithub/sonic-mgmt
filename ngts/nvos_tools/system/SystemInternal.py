"""
System Internal component for nv action update system internal commands.
Handles internal encryption settings for system-wide communications.
"""

import logging

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool

logger = logging.getLogger(__name__)


class SystemInternal(BaseComponent):
    """System internal encryption settings component."""

    def __init__(self, parent=None):
        super().__init__(parent=parent, path="/internal")
        self.certificate = SystemInternalCertificate(self, "/certificate")
        self.ca_certificate = SystemInternalCertificate(self, "/ca-certificate")
        self.alternate_certificate = SystemInternalCertificate(self, "/alternate-certificate")
        self.encryption = SystemInternalEncryption(self)
        self.connections = SystemInternalConnections(self)

    def action_restore(self, dut_engine=None) -> ResultObj:
        """Restore system internal to defaults."""
        with allure.step(f"Execute action restore for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_restore_system_internal_property, engine, self.get_resource_path()
            )


class SystemInternalCertificate(BaseComponent):
    """System internal certificate component for action update operations."""

    def __init__(self, parent, path):
        super().__init__(parent=parent, path=path)
        self.is_ca = "ca-certificate" in path

    def action_update(self, cert_id="", dut_engine=None) -> ResultObj:
        """Update system internal certificate."""
        with allure.step(f"Execute action update for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            param_name = f'{"ca" if self.is_ca else ""}cert-id'
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_update_system_internal_property, engine, self.get_resource_path(), param_name, cert_id
            )

    def action_restore(self, dut_engine=None) -> ResultObj:
        """Restore system internal certificate to default."""
        with allure.step(f"Execute action restore for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_restore_system_internal_property, engine, self.get_resource_path()
            )

    def action_rotate(self, dut_engine=None) -> ResultObj:
        """Rotate system internal certificate."""
        with allure.step(f"Execute action rotate for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_rotate_system_internal_property,
                engine,
                self.get_resource_path(),
            )


class SystemInternalEncryption(BaseComponent):
    """System internal encryption mode component."""

    def __init__(self, parent):
        super().__init__(parent=parent, path="/encryption")

    def action_update(self, mode="", dut_engine=None) -> ResultObj:
        """Update system internal encryption mode."""
        with allure.step(f"Execute action update for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_update_system_internal_property, engine, self.get_resource_path(), "mode", mode
            )

    def action_restore(self, dut_engine=None) -> ResultObj:
        """Restore system internal encryption to default."""
        with allure.step(f"Execute action restore for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action_restore_system_internal_property, engine, self.get_resource_path()
            )


class SystemInternalConnections(BaseComponent):
    """System internal connections component for reset action."""

    def __init__(self, parent):
        super().__init__(parent=parent, path="/connections")

    def action_reset(self, dut_engine=None) -> ResultObj:
        """Reset system internal connections."""
        with allure.step(f"Execute action reset for {self.get_resource_path()}"):
            engine = dut_engine or TestToolkit.engines.dut
            return SendCommandTool.execute_command(
                self._cli_wrapper.action, engine, action_str="reset", resource_path=self.get_resource_path()
            )

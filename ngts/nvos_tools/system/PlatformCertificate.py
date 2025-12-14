import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


class PlatformCertificate(BaseComponent):
    """
    Component for TCG Platform Certificate Profile operations.

    Supports:
    - nv show system security platform-certificate
    - nv action upload system security platform-certificate <remote-url>
    """

    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/platform-certificate")

    def action_upload(self, remote_url: str, expected_str: str = "", dut_engine=None) -> ResultObj:
        """
        Upload platform certificate to a remote server.

        Args:
            remote_url: Remote server URL (scp://user:pass@host/path/file,
                       https://..., sftp://...)
            expected_str: Optional expected string in output
            dut_engine: Optional engine override

        Returns:
            ResultObj with operation result
        """
        with allure.step(f"Execute action upload for {self.get_resource_path()}"):
            engine = dut_engine if dut_engine else TestToolkit.engines.dut
            return SendCommandTool.execute_command_expected_str(
                self._cli_wrapper.action_upload_platform_certificate, expected_str, engine, self.get_resource_path(), remote_url
            )

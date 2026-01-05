import logging

from ngts.nvos_constants.constants_nvos import ActionConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.system.Files import Files
from ngts.tools.test_utils import allure_utils as allure


class Debug(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/debug")
        self.info = Info(self)
        self.token = Token(self)


class Token(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/token")
        self.debug_image = DebugTokenComponent(self, 'debug-image')
        self.customer_support = DebugTokenComponent(self, 'customer-support')


class Info(BaseComponent):
    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/info")
        self.debug_image = DebugImageInfo(self)
        self.debug_image_bmc = DebugImageBmcInfo(self)
        self.customer_support = CustomerSupportInfo(self)


# ==================== CRCS (Customer Support) Info Component ====================

class CustomerSupportInfo(BaseComponent):
    """CRCS token info component - customer-support."""

    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/customer-support")
        self.files = Files(self)

    def action_generate(self, engine=None, name="", test_name=''):
        """
        Generate CRCS token info file.

        Command: nv action generate fae platform debug info customer-support <name>

        Args:
            engine: DUT engine (optional)
            name: Name for the generated token info file (.xml)
            test_name: Test name for tracking

        Returns:
            ResultObj: Command result
        """
        with allure.step(f'Generate CRCS token info: {name}'):
            engine = engine or TestToolkit.engines.dut
            resource_path = self.get_resource_path()

            cmd_info, duration = OperationTime.save_duration(
                'generate customer-support', name, test_name,
                SendCommandTool.execute_command,
                self.api_obj[TestToolkit.tested_api].action_generate,
                engine, resource_path, name
            )

            logging.info(f"Generating CRCS token took {duration} seconds")
            return cmd_info

    def action_delete_all(self):
        """Delete all CRCS token info files."""
        with allure.step("Delete all CRCS token info files"):
            return self.action_deprecated(ActionConsts.DELETE, 'files')


# ==================== CRDT (Debug Image) Info Component - ASIC/QTM4 ====================

class DebugImageInfo(BaseComponent):
    """CRDT token info component - debug-image (ASIC/QTM4)."""

    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/debug-image")
        self.files = Files(self)

    def action_delete_all(self):
        """Delete all CRDT token info files."""
        with allure.step("Delete all CRDT token info files"):
            return self.action_deprecated(ActionConsts.DELETE, 'files')


# ==================== Debug Image BMC Info Component ====================

class DebugImageBmcInfo(BaseComponent):
    """Debug image info component for BMC-based debug tokens."""

    def __init__(self, parent_obj=None):
        super().__init__(parent=parent_obj, path="/debug-image")
        self.files = Files(self)
        self.component_name = 'debug-image'

    def action_generate(self, engine=None, name="", test_name='', should_succeed=True):
        """
        Generate debug-image token info file (BMC).

        Command: nv action generate fae platform debug info debug-image <name>

        Args:
            engine: DUT engine (optional)
            name: Name for the generated token info file (.bin)
            test_name: Test name for tracking
            should_succeed: Whether the command should succeed

        Returns:
            ResultObj: Command result
        """
        with allure.step(f'Generate {self.component_name}: {name}'):
            if not engine:
                engine = TestToolkit.get_engine()

            cmd_info, duration = OperationTime.save_duration(
                f'generate {self.component_name}', name, test_name,
                SendCommandTool.execute_command,
                self.api_obj[TestToolkit.tested_api].action_generate,
                engine, self.get_resource_path(), name
            )

            logging.info(f"Generating debug token took {duration} seconds")
            cmd_info.verify_result(should_succeed)

    def action_delete_all(self):
        """Delete all debug-image BMC token info files."""
        with allure.step(f"Delete all files of {self.component_name}"):
            return self.action_deprecated(ActionConsts.DELETE, 'files')


# ==================== Token Component (for both CRCS and CRDT) ====================

class DebugTokenComponent(BaseComponent):
    """Debug token component for install/uninstall operations."""

    def __init__(self, parent_obj=None, component_name=None):
        super().__init__(parent=parent_obj, path=f"/{component_name}")
        self.files = Files(self)
        self.asic = BaseComponent(self, path='/asic')
        self.component_name = component_name

    def action_uninstall(self, params="", expected_str="", engine=None):
        """
        Uninstall debug token.

        Command: nv action uninstall fae platform debug token {debug-image | customer-support}

        Returns:
            ResultObj: Command result
        """
        with allure.step(f"Uninstall {self.component_name} token"):
            return self.action(ActionConsts.UNINSTALL, flags=params, expected_output=expected_str, engine=engine)

    def action_delete_all(self):
        """nv action delete fae platform debug token {debug-image | customer-support} files"""
        with allure.step(f"Delete all files of {self.component_name}"):
            return self.action_deprecated(ActionConsts.DELETE, 'files')

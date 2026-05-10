import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DutUtilsTool import RebootParams
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class RebootHistory(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/history')

    def filter(self, filter_name="", value="", dut_engine=None, exempted_err_msgs=None):
        """Run `nv show system reboot history --filter <name>=<value>` (NVUE) or
        the equivalent `?filter=<name>%3d<value>` REST query (OpenAPI).
        Returns a ResultObj whose returned_value is the raw JSON string."""
        if not dut_engine:
            dut_engine = TestToolkit.get_engine()
        with allure.step(f"filter {self.get_resource_path()} using {filter_name}={value}"):
            return SendCommandTool.execute_command(
                self._cli_wrapper.filter, dut_engine, self.get_resource_path(),
                filter_name, value,
                exempted_err_msgs=exempted_err_msgs or (),
            )


# todo: remove this entire file, instead set System.reboot = BaseComponent
class Reboot(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/reboot')
        self.reason = BaseComponent(self, path='/reason')
        self.history = RebootHistory(self)
        self.counters = BaseComponent(self, path='/counters')

    def action_reboot(self, engine=None, device=None, params="", should_wait_till_system_ready=True,
                      recovery_engine=None, topology_obj=None, system_is_ready_timeout=None, check_system_is_functional=None, send_user_confirmation=None):
        return self.parent_obj.action_reboot(params, engine=engine, device=device, reboot_params=RebootParams(
            should_wait_till_system_ready=should_wait_till_system_ready,
            recovery_engine=recovery_engine,
            topology_obj=topology_obj or TestToolkit.topology_obj,
            system_is_ready_timeout=system_is_ready_timeout,
            check_system_is_functional=check_system_is_functional), send_user_confirmation=send_user_confirmation)

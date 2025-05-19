import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.DutUtilsTool import RebootParams
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


# todo: remove this entire file, instead set System.reboot = BaseComponent
class Reboot(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/reboot')
        self.reason = BaseComponent(self, path='/reason')
        self.history = BaseComponent(self, path='/history')

    def action_reboot(self, engine=None, device=None, params="", should_wait_till_system_ready=True,
                      recovery_engine=None, topology_obj=None, system_is_ready_timeout=None):
        return self.parent_obj.action_reboot(params, engine=engine, device=device, reboot_params=RebootParams(
            should_wait_till_system_ready=should_wait_till_system_ready,
            recovery_engine=recovery_engine,
            topology_obj=topology_obj or TestToolkit.topology_obj,
            system_is_ready_timeout=system_is_ready_timeout))

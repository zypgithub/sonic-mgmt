import logging
import os
import time

import pytest

from ngts.constants.constants import InfraConst
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.scripts.check_and_store_sanitizer_dump import check_sanitizer_and_store_dump
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


class Reboot(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/reboot')

    def action_reboot(self, engine=None, device=None, params="", should_wait_till_system_ready=True, recovery_engine=None, topology_obj=None, system_is_ready_timeout=None):
        with allure.step('Execute action for {resource_path}'.format(resource_path=self.get_resource_path())):
            if not engine:
                engine = TestToolkit.engines.dut
            if not device:
                device = TestToolkit.devices.dut

            start_time = time.time()
            res_obj = SendCommandTool.execute_command(self.api_obj[TestToolkit.tested_api].action_reboot,
                                                      engine, device, self.get_resource_path().replace('/reboot', ' '),
                                                      params, should_wait_till_system_ready, recovery_engine, topology_obj, system_is_ready_timeout)
            end_time = time.time()
            duration = end_time - start_time

            with allure.step("Reboot and system is ready takes {} seconds".format(duration)):
                logger.info("Reboot and system is ready takes {} seconds".format(duration))

            if pytest.is_sanitizer:
                dumps_folder = os.environ.get(InfraConst.ENV_LOG_FOLDER)
                check_sanitizer_and_store_dump(engine, dumps_folder, pytest.test_name)

            return res_obj

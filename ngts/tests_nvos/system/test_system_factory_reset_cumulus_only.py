import random

import pytest
import logging

from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.system.factory_reset.helpers import verify_the_setup_is_functional
from ngts.tests_nvos.system.factory_reset.post_steps import factory_reset_system_message_post_steps
from ngts.tests_nvos.system.factory_reset.pre_steps import factory_reset_system_message_pre_steps
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.system.System import System
from ngts.cli_wrappers.nvue.cumulus.cumulus_general_cli import CumulusGeneralCli

logger = logging.getLogger()


@pytest.mark.timeout(50 * MINUTE)
@pytest.mark.system
@pytest.mark.checklist
@pytest.mark.reset_factory
@pytest.mark.cumulus_only
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_reset_factory_system_message(engines, devices, test_api, test_name, serial_log_analyzers):
    serial_analyzer, = serial_log_analyzers.values()
    TestToolkit.tested_api = test_api
    system = System()

    with allure.step('pre factory reset steps'):
        health_status, current_time, username = factory_reset_system_message_pre_steps(engines, devices, system)

    with allure.step("Run reset factory with system message params"):
        with serial_analyzer.stage('Reset-factory'):
            duration = execute_reset_factory(engines, devices, system, devices.dut.reset_factory, "keep basic", current_time, test_name=test_name)

    with allure.step('post factory reset system message steps'):
        factory_reset_system_message_post_steps(engines, devices, system)

    with allure.step("Verify the setup is functional"):
        verify_the_setup_is_functional(system, engines)


def execute_reset_factory(engines, devices, system, operation, flag, current_time, topology_obj=None, test_name=''):
    logging.info("Current time: " + str(current_time))
    topology_obj = topology_obj or (TestToolkit.topology_obj if TestToolkit else None)
    result_obj = system.factory_default.action_reset(operation=operation, param=flag, topology_obj=topology_obj, test_name=test_name)
    result_obj.verify_result()
    return result_obj.duration

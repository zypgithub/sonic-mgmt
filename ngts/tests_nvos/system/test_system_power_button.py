import logging

import pytest

from infra.tools.redmine.redmine_api import is_redmine_issue_active
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.system.test_system_reboot import validate_reboot_reason_and_user
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.nvos_constants.constants_nvos import SystemConsts, RebootConsts

logger = logging.getLogger()


@pytest.mark.bmc
def test_system_power_button(engines, topology_obj):
    """
    Test cover juliet power button functionality
        Test flow:
            1. simulate power button and check switch going down
            2. recover switch with remote reboot
            3. check reboot reason
    """
    system = System()
    expected_reason, expected_user = RebootConsts.REBOOT_REASON_MAP[RebootConsts.POWER_BUTTON]

    try:
        with allure.step('Simulate power button and check switch is down'):
            _simulate_power_button_press(engines)
            check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)

    finally:
        with allure.step('Recover system with remote reboot'):
            recover_dut_with_remote_reboot(topology_obj, engines)

        if not is_redmine_issue_active([4003176][0]):
            with allure.step('Check reboot reason'):
                reboot_output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.show())\
                    .get_returned_value()
                assert RebootConsts.POWER_BUTTON in reboot_output['reason'], \
                    "Expected reason: power button is not observed: {0}".format(reboot_output['reason'])

            validate_reboot_reason_and_user(system, expected_reason, expected_user)


def _simulate_power_button_press(engines):
    engines.dut.run_cmd('sudo touch /var/run/hw-management/events/power_button')
    engines.dut.run_cmd('sudo chmod 777 /var/run/hw-management/events/power_button')
    engines.dut.run_cmd('sudo service power-mgmt restart')
    engines.dut.run_cmd('sudo echo 1 > /var/run/hw-management/events/power_button')

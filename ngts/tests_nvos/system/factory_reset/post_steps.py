from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tools.test_utils import allure_utils as allure


def factory_reset_no_params_post_steps(apply_and_save_port, engines, just_apply_port, last_status_line, machine_type,
                                       not_apply_port, system):
    with allure.step('update timezone'):
        update_timezone(system)
    if machine_type != 'MQM9520':
        with allure.step("Validate health status and report"):
            validate_health_status_report(system, last_status_line)
    with allure.step("Verify description has been deleted"):
        validate_port_description(engines.dut, apply_and_save_port, "")
        validate_port_description(engines.dut, just_apply_port, "")
        validate_port_description(engines.dut, not_apply_port, "")

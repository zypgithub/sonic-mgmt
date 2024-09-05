from ngts.tests_nvos.general.security.tpm_attestation.helpers import factory_reset_tpm_checker
from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tests_nvos.system.gnmi.helpers import factory_reset_gnmi_checker
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
    with allure.step('pre factory reset security checks'):
        post_factory_reset_security_checks()


def post_factory_reset_security_checks():
    with allure.step('TPM check'):
        next(factory_reset_tpm_checker)
    with allure.step('GNMI cert check'):
        next(factory_reset_gnmi_checker)

import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.tools.test_utils import allure_utils as allure


def configure_resource(engines, resource_obj: BaseComponent, conf, apply=False, verify_apply=True, dut_engine=None):
    """
    @summary: Configure resource according to the given desired configuration
        * Configuration example:
            if we want:
            ldap
                bind-dn = abc
                auth-port = 123
            then configuration dictionary should be:
            {
                bind-dn: abc,
                auth-port: 123
            }
    @param engines: engines object
    @param resource_obj: resource object
    @param conf: the desired configuration (dictionary)
    @param apply: whether to apply the changes or not
    @param verify_apply: whether to verify the apply or not
    @param dut_engine: engine to run the set commands on (optional)
    """
    if not conf:
        return

    with allure.step(f'Set configuration for resource: {resource_obj.get_resource_path()}'):
        logging.info(f'Given configuration to set:\n{conf}')

        with allure.step('Set fields'):
            for key, value in conf.items():
                logging.info(f'Set field "{key}" to value "{value}"')
                value = int(value) if isinstance(value, int) or isinstance(value, str) and value.isnumeric() else value
                if not dut_engine:
                    resource_obj.set(key, value, apply=False).verify_result()
                else:
                    resource_obj.set(key, value, apply=False, dut_engine=dut_engine).verify_result()

        if apply:
            with allure.step('Apply changes'):
                if not dut_engine:
                    res = SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config,
                                                          engines.dut, True)
                else:
                    res = SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config,
                                                          dut_engine, True)
                if verify_apply:
                    res.verify_result()
                else:
                    res.ignore_result()

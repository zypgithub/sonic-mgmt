import pytest
from retry import retry

from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Tools import Tools

logger = logging.getLogger()


@retry(AssertionError, tries=10, delay=2)
def _wait_for_autoconf_value(ipoib_port, expected_value):
    """Wait for autoconf configuration to be applied with retry."""
    ip_dict = OutputParsingTool.parse_json_str_to_dictionary(ipoib_port.interface.ipv6.show()).verify_result()
    Tools.ValidationTool.verify_field_value_in_output(
        ip_dict, IbInterfaceConsts.AUTOCONFIG, expected_value).verify_result()


@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_autoconfig_disabled_sm(engines, topology_obj, stop_sm, random_api, test_name):
    """
    Verify default autoconf  (disable), check that we can configure possible value (enable).
    and we can unset the configuration

    flow:
    1. Check default values disable - nv show interface <param1> ip
    2. Configure autoconf (enable)
    3. Unset autoconf, check default value
    """
    TestToolkit.tested_api = random_api

    ipoib_port = Port('ib0')
    with allure.step('verify the default ib0 autoconf value is {value}'.format(
            value=IbInterfaceConsts.IB0_IP_AUTOCONF_DEFAULT_VALUE)):
        ip_dict = OutputParsingTool.parse_json_str_to_dictionary(ipoib_port.interface.ipv6.show()).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(
            ip_dict, IbInterfaceConsts.AUTOCONFIG, IbInterfaceConsts.IB0_IP_AUTOCONF_DEFAULT_VALUE).verify_result()

    new_value = 'enabled'
    with allure.step('Set autoconf = {value} for ib0'.format(value=new_value)):
        result_obj, duration = OperationTime.save_duration(
            'set ib0 autoconf', new_value, test_name,
            ipoib_port.interface.ipv6.set,
            op_param_name='autoconf', op_param_value=new_value, apply=True, ask_for_confirmation=True)
        logger.info(f"Setting autoconf to '{new_value}' took {duration:.2f} seconds")
        _wait_for_autoconf_value(ipoib_port, new_value)

    with allure.step('Unset autoconf for ib0'):
        result_obj, duration = OperationTime.save_duration(
            'unset ib0 autoconf', '', test_name,
            ipoib_port.interface.ipv6.unset,
            op_param='autoconf', apply=True, ask_for_confirmation=True)
        logger.info(f"Unsetting autoconf took {duration:.2f} seconds")
        _wait_for_autoconf_value(ipoib_port, IbInterfaceConsts.IB0_IP_AUTOCONF_DEFAULT_VALUE)

import pytest
import random
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.ib.InterfaceConfiguration.MgmtPort import MgmtPort
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import *
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType

logger = logging.getLogger()


@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_mtu_disabled_sm(engines, stop_sm):
    """
    Verify default mtu configuration(2044), check that we can configure possible values (252, 508, 1020, 2044, 4092).
    negative check random value, check changes, unset it to default

    flow:
    1. Check default values
    2. Negative testing
    3. Configure possible mtu
    4. Unset mtu, check default value
    """

    ipoib_port = MgmtPort('ib0')
    possible_values = [4092]
    with allure.step('pick random mtu value out of {possible_values}'.format(possible_values=possible_values)):
        random_mtu = random.choice(possible_values)
        logger.info('the random mtu is {val}'.format(val=random_mtu))

    with allure.step('Run show command on ib0 and verify mtu default value is {value}'.format(
            value=IbInterfaceConsts.IB0_LINK_MTU_DEFAULT_VALUE)):
        ipoib_port.interface.wait_for_mtu_changed(IbInterfaceConsts.IB0_LINK_MTU_DEFAULT_VALUE)

    with allure.step('Set validation with supported for ib0 mtu {random}'.format(random=random_mtu)):
        ipoib_port.interface.link.set(op_param_name='mtu', op_param_value=random_mtu, apply=True,
                                      ask_for_confirmation=True).verify_result()
        logger.info('Check port status, should be up')
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        ipoib_port.interface.wait_for_mtu_changed(random_mtu)

    with allure.step('Negative validation - not supported ib0 mtu value: 500'):
        ipoib_port.interface.link.set(op_param_name='mtu', op_param_value=500, apply=True).verify_result(False)
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        logger.info('Check port status, should be up')
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        ipoib_port.interface.wait_for_mtu_changed(random_mtu)

    with allure.step('Unset mtu validation'):
        ipoib_port.interface.link.unset(op_param='mtu', apply=True, ask_for_confirmation=True).verify_result()
        logger.info('Check port status, should be up')
        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
        ipoib_port.interface.wait_for_mtu_changed(IbInterfaceConsts.IB0_LINK_MTU_DEFAULT_VALUE)


@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_arp_timeout_disabled_sm(stop_sm):
    """
    Verify default arp timeout (1800 sec), check that we can configure possible values (60-28800).
    negative check random value, unset it to default

    flow:
    1. Check default values 1800 - nv show interface <param1> ip arp-timeout
    2. Negative testing less than 60 or more than 28800 or negative
    3. Configure possible timeout  60-28800
    4. Unset arp timeout, check default value
    """

    ipoib_port = MgmtPort('ib0')
    with allure.step('pick random valid and invalid arp-timeout values'):
        random_valid_timeout = random.randint(60, 28800)
        random_invalid_timeout = random.randint(0, 59)
        random_invalid_timeout_neg = random.randint(-100, -1)
        random_invalid_timeout_max = random.randint(28801, 40000)
        logger.info('valid value is {val}, invalid values is {invalid} ,{invalid_negative} ,{invalid_max}'.format(
            val=random_valid_timeout, invalid=random_invalid_timeout, invalid_negative=random_invalid_timeout_neg,
            invalid_max=random_invalid_timeout_max))

    with allure.step('verify the default ib0 arp-timeout value is {value}'.format(
            value=IbInterfaceConsts.IB0_IP_ARP_DEFAULT_VALUE)):
        ip_dict = OutputParsingTool.parse_json_str_to_dictionary(ipoib_port.interface.ip.show()).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(
            ip_dict, IbInterfaceConsts.ARPTIMEOUT, str(IbInterfaceConsts.IB0_IP_ARP_DEFAULT_VALUE)).verify_result()

    with allure.step('Set random arp-timeout - {random}'.format(random=random_valid_timeout)):
        ipoib_port.interface.ip.set(op_param_name='arp-timeout', op_param_value=random_valid_timeout,
                                    apply=True, ask_for_confirmation=True)
        ip_dict = OutputParsingTool.parse_json_str_to_dictionary(ipoib_port.interface.ip.show()).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(ip_dict, IbInterfaceConsts.ARPTIMEOUT,
                                                          str(random_valid_timeout)).verify_result()

    with allure.step('try a random not supported ib0 arp-timeout {value} - between 0 and 60'.format(
            value=random_invalid_timeout)):
        result = ipoib_port.interface.ip.set(op_param_name='arp-timeout', op_param_value=random_invalid_timeout,
                                             apply=TestToolkit.tested_api == ApiType.OPENAPI)
        assert not result.result or "Valid range is" in result.info or \
            'Invalid Command' in result.info, "Set of an invalid arp-timeout should fail"
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        ip_dict = OutputParsingTool.parse_json_str_to_dictionary(ipoib_port.interface.ip.show()).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(ip_dict, IbInterfaceConsts.ARPTIMEOUT,
                                                          str(random_valid_timeout)).verify_result()

    with allure.step('try a random not supported ib0 arp-timeout {value} - less than 0'.format(
            value=random_invalid_timeout_neg)):
        result = ipoib_port.interface.ip.set(op_param_name='arp-timeout', op_param_value=random_invalid_timeout_neg,
                                             apply=TestToolkit.tested_api == ApiType.OPENAPI)
        assert not result.result or "Valid range is" in result.info or \
            'Invalid Command' in result.info, "Set of an invalid arp-timeout should fail"
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        ip_dict = OutputParsingTool.parse_json_str_to_dictionary(ipoib_port.interface.ip.show()).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(ip_dict, IbInterfaceConsts.ARPTIMEOUT,
                                                          str(random_valid_timeout)).verify_result()

    with allure.step('try a random not supported ib0 arp-timeout {value} - more than 28800'.format(
            value=random_invalid_timeout_max)):
        result = ipoib_port.interface.ip.set(op_param_name='arp-timeout', op_param_value=random_invalid_timeout_max,
                                             apply=TestToolkit.tested_api == ApiType.OPENAPI)
        assert not result.result or "Valid range is" in result.info or \
            'Invalid Command' in result.info, "Set of an invalid arp-timeout should fail"
        NvueGeneralCli.detach_config(TestToolkit.engines.dut)
        ip_dict = OutputParsingTool.parse_json_str_to_dictionary(ipoib_port.interface.ip.show()).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(ip_dict, IbInterfaceConsts.ARPTIMEOUT,
                                                          str(random_valid_timeout)).verify_result()

    with allure.step('Unset arp-timeout for ib0'):
        ipoib_port.interface.ip.unset(op_param='arp-timeout', apply=True, ask_for_confirmation=True)
        ip_dict = OutputParsingTool.parse_json_str_to_dictionary(ipoib_port.interface.ip.show()).verify_result()
        Tools.ValidationTool.verify_field_value_in_output(
            ip_dict, IbInterfaceConsts.ARPTIMEOUT, str(IbInterfaceConsts.IB0_IP_ARP_DEFAULT_VALUE)).verify_result()


# ------------ Open API tests -----------------

@pytest.mark.openapi
@pytest.mark.ib
@pytest.mark.simx
def test_interface_ib0_mtu_disabled_sm_openapi(engines, stop_sm):
    TestToolkit.tested_api = ApiType.OPENAPI
    test_interface_ib0_mtu_disabled_sm(engines, stop_sm)


@pytest.mark.openapi
@pytest.mark.simx
def test_interface_ib0_arp_timeout_disabled_sm_openapi(stop_sm):
    TestToolkit.tested_api = ApiType.OPENAPI
    test_interface_ib0_arp_timeout_disabled_sm(stop_sm)

import logging
import time

from ngts.tools.test_utils import allure_utils as allure
import pytest
import ast
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.tests_nvos.system.test_unsolicited_mgmt.helpers import *
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_constants.constants_nvos import SystemConsts, DatabaseConst, NvosConst
from ngts.nvos_tools.infra.Tools import Tools
from ngts.tests_nvos.constants import MINUTE

logger = logging.getLogger()
ipv4_eth0_expected_logs = f"NOTICE mgmt-unsolicited: Detected cable connection - running script with interface eth0"
ipv4_eth1_expected_logs = f"NOTICE mgmt-unsolicited: Detected cable connection - running script with interface eth1"
feature_disabled_logs = "NOTICE mgmt-unsolicited: Feature is disabled"


@pytest.mark.system
def test_show_system_mgmt_unsolicited_default_values(engines, devices):
    """
    @summary:
        in this function we will verify the mgmt unsolicited default value
    Test Flow:
        1. run nv show fae system mgmt-unsolicited
        2. verify output is enabled
        3. run sonic-db-cli -n asic0 CONFIG_DB hgetall "DEVICE_METADATA|localhost"
        4. verify 'mgmt_unsolicited_state' label exist and is 'enabled'

    :param engines:
    :param devices:
    :return:
    """
    fae = Fae()

    with allure.step('verify default values'):
        with allure.independent_step('show command output'):
            show_output = OutputParsingTool.parse_json_str_to_dictionary(fae.system.mgmt_unsolicited.show()).verify_result()
            ValidationTool.verify_field_value_in_output(show_output, SystemConsts.FAE_SYSTEM_STATE, SystemConsts.FAE_SYSTEM_STATE_DEFAULT_VALUE).verify_result()

        with allure.independent_step('database table'):
            table_name = '\"DEVICE_METADATA|localhost\"'
            database_values = Tools.DatabaseTool.sonic_db_cli_hgetall(engine=engines.dut, asic="", db_name=DatabaseConst.CONFIG_DB_NAME, table_name=table_name)
            output_dict = ast.literal_eval(database_values)
            ValidationTool.verify_field_value_in_output(output_dict, 'mgmt_unsolicited_state', NvosConst.ENABLED).verify_result()


@pytest.mark.system
def test_system_mgmt_unsolicited_enabled(engines, devices):
    """
    @summary:
        in this function we want to check the basic flow configuring ip address and unsolicited feature is enabled
    Run
        Test flow:
            1. replace between the ip address of eth0 and eth1 and update gateway for both
            2. check expected logs
            3. run sudo tcpdump -i eth0 -c 10 | grep "ARP, Request who-has"
            4. verify the packet has been sent
    """

    ipv4_eth0_expected_logs = "NOTICE mgmt-unsolicited: Executing command: arping -c 1 -U -i eth0 -S {}"
    ipv4_eth1_expected_logs = "NOTICE mgmt-unsolicited: Executing command: arping -c 1 -U -i eth1 -S {}"

    swap_ips_and_verify_logs_and_packets(engine=engines.dut, expected_messages=[ipv4_eth0_expected_logs, ipv4_eth1_expected_logs], is_enabled=True)


@pytest.mark.system
def test_system_mgmt_unsolicited_disabled(engines, devices):
    """
    @summary:
        in this case we want to disable the unsolicited feature and verify basic flow
    Run
        Test flow:
            1. run nv set fae system mgmt-unsolicited state disable + apply
            2. run nv show fae system mgmt-unsolicited
            3. verify output is disabled
            4. replace between the ip address of eth0 and eth1 and update gateway for both
            5. check expected logs
            6. run sudo tcpdump -i eth0 -c 10 | grep "ARP, Request who-has"
            7. verify the packet has not been sent
    """
    fae = Fae()
    with allure.step("testing disabled mgmt-unsolicited"):
        with allure.step("disable mgmt unsolicited feature"):
            fae.system.mgmt_unsolicited.set(op_param_name=SystemConsts.STATE, op_param_value=NvosConst.DISABLED, apply=True)
        try:
            with allure.step('show command output'):
                show_output = OutputParsingTool.parse_json_str_to_dictionary(fae.system.mgmt_unsolicited.show()).verify_result()
                ValidationTool.verify_field_value_in_output(show_output, SystemConsts.FAE_SYSTEM_STATE, NvosConst.DISABLED).verify_result()

            swap_ips_and_verify_logs_and_packets(engine=engines.dut, expected_messages=[feature_disabled_logs, feature_disabled_logs], is_enabled=False)
        finally:
            with allure.step("enable mgmt unsolicited feature"):
                fae.system.mgmt_unsolicited.set(op_param_name=SystemConsts.STATE, op_param_value=NvosConst.ENABLED, apply=True)


@pytest.mark.system
@pytest.mark.timeout(3 * MINUTE, func_only=True)
def test_system_mgmt_unsolicited_shutdown_enabled(engines, devices):
    """
    @summary:
        in this function we want to check the shutdown of mgmt interface while unsolicited feature is enabled
    Run
        Test flow:
            1. run nv set interface eth0 link state down
            2. check logs
    """
    with allure.step("shutdown a management interface and verify logs"):
        config_management_interface_verify_logs(engine=engines.dut, mgmt_interface='eth1', state=NvosConsts.LINK_STATE_DOWN, expected_logs=ipv4_eth0_expected_logs)

    with allure.step("activate a management interface and verify logs"):
        config_management_interface_verify_logs(engine=engines.dut, mgmt_interface='eth1', state=NvosConsts.LINK_STATE_UP, expected_logs=ipv4_eth1_expected_logs)


@pytest.mark.system
@pytest.mark.timeout(3 * MINUTE, func_only=True)
def test_system_mgmt_unsolicited_shutdown_disabled(engines, devices):
    """
    @summary:
        in this function we want to check the shutdown of mgmt interface while unsolicited feature is disabled
    Test Flow:
            1. run nv set fae system mgmt-unsolicited state disable + apply
            2. run nv set interface eth0 link state up
            3. check logs
            4. check tcpdump
            5. enable system mgmt-unsolicited
    :param engines:
    :param devices:
    :return:
    """
    fae = Fae()

    with allure.step("disable mgmt unsolicited feature"):
        fae.system.mgmt_unsolicited.set(op_param_name=SystemConsts.STATE, op_param_value=NvosConst.DISABLED, apply=True)

    try:
        with allure.step("shutdown a management interface and verify logs"):
            config_management_interface_verify_logs(engine=engines.dut, mgmt_interface='eth1', state=NvosConsts.LINK_STATE_DOWN, expected_logs=feature_disabled_logs)

        with allure.step("activate a management interface and verify logs"):
            config_management_interface_verify_logs(engine=engines.dut, mgmt_interface='eth1', state=NvosConsts.LINK_STATE_UP, expected_logs=feature_disabled_logs)
    finally:
        with allure.step("enable mgmt unsolicited feature"):
            fae.system.mgmt_unsolicited.set(op_param_name=SystemConsts.STATE, op_param_value=NvosConst.ENABLED, apply=True)

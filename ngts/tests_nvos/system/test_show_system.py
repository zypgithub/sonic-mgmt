import logging
import time

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system(test_api, engines, devices, topology_obj, nv_command, test_name):
    """
    Run show system message command and verify the required message
        Test flow:
            1. run show system message
            2. validate all fields have values
            3. set hostname to "Jaguar-NVOS"
            5. run show system message
            6. verify hostname appending value is "Jaguar-NVOS"
            7. run nv config apply
            8. verify hostname changed to "Jaguar-NVOS"
            9. run unset system hostname
            10. run nv config apply
            11. verify hostname changed to ""nvos"
    """
    TestToolkit.tested_api = test_api
    dut_device: BaseDevice = devices.dut

    with allure.step('Run show system command and verify that each field has a value'):
        system_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show()).get_returned_value()

    with allure.step('validate expected fields exist in output'):

        keys_to_remove = [SystemConsts.VERSION, SystemConsts.LOCATION, SystemConsts.CONTACT]  # keys pruned from output
        for key in keys_to_remove:
            system_output.pop(key, None)

        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(
            system_output, nv_command.system.get_expected_fields(devices.dut, 'system')).verify_result()

    with allure.step('get default hostname value'):
        output = OutputParsingTool.parse_json_str_to_dictionary(Interface(None, dut_device.cur_mgmt_port_name).show()).get_returned_value()
        dhcp_enabled = 'state' in output and output['state'] == "enabled"
        if dhcp_enabled:
            noga_query_data = topology_obj.players['dut']['attributes'].noga_query_data['attributes']
            dhcp_hostname = noga_query_data['Specific']['dhcp_hostname'] or noga_query_data['Common']['Name']
            if dhcp_hostname:
                assert system_output[SystemConsts.HOSTNAME] in [dhcp_hostname, f'{dhcp_hostname}-mgmt2'], f'unexpected "{SystemConsts.HOSTNAME}" value.\nexpected: {[dhcp_hostname, f"{dhcp_hostname}-mgmt2"]}\nactual: {system_output[SystemConsts.HOSTNAME]}'
            default_hostname = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show()).get_returned_value()[SystemConsts.HOSTNAME]
        else:
            default_hostname = SystemConsts.HOSTNAME_DEFAULT_VALUE

    with allure.step('set system hostname command and verify that hostname is updated'):
        with allure.step('set new hostname'):
            new_hostname_value = "NOS-NVOS"
            res_obj, duration = OperationTime.save_duration('set hostname', '', test_name, nv_command.system.set,
                                                            SystemConsts.HOSTNAME, new_hostname_value,
                                                            apply=True, ask_for_confirmation=True)
            res_obj.verify_result()
            time.sleep(3)
        with allure.step('verify duration'):
            OperationTime.verify_operation_time(duration, 'set hostname').verify_result()
        with allure.step('verify change in show'):
            system_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(system_output, SystemConsts.HOSTNAME, new_hostname_value).verify_result()

    with allure.step('Run unset system hostname command and verify that hostname is updated'):
        with allure.step('unset hostname'):
            nv_command.system.unset(SystemConsts.HOSTNAME, apply=True, ask_for_confirmation=True).verify_result()
            if dhcp_enabled:
                logging.info("Wait till the management interface will be reloaded to get a hostname from DHCP")
                time.sleep(30)
        with allure.step('verify hostname is back to default'):
            system_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show()).get_returned_value()
            time.sleep(3)
            assert system_output[SystemConsts.HOSTNAME] in [default_hostname, f'{default_hostname}-mgmt2'], f'unexpected "{SystemConsts.HOSTNAME}" value.\nexpected: {[default_hostname, f"{default_hostname}-mgmt2"]}\nactual: {system_output[SystemConsts.HOSTNAME]}'


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.cumulus
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_message(test_api, engines, devices, nv_command):
    """
    Run show/set/unset system message command and verify the required message
        Test flow:
            1. run show system message
            2. validate all fields have values
            3. set pre-login message[run cmd + apply conf]
            5. run show system message
            6. verify pre-login changed to "NVOS-TESTING"
            7. set post-login message[run cmd + apply conf]
            8. run show system message
            9. verify post-login changed to "NVOS-TESTING"
            10. unset post-login message[run cmd + apply conf]
            11. run show system message
            12. verify post-login changed to default value
            10. unset pre-login message[run cmd + apply conf]
            11. run show system message
            12. verify pre-login changed to default value
    """
    TestToolkit.tested_api = test_api

    new_pre_login_msg = "Testing PRE LOGIN MESSAGE"
    new_post_login_msg = "Testing POST LOGIN MESSAGE"

    with allure.step('Run set system message pre/post-login command and verify that pre/post-login are updated'):
        message_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                    devices.dut.pre_login_message).verify_result()
        TestToolkit.tested_api = ApiType.NVUE
        message_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                    devices.dut.post_login_message).verify_result()
        TestToolkit.tested_api = test_api

        nv_command.system.message.set(op_param_name=SystemConsts.PRE_LOGIN_MESSAGE, op_param_value=f'"{new_pre_login_msg}"',
                                      apply=True, dut_engine=engines.dut).verify_result()
        nv_command.system.message.set(op_param_name=SystemConsts.POST_LOGIN_MESSAGE, op_param_value=f'"{new_post_login_msg}"',
                                      apply=True, dut_engine=engines.dut).verify_result()
        time.sleep(3)
        message_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                    new_pre_login_msg).verify_result()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                    new_post_login_msg).verify_result()

    with allure.step('Run unset system message pre-login command and verify that pre-login is updated'):
        nv_command.system.message.unset(op_param=SystemConsts.PRE_LOGIN_MESSAGE, apply=True).verify_result()
        time.sleep(3)
        message_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                    devices.dut.pre_login_message).verify_result()
        logging.info("Verify the post-login was not affected")
        TestToolkit.tested_api = ApiType.NVUE
        message_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                    new_post_login_msg).verify_result()
        TestToolkit.tested_api = test_api

    with allure.step('Run unset system message post-login command and verify that pre-login is updated'):
        nv_command.system.message.unset(op_param=SystemConsts.POST_LOGIN_MESSAGE, apply=True).verify_result()
        time.sleep(3)
        TestToolkit.tested_api = ApiType.NVUE
        message_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                    devices.dut.post_login_message).verify_result()
        TestToolkit.tested_api = test_api


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_reboot(test_api, engines, devices, nv_command):
    """
    Run show system reboot command and verify the reboot history and reason values
        Test flow:
            1. run show system reboot
            2. validate all fields have values
            3. reboot the switch
            5. run show system reboot
            6. validate all fields have the new values
    """
    TestToolkit.tested_api = test_api

    with allure.step('Run show system reboot command and verify that each field has a value'):
        reboot_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.reboot.show()).get_returned_value()
        assert reboot_output['reason'], "reason field is missing"


@pytest.mark.cumulus
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_memory(test_api, engines, devices, nv_command):
    """
    Run show system memory and verify there is a correlation between the different values,
    and the values are in appropriate range.
        Test flow:
            1. run show system memory
            2. verify both keys (Physical and Swap) are exist
            3. validate total value = (free + used) values and greater than 0
            4. validate Utilization percentages are not reaching 60% for both Physical and Swap types (physical > 0)
            5. validate utilization value = (used / total) * 100, for both Physical and Swap types
    """
    TestToolkit.tested_api = test_api

    with allure.step('Run show system memory command and verify that each field has a value'):
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show("memory")).get_returned_value()

        assert len(output_dictionary.keys()) == 2, "Unexpected Number of keys"
        assert list(output_dictionary.keys())[0] == SystemConsts.MEMORY_PHYSICAL_KEY, "Unexpected Key value"
        assert list(output_dictionary.keys())[1] == SystemConsts.MEMORY_SWAP_KEY, "Unexpected Key value"

        total_sum = output_dictionary[SystemConsts.MEMORY_PHYSICAL_KEY]["free"] + \
            output_dictionary[SystemConsts.MEMORY_PHYSICAL_KEY]["used"]

        assert 0 < output_dictionary[SystemConsts.MEMORY_PHYSICAL_KEY]["total"] == total_sum, \
            "Total number of bytes must be equal to calculated total sum and greater than 0"

        utilization = output_dictionary[SystemConsts.MEMORY_PHYSICAL_KEY]["utilization"]
        utilization_calc = (output_dictionary[SystemConsts.MEMORY_PHYSICAL_KEY]["used"] /
                            output_dictionary[SystemConsts.MEMORY_PHYSICAL_KEY]["total"]) * 100
        assert SystemConsts.MEMORY_PERCENT_THRESH_MIN < utilization < SystemConsts.MEMORY_PERCENT_THRESH_MAX, \
            "Physical utilization percentage is out of range"
        assert abs(utilization - utilization_calc) < 0.000001, \
            f"Mismatch between Physical utilization: {utilization}% to calculated utilization: {utilization_calc}%"

        utilization = output_dictionary[SystemConsts.MEMORY_SWAP_KEY]["utilization"]
        assert SystemConsts.MEMORY_PERCENT_THRESH_MIN <= utilization < SystemConsts.MEMORY_PERCENT_THRESH_MAX, \
            "Swap utilization percentage is out of range"
        if output_dictionary[SystemConsts.MEMORY_SWAP_KEY]["total"] > 0:
            utilization_calc = (output_dictionary[SystemConsts.MEMORY_SWAP_KEY]["used"] /
                                output_dictionary[SystemConsts.MEMORY_SWAP_KEY]["total"]) * 100
            assert abs(utilization - utilization_calc) < 0.000001, \
                f"Mismatch between Swap utilization: {utilization}% to calculated utilization: {utilization_calc}%"


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.cumulus
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_cpu(test_api, engines, devices, nv_command):
    """
    Run show system memory and verify there is a correlation between the different values,
    and the values are in appropriate range.
        Test flow:
            1. run show system memory
            2. verify 3 keys (core-count, model and utilization) are exist
            3. verify switch CPU core-count matches the switch type
            4. validate Utilization percentages are not reaching 30%
    """
    TestToolkit.tested_api = test_api

    with allure.step('Run show system cpu command and verify that each field has a value'):
        time.sleep(10)
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show("cpu")).get_returned_value()

        assert len(output_dictionary.keys()) == 5, "Unexpected Number of keys"
        assert list(output_dictionary.keys())[0] == SystemConsts.CPU_CORE_COUNT_KEY, "Unexpected Key value"
        assert list(output_dictionary.keys())[1] == SystemConsts.CPU_CORES, "Unexpected Key value"
        assert list(output_dictionary.keys())[2] == SystemConsts.CPU_LOAD_AVERAGE_KEY, "Unexpected Key value"
        assert list(output_dictionary.keys())[3] == SystemConsts.CPU_MODEL_KEY, "Unexpected Key value"
        assert list(output_dictionary.keys())[4] == SystemConsts.CPU_TOTAL_UTILIZATION_KEY, "Unexpected Key value"
        assert output_dictionary[SystemConsts.CPU_CORE_COUNT_KEY] == devices.dut.core_count, \
            "Unexpected switch core-count"

        utilization = output_dictionary[SystemConsts.CPU_TOTAL_UTILIZATION_KEY]
        assert SystemConsts.CPU_PERCENT_THRESH_MIN < utilization < SystemConsts.CPU_PERCENT_THRESH_MAX, \
            "utilization percentage is out of range"


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_contact_set(test_api, engines, nv_command):
    """
    Run show system message command and verify the required message
        Test flow:
            1. Run set system contact
            2. Run system show
            3. Validate system contact is as set in step 1
            4. Run unset system contact
            5. Run system show
            6. Validate system contact is not present in system show
    """
    TestToolkit.tested_api = test_api

    if test_api == ApiType.NVUE and is_bug_active(4362872):
        pytest.skip("skipped for NVUE type due to bug: https://redmine.mellanox.com/issues/4362872")

    try:
        help_system_contact_location(engines, nv_command.system, SystemConsts.CONTACT)

    finally:
        clear_system_contact_and_location(nv_command.system)


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_location_set(test_api, engines, nv_command):
    """
    Run show system message command and verify the required message
        Test flow:
            1. Run set system location
            2. Run system show
            3. Validate system location is as set in step 1
            4. Run unset system location
            5. Run system show
            6. Validate system location is not present in system show
    """
    TestToolkit.tested_api = test_api

    if test_api == ApiType.NVUE and is_bug_active(4362872):
        pytest.skip("skipped for NVUE type due to bug: https://redmine.mellanox.com/issues/4362872")

    try:
        help_system_contact_location(engines, nv_command.system, SystemConsts.LOCATION)

    finally:
        clear_system_contact_and_location(nv_command.system)


@pytest.mark.system
@pytest.mark.simx
def test_factory_reset_for_system_contact_location(engines, nv_command):
    """
    Run factory reset system command and verify the system contact and location fields are removed from system show
        Test flow:
            1. Run 'nv set system contact <args>>'
            2. Run 'nv set system location <args>>'
            4. Run 'nv show system' and verify system contact and location are set
            5. Run system factory reset
            6. Run 'nv show system' and verify systems contact and location fields are removed
    """

    if is_bug_active(4362872):
        pytest.skip("skipped for NVUE type due to bug: https://redmine.mellanox.com/issues/4362872")

    try:
        with allure.step('Run set system contact command and apply config'):
            nv_command.system.set(op_param_name=SystemConsts.CONTACT, op_param_value="contact_info", apply=True,
                                  dut_engine=engines.dut).verify_result()

        with allure.step('Verify system contact is set'):
            system_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(system_output, SystemConsts.CONTACT, "contact_info").\
                verify_result()

        with allure.step('Run set system location command and apply config'):
            nv_command.system.set(op_param_name=SystemConsts.LOCATION, op_param_value="location_info", apply=True,
                                  dut_engine=engines.dut).verify_result()

        with allure.step('Verify system location is set'):
            system_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(system_output, SystemConsts.LOCATION, "location_info").\
                verify_result()

        with allure.step("Run reset factory with keep basic param"):
            nv_command.system.factory_default.action_reset(param="keep basic").verify_result()

        with allure.step('Validate system contact is back to default (Null)'):
            system_output = OutputParsingTool.parse_json_str_to_dictionary(nv_command.system.show()).get_returned_value()
            assert system_output[SystemConsts.CONTACT] is None, "System contact in system show is {} instead of Null".\
                format(system_output[SystemConsts.CONTACT])

        with allure.step('Validate system location is back to default (Null)'):
            assert system_output[SystemConsts.LOCATION] is None, "System location in system show is {} instead of" \
                                                                 "Null".format(system_output[SystemConsts.LOCATION])

    finally:
        clear_system_contact_and_location(nv_command.system)


def clear_system_contact_and_location(system):

    with allure.step('Unset the system contact'):
        system.unset(SystemConsts.CONTACT, apply=True).verify_result()

    with allure.step('Unset the system location'):
        system.unset(SystemConsts.LOCATION, apply=True).verify_result()

    with allure.step('Validate system contact is back to default (Null)'):
        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        assert system_output[SystemConsts.CONTACT] is None, "System contact in system show is {} instead of Null". \
            format(system_output[SystemConsts.CONTACT])

    with allure.step('Validate system location is back to default (Null)'):
        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        assert system_output[SystemConsts.LOCATION] is None, "System location in system show is {} instead of Null". \
            format(system_output[SystemConsts.LOCATION])


def help_system_contact_location(engines, system, field_name):
    with allure.step('Set system {} command and verify that contact is updated'.format(field_name)):
        with allure.step('Set new system {}'.format(field_name)):
            field_info = field_name + "info"
            system.set(op_param_name=field_name, op_param_value=field_info, apply=True,
                       dut_engine=engines.dut).verify_result()

        with allure.step('Run show system and validate system {}'.format(field_name)):
            system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(system_output, field_name, field_info).\
                verify_result()

    with allure.step('Unset system {} command and verify that {} field is Null'.format(field_name, field_name)):
        with allure.step('Unset the system {}'.format(field_name)):
            system.unset(field_name, apply=True).verify_result()

        with allure.step('Validate system {} is back to default (Null)'.format(field_name)):
            system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
            assert system_output[field_name] is None, "System {} in system show is {} instead of Null".\
                format(field_name, system_output[field_name])

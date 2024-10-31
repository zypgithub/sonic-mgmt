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
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system(test_api, engines, devices, topology_obj, test_name):
    """
    Run show system message command and verify the required message
        Test flow:
            1. run show system message
            2. validate all fields have values
            3. set hostname to "Jaguar-NVOS"
            5. run show system message
            # 6. verify hostname appending value is "Jaguar-NVOS"
            7. run nv config apply
            8. verify hostname changed to "Jaguar-NVOS"
            9. run unset system hostname
            10. run nv config apply
            11. verify hostname changed to ""nvos"
    """
    TestToolkit.tested_api = test_api
    dut_device: BaseDevice = devices.dut

    with allure.step('Run show system command and verify that each field has a value'):
        system = System()
        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()

    with allure.step('validate expected fields exist in output'):

        keys_to_remove = [SystemConsts.VERSION, SystemConsts.LOCATION, SystemConsts.CONTACT]  # keys pruned from output
        for key in keys_to_remove:
            system_output.pop(key, None)

        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(
            system_output, system.get_expected_fields(devices.dut, 'system')).verify_result()

    with allure.step('get default hostname value'):
        output = OutputParsingTool.parse_json_str_to_dictionary(Interface(None, dut_device.cur_mgmt_port_name).show()).get_returned_value()
        dhcp_enabled = 'state' in output and output['state'] == "enabled"
        if dhcp_enabled:
            noga_query_data = topology_obj.players['dut']['attributes'].noga_query_data['attributes']
            dhcp_hostname = noga_query_data['Specific']['dhcp_hostname'] or noga_query_data['Common']['Name']
            if dhcp_hostname:
                assert system_output[SystemConsts.HOSTNAME] in [dhcp_hostname, f'{dhcp_hostname}-mgmt2'], f'unexpected "{SystemConsts.HOSTNAME}" value.\nexpected: {[dhcp_hostname, f"{dhcp_hostname}-mgmt2"]}\nactual: {system_output[SystemConsts.HOSTNAME]}'
            default_hostname = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()[SystemConsts.HOSTNAME]
        else:
            default_hostname = SystemConsts.HOSTNAME_DEFAULT_VALUE

    with allure.step('set system hostname command and verify that hostname is updated'):
        with allure.step('set new hostname'):
            new_hostname_value = "NOS-NVOS"
            res_obj, duration = OperationTime.save_duration('set hostname', '', test_name, system.set,
                                                            SystemConsts.HOSTNAME, new_hostname_value,
                                                            apply=True, ask_for_confirmation=True)
            res_obj.verify_result()
            time.sleep(3)
        with allure.step('verify duration'):
            OperationTime.verify_operation_time(duration, 'set hostname').verify_result()
        with allure.step('verify change in show'):
            system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(system_output, SystemConsts.HOSTNAME, new_hostname_value).verify_result()

    with allure.step('Run unset system hostname command and verify that hostname is updated'):
        with allure.step('unset hostname'):
            system.unset(SystemConsts.HOSTNAME, apply=True, ask_for_confirmation=True).verify_result()
            if dhcp_enabled:
                logging.info("Wait till the management interface will be reloaded to get a hostname from DHCP")
                time.sleep(30)
        with allure.step('verify hostname is back to default'):
            system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
            time.sleep(3)
            assert system_output[SystemConsts.HOSTNAME] in [default_hostname, f'{default_hostname}-mgmt2'], f'unexpected "{SystemConsts.HOSTNAME}" value.\nexpected: {[default_hostname, f"{default_hostname}-mgmt2"]}\nactual: {system_output[SystemConsts.HOSTNAME]}'


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.cumulus
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_message(test_api, engines, devices):
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
    system = System()

    with allure.step('Run set system message pre/post-login command and verify that pre/post-login are updated'):
        message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                    devices.dut.pre_login_message).verify_result()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                    devices.dut.post_login_message).verify_result()

        system.message.set(op_param_name=SystemConsts.PRE_LOGIN_MESSAGE, op_param_value=f'"{new_pre_login_msg}"',
                           apply=True, dut_engine=engines.dut).verify_result()
        system.message.set(op_param_name=SystemConsts.POST_LOGIN_MESSAGE, op_param_value=f'"{new_post_login_msg}"',
                           apply=True, dut_engine=engines.dut).verify_result()
        time.sleep(3)
        message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                    new_pre_login_msg).verify_result()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                    new_post_login_msg).verify_result()

    with allure.step('Run unset system message pre-login command and verify that pre-login is updated'):
        system.message.unset(op_param=SystemConsts.PRE_LOGIN_MESSAGE, apply=True).verify_result()
        time.sleep(3)
        message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                    devices.dut.pre_login_message).verify_result()
        logging.info("Verify the post-login was not affected")
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                    new_post_login_msg).verify_result()

    with allure.step('Run unset system message post-login command and verify that pre-login is updated'):
        system.message.unset(op_param=SystemConsts.POST_LOGIN_MESSAGE, apply=True).verify_result()
        time.sleep(3)
        message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                    devices.dut.post_login_message).verify_result()


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.nvos_ci
@pytest.mark.nvos_chipsim_ci
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_version(test_api, engines, devices):
    """
    Run show system version command and verify version values
        Test flow
        1. run show system message
        2. validate values in db
    """
    TestToolkit.tested_api = test_api

    with allure.step('Run show system command and verify that each field has a value'):
        system = System()
        version_output = OutputParsingTool.parse_json_str_to_dictionary(system.version.show()).get_returned_value()
        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(
            version_output, system.get_expected_fields(devices.dut, 'version')).verify_result()


@pytest.mark.system
@pytest.mark.cumulus
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_reboot(test_api, engines, devices):
    """
    Run show system reboot command and verify the reboot history and reason values
        Test flow:
            1. run show system reboot
            2. validate all fields have values
            3. reboot the switch
            5. run show system message
            6. validate all fields have the new values
    """
    TestToolkit.tested_api = test_api

    with allure.step('Run show system reboot command and verify that each field has a value'):
        system = System()
        reboot_output = OutputParsingTool.parse_json_str_to_dictionary(system.reboot.show()).get_returned_value()
        assert reboot_output['reason'], "reason field is missing"


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_memory(test_api, engines, devices):
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
        system = System()
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.show("memory")).get_returned_value()

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
def test_show_system_cpu(test_api, engines, devices):
    """
    Run show system memory and verify there is a correlation between the different values,
    and the values are in appropriate range.
        Test flow:
            1. run show system cpu
            2. verify the 5 keys (core-count, cores, load-average, model and utilization) do exist
            3. verify switch CPU core-count matches the switch type
            4. validate Utilization percentages are in the appropriate range
    """
    TestToolkit.tested_api = test_api
    time.sleep(10)
    system = System()

    with allure.step('Validate all expected show cpu fields are present'):
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.show("cpu")).get_returned_value()
        ValidationTool.verify_all_fields_value_exist_in_output_dictionary(output_dictionary,
                                                                          SystemConsts.CPU_INFO_LIST).verify_result()

    with allure.step('Validate CPU core-count'):
        assert output_dictionary[SystemConsts.CPU_CORE_COUNT_KEY] == devices.dut.core_count, \
            "Switch core-count is {} instead of {}".format(output_dictionary[SystemConsts.CPU_CORE_COUNT_KEY],
                                                           devices.dut.core_count)

    with allure.step('Validate utilization for all the CPU cores'):
        for core_num in range(0, devices.dut.core_count):
            util = output_dictionary[SystemConsts.CPU_CORES]["CPU " + str(core_num)][SystemConsts.CPU_UTILIZATION_KEY]
            assert SystemConsts.CPU_PERCENT_THRESH_MIN < util < SystemConsts.CPU_PERCENT_THRESH_MAX, \
                "Utilization percentage is out of range for CPU {}".format(core_num)

    with allure.step('Validate CPU load average'):
        load_1m = output_dictionary[SystemConsts.CPU_LOAD_AVERAGE]["1m"]
        load_5m = output_dictionary[SystemConsts.CPU_LOAD_AVERAGE]["5m"]
        load_15m = output_dictionary[SystemConsts.CPU_LOAD_AVERAGE]["15m"]
        assert 0 < load_1m < devices.dut.core_count, \
            'CPU load average for 1m is {} instead of being between 0 & {}'.format(load_1m, devices.dut.core_count)
        assert 0 < load_5m < devices.dut.core_count, \
            'CPU load average for 5m is {} instead of being between 0 & {}'.format(load_5m, devices.dut.core_count)
        assert 0 < load_15m < devices.dut.core_count, \
            'CPU load average for 15m is {} instead of being between 0 & {}'.format(load_15m, devices.dut.core_count)

    with allure.step('Validate average CPU utilization is in range'):
        utilization = output_dictionary[SystemConsts.CPU_UTILIZATION_KEY]
        assert SystemConsts.CPU_PERCENT_THRESH_MIN < utilization < SystemConsts.CPU_PERCENT_THRESH_MAX, \
            "utilization percentage is out of range"

    with allure.step('Validate CPU model is present'):
        assert output_dictionary[SystemConsts.CPU_MODEL_KEY] != "", 'CPU model is empty'


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.cumulus
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_disk(test_api):
    """
    Run show system disk and verify there is a correlation between the different values,
    and the values are in appropriate range.
        Test flow:
            1. run show system disk
            2. verify the 6 keys ('available', 'used', 'free-percent', 'free', 'mountpoint', 'total-size') do exist
            3. verify the values for the keys: 'available', 'used', 'free-percent', 'free', 'total-size' are valid
    """
    TestToolkit.tested_api = test_api
    system = System()

    with allure.step('Validate all expected show disk fields are present'):
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.show("disk")).get_returned_value()
        for key in output_dictionary.keys():
            ValidationTool.verify_all_fields_value_exist_in_output_dictionary(
                output_dictionary[key], SystemConsts.DISK_INFO_FIELD_LIST).verify_result()

    for fs in output_dictionary.keys():
        with allure.step('Verify total size for file system {} > 0'.format(fs)):
            total_size = float(output_dictionary[fs][SystemConsts.DISK_TOTAL_SIZE_KEY].split(' ')[0])
            assert total_size > 0, 'Total size for file system {} is {} which is invalid'.format(fs, total_size)

        with allure.step('Verify available size for file system {}'.format(fs)):
            _verify_disk_size_field(fs, SystemConsts.DISK_AVAILABLE_KEY, 0, total_size, output_dictionary)

        with allure.step('Verify free size for file system {}'.format(fs)):
            _verify_disk_size_field(fs, SystemConsts.DISK_FREE_KEY, 0, total_size, output_dictionary)

        with allure.step('Verify used size for file system {}'.format(fs)):
            _verify_disk_size_field(fs, SystemConsts.DISK_USED_KEY, 0, total_size, output_dictionary)

        with allure.step('Verify free percent for file system {}'.format(fs)):
            _verify_disk_size_field(fs, SystemConsts.DISK_FREE_PERCENT_KEY, 0, 100, output_dictionary)


def _verify_disk_size_field(fs, field, range_start, range_end, output_dict):
    assert field in output_dict[fs].keys(), '{} field is not present in output for filesystem {}'.format(field, fs)
    field_value = float(output_dict[fs][field].split(' ')[0])
    assert range_start < field_value < range_end, '{} size of file system {} is {} which is out of range ({}, {})'.\
        format(field, fs, field_value, range_start, range_end)

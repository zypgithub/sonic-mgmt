import logging
import time

from ngts.tools.test_utils import allure_utils as allure
import pytest
from retry.api import retry_call
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_constants.constants_nvos import SystemConsts, ActionConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger()
cmd_to_simulate_events = 'docker exec eventd events_publish_test.py -c '


@pytest.mark.events
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_events(test_api, engines):
    """
    Run show system events and table-size commands and verify the required events and table-size
        Test flow:
            1. Simulate 60 events
            2. Run 'nv show system events' and validate there are 50(default) no of events in the output
            3. Run 'nv show system events last' and validate there are 20(default for 'last') events in the output
            4. Run 'nv show system events last 25' and validate there are 25 events in the output
            5. Run 'nv show system events recent 5' and validate there are events in the output
    """
    TestToolkit.tested_api = test_api
    system = System()

    with allure.step('Simulate 60 system events'):
        # Simulate more events than the default no of events(50) displayed by show event command
        no_of_events_to_simulate = 60
        cmd_to_run = cmd_to_simulate_events + str(no_of_events_to_simulate)
        output = engines.dut.run_cmd(cmd_to_run)
        assert output == '', 'Error in executing simulate command: {}\n{}'.format(output, cmd_to_run)
        time.sleep(10)

    with allure.step('Run show system events command & validate there are 50(default) no of events in the output'):
        output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show()).get_returned_value()
        no_of_events = len(output[SystemConsts.SYSTEM_LAST_EVENT_OLD])
        assert no_of_events is 50, 'No of events in show output is {} instead of {}'.format(no_of_events, 50)

    with allure.step('Run show system events last command & validate there are 20(default) events in the output'):
        output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show(SystemConsts.SYSTEM_LAST_EVENT)).get_returned_value()
        if test_api == ApiType.OPENAPI and is_bug_active(4396664):
            pytest.skip("Skipping this test due to Rm bug for OpenApi: https://redmine.mellanox.com/issues/4396664")
        else:
            no_of_events = len(output)
            assert no_of_events is 20, 'No of events in show output is {} instead of {}'.format(no_of_events, 20)

    with allure.step('Run show system events last 25 command, validate there are 25 events in the output'):
        output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show_last('25')).get_returned_value()
        no_of_events = len(output)
        assert no_of_events is 25, 'No of events in show output is {} instead of {}'.format(no_of_events, 25)

    with allure.step('Run show system events recent 5 command, validate there are events in the output'):
        # show events last <param> displays events in the last <param> minutes
        output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show_recent()).get_returned_value()
        no_of_events = len(output)
        assert no_of_events > 0, 'There are no events found'


@pytest.mark.events
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_events_table_size(test_api):
    """
    Run show system events and table-size commands and verify the required events and table-size
        Test flow:
            1. Run 'nv show system events table-size' and validate table-size is present in the output
    """
    TestToolkit.tested_api = test_api
    system = System()

    with allure.step('Run show system events table-size command & validate table-size is present in the output'):
        output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show()).get_returned_value()
        ValidationTool.verify_field_value_exist_in_output_dict(output,
                                                               SystemConsts.EVENTS_TABLE_SIZE).verify_result()


@pytest.mark.events
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_events_maximum(test_api, engines):
    """
    Verify show system events is able to capture maximum no of events (10000)
        Test flow:
            1. Run 'nv set system events table-size 10000'
            2. Run 'nv show system events' and validate table-size is set to 10000
            3. Simulate 10000 system events
            4. Run 'nv show system events' and validate 10000 events are shown in output
            5. Unset system events table-size and validate table-size is set to default(1000)
            6. Clear system events
    """
    TestToolkit.tested_api = test_api
    system = System()
    clear_system_events(system)
    try:
        with allure.step('Set system events table-size to maximum(10000)'):
            system.events.set(op_param_name='table-size', op_param_value=SystemConsts.EVENTS_TABLE_SIZE_MAX,
                              apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Validate system events table-size is set to 10000'):
            retry_call(_verify_field_in_show_output,
                       [system.events, SystemConsts.EVENTS_TABLE_SIZE, SystemConsts.EVENTS_TABLE_SIZE_MAX],
                       exceptions=AssertionError, tries=2, delay=5, logger=logger)

        with allure.step('Simulate 10100 system events'):
            # Trying to create more than 10000 to verify that the size of table is limited to 10000 which is max
            no_of_events_to_simulate = 10100
            cmd_to_run = cmd_to_simulate_events + str(no_of_events_to_simulate)
            output = engines.dut.run_cmd(cmd_to_run)
            assert output == '', 'Error in executing simulate command: {}\n{}'.format(output, cmd_to_run)
            time.sleep(60)

        with allure.step('Run show system events command & validate there are 10000(max) no of events in the output'):
            # Trying to display more than 10000 to verify that the size of display is limited to 10000 which is max
            output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show_last(10100)).\
                get_returned_value()
            no_of_events = len(output)
            assert no_of_events == 10000, 'No of events in show output is {} instead of {}'.format(no_of_events, 10000)

    finally:
        with allure.step('Unset system events table-size'):
            system.events.unset(apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Validate system events table-size is set to default(1000)'):
            retry_call(_verify_field_in_show_output,
                       [system.events, SystemConsts.EVENTS_TABLE_SIZE, SystemConsts.EVENTS_TABLE_SIZE_DEFAULT],
                       exceptions=AssertionError, tries=2, delay=5, logger=logger)

        with allure.step('Clear system events'):
            clear_system_events(system)


@pytest.mark.events
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_system_events_table_size(test_api, engines):
    """
    Verify nv set system events table-size <size> command
        Test flow:
            1	Run nv unset system events table-size and validate table-size is set to default
            2	Simulate events more than default value (1100)
            3	Run nv show system events and validate table-occupancy should be default
            4	Run nv set system events table-size 600
            5	Run nv show system events table-size and validate it is set to 600 via show command
            6	Run nv show system events and validate table-occupancy should be 600
            7	Run nv set system events table-size 1100
            8	Run nv show system events table-size and validate table-size should be 1100
            9	Simulate 500 more events (to make the total 1100+)
            10	Run nv show system events  and validate table-occupancy should be 1100+
            11	Run nv unset system events table-size
            12	Run nv show system events table-size and validate table-size should be default (1000)
            13	Run nv show system events and validate table-occupancy should be default (1000)
            14	Run nv action clear system events
            15	Run nv show system events and validate table-occupancy should be 0
    """
    TestToolkit.tested_api = test_api
    system = System()

    try:
        with allure.step('Unset system events table-size'):
            system.events.unset(apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Validate system events table-size is set to default(1000)'):
            output = OutputParsingTool.parse_json_str_to_dictionary(system.events.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(output, SystemConsts.EVENTS_TABLE_SIZE,
                                                        SystemConsts.EVENTS_TABLE_SIZE_DEFAULT).verify_result()

        with allure.step('Simulate 1100 system events'):
            # Trying to create more than 1000 to verify that the size of table is limited to default (1000)
            no_of_events_to_simulate = 1100
            cmd_to_run = cmd_to_simulate_events + str(no_of_events_to_simulate)
            output = engines.dut.run_cmd(cmd_to_run)
            assert output == '', 'Error in executing simulate command: {}\n{}'.format(output, cmd_to_run)

        with allure.step('Run show system events command & validate table-occupancy should be default'):
            retry_call(_verify_field_in_show_output,
                       [system.events, SystemConsts.EVENTS_TABLE_OCCUPANCY, SystemConsts.EVENTS_TABLE_SIZE_DEFAULT],
                       exceptions=AssertionError, tries=6, delay=5, logger=logger)

        with allure.step('Set system events table-size to 600'):
            system.events.set(op_param_name='table-size', op_param_value=600,
                              apply=True, dut_engine=engines.dut).verify_result()
            time.sleep(10)

        with allure.step('Validate system events table-size is set to 600'):
            retry_call(_verify_field_in_show_output, [system.events, SystemConsts.EVENTS_TABLE_SIZE, 600],
                       exceptions=AssertionError, tries=4, delay=5, logger=logger)

        with allure.step('Run show system events command & validate table-occupancy should be 600'):
            retry_call(_verify_field_in_show_output, [system.events, SystemConsts.EVENTS_TABLE_OCCUPANCY, 599],
                       exceptions=AssertionError, tries=4, delay=5, logger=logger)

        with allure.step('Set system events table-size to 1100'):
            system.events.set(op_param_name='table-size', op_param_value=1100,
                              apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Validate system events table-size is set to 1100'):
            retry_call(_verify_field_in_show_output, [system.events, SystemConsts.EVENTS_TABLE_SIZE, 1100],
                       exceptions=AssertionError, tries=4, delay=5, logger=logger)

        with allure.step('Simulate 500 more system events(to make it 1100+)'):
            # Trying to create more than 1000 to verify that the size of table is limited to 1000 which is default
            no_of_events_to_simulate = 500
            cmd_to_run = cmd_to_simulate_events + str(no_of_events_to_simulate)
            output = engines.dut.run_cmd(cmd_to_run)
            assert output == '', 'Error in executing simulate command: {}\n{}'.format(output, cmd_to_run)

        with allure.step('Run show system events command & validate table-occupancy should be 1100'):
            retry_call(_verify_field_in_show_output,
                       [system.events, SystemConsts.EVENTS_TABLE_OCCUPANCY, 1099, 0, True],
                       exceptions=AssertionError, tries=4, delay=5, logger=logger)

        with allure.step('Unset system events table-size'):
            system.events.unset(apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Validate system events table-size is set to default(1000)'):
            retry_call(_verify_field_in_show_output,
                       [system.events, SystemConsts.EVENTS_TABLE_SIZE, SystemConsts.EVENTS_TABLE_SIZE_DEFAULT],
                       exceptions=AssertionError, tries=4, delay=5, logger=logger)

        with allure.step('Run show system events command & validate table-occupancy should be default(1000)'):
            retry_call(_verify_field_in_show_output,
                       [system.events, SystemConsts.EVENTS_TABLE_OCCUPANCY, 999, 0, True],
                       exceptions=AssertionError, tries=4, delay=5, logger=logger)

    finally:
        with allure.step('Clear system events'):
            clear_system_events(system)


def _verify_field_in_show_output(obj_name, field_name, val_min=0, val_max=0, check_min=False, check_max=False):
    if not (check_min | check_max):
        output = OutputParsingTool.parse_json_str_to_dictionary(obj_name.show()).get_returned_value()
        # Minimum & maximum values are same
        res_obj = ValidationTool.verify_field_value_in_output(output, field_name, val_min).verify_result()
        return res_obj

    if check_min:
        output = OutputParsingTool.parse_json_str_to_dictionary(obj_name.show()).get_returned_value()
        val = int(output[field_name])
        assert val_min <= val, "{} is {}, less than minimum value of {}".format(field_name, val, val_min)

    if check_max:
        output = OutputParsingTool.parse_json_str_to_dictionary(obj_name.show()).get_returned_value()
        val = int(output[field_name])
        assert val_max >= val, "{} is {}, larger than maximum value of {}".format(field_name, val, val_max)


def clear_system_events(system):
    """
    Method to unset the system messages for pre-login, post-login and post-logout
    :param system:  System object
    """
    with allure.step('Run clear system events and apply config'):
        system.events.action(ActionConsts.CLEAR)

    with allure.step('Validate events are cleared'):
        retry_call(_verify_field_in_show_output, [system.events, SystemConsts.EVENTS_TABLE_OCCUPANCY, 0],
                   exceptions=AssertionError, tries=4, delay=5, logger=logger)

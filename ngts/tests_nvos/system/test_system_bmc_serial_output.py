import pytest
import logging
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils.allure_utils import step as allure_step
from ngts.nvos_constants.constants_nvos import ActionConsts
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_constants.constants_nvos import ApiType


logger = logging.getLogger(__name__)


@pytest.mark.bmc
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_bmc_serial_output(engines, devices, serial_engine, topology_obj, test_api):
    """
    Test flow:
        1. Verify default values and fields
        2. Run nv show system image from serial console and check it exist in the logs
        3. Change serial-logs to BMC and verify output
        4. Change serial-logs back to CPU and verify output
        5. Run show system event and check it exist in the log

    """
    fae = Fae()
    system = System()
    serial_engine = ConnectionTool.create_serial_connection(topology_obj=topology_obj, devices=devices,
                                                            force_new_login=True)

    try:
        with allure_step('Run nv show system serial-console and verify default values and fields'):
            serial_output = OutputParsingTool.parse_json_str_to_dictionary(system.serial_console.show())\
                .get_returned_value()

            with allure_step("Verify default field"):
                ValidationTool.validate_fields_values_in_output(SystemConsts.SERIAL_BMC_CONSOLE_OUTPUT_DEFAULT_FIELD,
                                                                SystemConsts.SERIAL_BMC_CONSOLE_OUTPUT_DEFAULT_VALUE,
                                                                serial_output).verify_result()

        _show_and_verify_serial_console(system, serial_engine, param='image')

        with allure_step('Run nv action change fae system system serial-console connected-to bmc'):
            fae.system.serial_console.action(action=ActionConsts.CHANGE,
                                             param_value=SystemConsts.SERIAL_BMC_ACTION_CHANGE_BMC).verify_result()

        with allure_step('Show ssh and verify default values'):
            serial_output = OutputParsingTool.parse_json_str_to_dictionary(system.serial_console.show())\
                .get_returned_value()

            with allure_step("Verify output changed to bmc"):
                ValidationTool.verify_field_value_in_output(serial_output, SystemConsts.SERIAL_CONSOLE_CONNECTED_TO,
                                                            SystemConsts.SERIAL_CONSOLE_OUTPUT_BMC).verify_result()

        # TBD add BMC validations after it will be implemented

    finally:
        with allure_step('Run nv action change fae system system serial-console connected-to cpu'):
            fae.system.serial_console.action(action=ActionConsts.CHANGE,
                                             param_value=SystemConsts.SERIAL_BMC_ACTION_CHANGE_CPU).verify_result()

        with allure_step('Run nv show serial-console and verify value changed to cpu'):
            serial_output = OutputParsingTool.parse_json_str_to_dictionary(system.serial_console.show())\
                .get_returned_value()

            with allure_step("Verify output changed to cpu"):
                ValidationTool.verify_field_value_in_output(serial_output, SystemConsts.SERIAL_CONSOLE_CONNECTED_TO,
                                                            SystemConsts.SERIAL_CONSOLE_OUTPUT_CPU).verify_result()

        _show_and_verify_serial_console(system, serial_engine, param='event')


def _show_and_verify_serial_console(system, serial_engine, param):
    with allure_step("Run nv show system memory from serial console"):
        system.events.show(dut_engine=serial_engine)

    with allure_step("Verify system events logged"):
        system.log.show_log(param='| grep {0}'.format(param), exit_cmd='q', expected_str='system/{0}'.format(param))

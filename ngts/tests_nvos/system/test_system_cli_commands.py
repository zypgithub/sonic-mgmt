import time
import pytest
import logging
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.conftest import create_ssh_login_engine
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from infra.tools.connection_tools.pexpect_serial_engine import PexpectSerialEngine
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from infra.tools.general_constants.constants import DefaultConnectionValues
from ngts.tools.test_utils import allure_utils as allure


logger = logging.getLogger(__name__)


@pytest.mark.checklist
@pytest.mark.ssh_config
def test_set_max_cli_session(engines, devices):
    """
    Test flow:
        1. run show system ssh and check default fields and values
        2. set max cli session to 98, check functionality of it, cpu and memory utilization
        3. unset system ssh-config max cli session and verify

    """
    system = System()

    with allure.step('Show ssh and verify default values'):
        ssh_output = OutputParsingTool.parse_json_str_to_dictionary(system.ssh_server.show()).get_returned_value()

        with allure.step("Verify default values"):
            ValidationTool.validate_fields_values_in_output(SystemConsts.SSH_CONFIG_OUTPUT_FIELDS,
                                                            SystemConsts.SSH_CONFIG_DEFAULT_VALUES,
                                                            ssh_output).verify_result()

        with allure.step("Validate login max cli session"):
            system.ssh_server.set(SystemConsts.SSH_CONFIG_MAX_SESSIONS, '98', apply=True,
                                  ask_for_confirmation=True).verify_result()
            ssh_output = OutputParsingTool.parse_json_str_to_dictionary(system.ssh_server.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(ssh_output, SystemConsts.SSH_CONFIG_MAX_SESSIONS, '98')\
                .verify_result()

    with allure.step("Open more than 98 cli's session and verify result"):
        connection_list = []
        try:
            for conn_no in range(100):
                try:
                    logger.info("Creating connection number: {}".format(conn_no + 1))
                    connection = create_ssh_login_engine(engines.dut.ip, username=DefaultConnectionValues.DEFAULT_USER,
                                                         port=22)
                    connection_list.append(connection)
                    respond = connection.expect([DefaultConnectionValues.PASSWORD_REGEX, '~'])
                    if respond == 0:
                        connection.sendline(devices.dut.default_password)
                        connection.expect(DefaultConnectionValues.DEFAULT_PROMPTS[0])
                except Exception as err:
                    logger.info("Failed in creating connection {}, Error: {}".format(conn_no + 1, err))
                    break

            with allure.step("Validate no of users is 98"):
                connection_list[conn_no - 1].sendline('w')
                connection_list[conn_no - 1].expect('98 users')

            with allure.step("Validate system resources CPU utilization with 98 cli session configured"):
                logging.info("Validate system resources CPU utilization with 98 cli session configured")
                output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
                    system.show("cpu")).get_returned_value()
                cpu_utilization = output_dictionary[SystemConsts.CPU_TOTAL_UTILIZATION_KEY]
                assert cpu_utilization < SystemConsts.CPU_PERCENT_THRESH_MAX, \
                    "CPU utilization: {actual}% is higher than the maximum limit of: {expected}%" \
                    "".format(actual=cpu_utilization, expected=SystemConsts.CPU_PERCENT_THRESH_MAX)

            with allure.step("Validate system memory utilization with 98 cli session configured"):
                logging.info("Validate system memory  utilization with 98 cli session configured")
                output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(
                    system.show("memory")).get_returned_value()
                utilization = output_dictionary[SystemConsts.MEMORY_PHYSICAL_KEY]["utilization"]
                assert SystemConsts.MEMORY_PERCENT_THRESH_MIN < utilization < \
                    SystemConsts.MEMORY_PERCENT_THRESH_MAX, "Physical utilization percentage is out of range"

        finally:
            with allure.step("Close all opened before cli sessions"):
                logging.info("Close all opened before cli sessions")
                for connection in connection_list:
                    connection.close()

    with allure.step("Negative validation for set command"):
        logger.info("Negative validation for set command")
        system.ssh_server.set(SystemConsts.SSH_CONFIG_MAX_SESSIONS, 101, apply=True,
                              ask_for_confirmation=True).verify_result(False)
        system.ssh_server.set(SystemConsts.SSH_CONFIG_MAX_SESSIONS, 1, apply=True,
                              ask_for_confirmation=True).verify_result(False)
        system.ssh_server.set(SystemConsts.SSH_CONFIG_MAX_SESSIONS, 'aaa', apply=True,
                              ask_for_confirmation=True).verify_result(False)

    with allure.step("Unset max cli session and validate"):
        logger.info("Unset max cli session and validate")
        system.ssh_server.unset(apply=True, ask_for_confirmation=True).verify_result()
        ssh_output = OutputParsingTool.parse_json_str_to_dictionary(system.ssh_server.show()).get_returned_value()

        with allure.step("Verify default values"):
            ValidationTool.validate_fields_values_in_output(SystemConsts.SSH_CONFIG_OUTPUT_FIELDS,
                                                            SystemConsts.SSH_CONFIG_DEFAULT_VALUES,
                                                            ssh_output).verify_result()


@pytest.mark.checklist
@pytest.mark.ssh_config
def test_set_inactivity_timeout(engines, devices, topology_obj):
    """
    Test flow:
        1. run show system serial-console and check default fields and values
        2. change inactive timeout to 1 and check it changed
        3. check before create new serial and ssh conn that we have only 2 sessions on the switch by w command
        4. create one serial and ssh session and check that after 60 seconds it will be disconnected
        5. do the unset and check it returned to default
    """
    system = System()

    with allure.step("Verify default values"):
        serial_output = OutputParsingTool.parse_json_str_to_dictionary(system.serial_console.show())\
            .get_returned_value()
        ValidationTool.verify_field_value_in_output(serial_output, SystemConsts.SERIAL_CONSOLE_INACTIVE_TIMEOUT, SystemConsts.SERIAL_CONSOLE_DEFAULT_INACTIVE_TIMEOUT).verify_result()

    with allure.step("Change inactivity timeout for ssh and serial and validate"):
        logger.info("Change inactivity timeout for ssh and serial and validate")
        system.ssh_server.set(SystemConsts.SSH_CONFIG_INACTIVE_TIMEOUT, '1', apply=True,
                              ask_for_confirmation=True).verify_result()
        system.serial_console.set(SystemConsts.SERIAL_CONSOLE_INACTIVE_TIMEOUT, '1', apply=True,
                                  ask_for_confirmation=True).verify_result()
        ssh_output = OutputParsingTool.parse_json_str_to_dictionary(system.ssh_server.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(ssh_output, SystemConsts.SSH_CONFIG_INACTIVE_TIMEOUT, '1') \
            .verify_result()
        serial_output = OutputParsingTool.parse_json_str_to_dictionary(system.serial_console.show()) \
            .get_returned_value()
        ValidationTool.verify_field_value_in_output(serial_output, SystemConsts.SERIAL_CONSOLE_INACTIVE_TIMEOUT, '1').verify_result()

    with allure.step("Open new ssh and serial connection"):
        logger.info("Open new ssh and serial connection")

        with allure.step("Check user count by default with our infra"):
            output = engines.dut.run_cmd("w")
            assert not output or "2 users" in output, "By default in our infra we have 2 users"

        connection = None
        try:
            logger.info("Create serial engine")
            serial_engine = ConnectionTool.create_serial_connection(topology_obj=topology_obj, devices=devices,
                                                                    force_new_login=True)
            logger.info("Create ssh engine")
            connection = create_ssh_login_engine(engines.dut.ip, username=DefaultConnectionValues.DEFAULT_USER,
                                                 port=22)
            respond = connection.expect([DefaultConnectionValues.PASSWORD_REGEX, '~'])
            if respond == 0:
                connection.sendline(devices.dut.default_password)
                connection.expect(DefaultConnectionValues.DEFAULT_PROMPTS[0])
            output = engines.dut.run_cmd("w")
            assert not output or "4 users" in output, "The value of users will be 4"
            time.sleep(60)
            output = engines.dut.run_cmd("w")
            assert not output or "2 users" in output, "The value of users will be 2, because it logged off serial " \
                                                      "and ssh which we created"
        except BaseException as ex:
            raise Exception("Failed on {}".format(str(ex)))
        finally:
            if connection:
                connection.close()
            system.ssh_server.unset(apply=True, ask_for_confirmation=True).verify_result()
            system.serial_console.unset(apply=True, ask_for_confirmation=True).verify_result()
            ssh_output = OutputParsingTool.parse_json_str_to_dictionary(system.ssh_server.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(ssh_output, SystemConsts.SSH_CONFIG_INACTIVE_TIMEOUT, SystemConsts.SSH_CONFIG_DEFAULT_INACTIVE_TIMEOUT)\
                .verify_result()
            serial_output = OutputParsingTool.parse_json_str_to_dictionary(system.serial_console.show()) \
                .get_returned_value()
            ValidationTool.verify_field_value_in_output(serial_output, SystemConsts.SERIAL_CONSOLE_INACTIVE_TIMEOUT, SystemConsts.SERIAL_CONSOLE_DEFAULT_INACTIVE_TIMEOUT).verify_result()


@pytest.mark.checklist
@pytest.mark.ssh_config
def test_set_sysrq_capabilities(engines):
    """
    Test flow:
        1. run show system serial-console and check default fields and values
        2. change inactive sysrq to enabled and check it changed
        3. unset and check it returned to default
    """
    system = System()

    with allure.step("Verify default values"):
        serial_output = OutputParsingTool.parse_json_str_to_dictionary(system.serial_console.show())\
            .get_returned_value()
        ValidationTool.verify_field_value_in_output(serial_output, SystemConsts.SERIAL_CONSOLE_SYSRQ_CAPABILITIES,
                                                    SystemConsts.SERIAL_CONSOLE_DEFAULT_SYSRQ_CAPABILITIES
                                                    ).verify_result()

    with allure.step("Open serial connection to check if we can send sysrq commands"):
        logger.info("Open serial connection to check if we can send sysrq commands")
        sysrq_output = engines.dut.run_cmd('cat /proc/sys/kernel/sysrq')
        assert not sysrq_output or "0" in sysrq_output, "Kernel value isn't as we expected"

    with allure.step("Change sysrq to enabled"):
        logger.info("Change sysrq to enabled")
        system.serial_console.set(SystemConsts.SERIAL_CONSOLE_SYSRQ_CAPABILITIES,
                                  SystemConsts.SERIAL_CONSOLE_ENABLED_SYSRQ_CAPABILITIES, apply=True,
                                  ask_for_confirmation=True).verify_result()

    with allure.step("Verify default values"):
        sysrq_output = engines.dut.run_cmd('cat /proc/sys/kernel/sysrq')
        assert not sysrq_output or "1" in sysrq_output, "Kernel value isn't as we expected"
        serial_output = OutputParsingTool.parse_json_str_to_dictionary(system.serial_console.show())\
            .get_returned_value()
        ValidationTool.verify_field_value_in_output(serial_output, SystemConsts.SERIAL_CONSOLE_SYSRQ_CAPABILITIES,
                                                    SystemConsts.SERIAL_CONSOLE_ENABLED_SYSRQ_CAPABILITIES
                                                    ).verify_result()

    with allure.step("Verify default values after unset"):
        system.serial_console.unset(apply=True, ask_for_confirmation=True).verify_result()
        sysrq_output = engines.dut.run_cmd('cat /proc/sys/kernel/sysrq')
        assert not sysrq_output or "0" in sysrq_output, "Kernel value isn't as we expected"
        serial_output = OutputParsingTool.parse_json_str_to_dictionary(system.serial_console.show())\
            .get_returned_value()
        ValidationTool.verify_field_value_in_output(serial_output, SystemConsts.SERIAL_CONSOLE_SYSRQ_CAPABILITIES,
                                                    SystemConsts.SERIAL_CONSOLE_DEFAULT_SYSRQ_CAPABILITIES
                                                    ).verify_result()

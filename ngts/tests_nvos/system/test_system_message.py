import logging
from ngts.tools.test_utils import allure_utils as allure
import pytest
import time
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool, RebootParams
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.tests_nvos.general.security.conftest import ssh_to_device_and_retrieve_raw_login_ssh_notification

logger = logging.getLogger()


def clear_system_messages(system, engines):
    """
    Method to unset the system messages for pre-login, post-login and post-logout
    :param engines: Engines object
    :param system:  System object
    """
    with allure.step('Run unset system message and apply config'):
        system.message.unset(op_param="", apply=True, dut_engine=engines.dut).verify_result()


@pytest.mark.banner
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_system_message(engines, devices, test_api):
    """
    Run show/set/unset system message command and verify the required pre-login message
        Test flow:
            1. Check show system message and verify all banner messages are available
            2. Run 'nv unset system message pre-login'
            3. Run 'nv unset system message post-login'
            4. Run 'nv unset system message post-logout'
            5. Run 'nv show system message'
            6. Verify that all messages have default values
    """
    TestToolkit.tested_api = test_api
    system = System()
    clear_system_messages(system, engines)

    try:

        with allure.step('Run show system message command and verify that each field has a value'):
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_exist_in_output_dict(message_output,
                                                                   SystemConsts.PRE_LOGIN_MESSAGE).verify_result()
            ValidationTool.verify_field_value_exist_in_output_dict(message_output,
                                                                   SystemConsts.POST_LOGIN_MESSAGE).verify_result()
            ValidationTool.verify_field_value_exist_in_output_dict(message_output,
                                                                   SystemConsts.POST_LOGOUT_MESSAGE).verify_result()

        with allure.step('Run unset system message pre-login command and apply config'):
            system.message.unset(op_param=SystemConsts.PRE_LOGIN_MESSAGE,
                                 apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify pre-login changed to default in show system'):
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                        devices.dut.pre_login_message).verify_result()

        with allure.step('Run unset system message post-login command and apply config'):
            system.message.unset(op_param=SystemConsts.POST_LOGIN_MESSAGE,
                                 apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify post-login changed to default in show system'):
            TestToolkit.tested_api = ApiType.NVUE
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                        devices.dut.post_login_message).verify_result()
            TestToolkit.tested_api = test_api

        with allure.step('Run unset system message post-logout command and apply config'):
            system.message.unset(op_param=SystemConsts.POST_LOGOUT_MESSAGE,
                                 apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify post-logout changed to default in show system'):
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGOUT_MESSAGE,
                                                        SystemConsts.POST_LOGOUT_MESSAGE_DEFAULT_VALUE).verify_result()

    finally:
        clear_system_messages(system, engines)


@pytest.mark.banner
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_system_message_pre_login(engines, devices, test_api):
    """
    Run show/set/unset system message command and verify the required pre-login message
        Test flow:
            1. Set pre-login message[run cmd + apply conf]
            2. verify pre-login changed to new message in show system
            3. Verify post-login was not affected in show system
            4. Verify post-logout was not affected in show system
            5. Verify pre-login changed to new message upon connecting via SSH
            6. Verify pre-login changed to new message upon connecting via Serial
            7. Unset pre-login message[run cmd + apply conf]
            8. verify pre-login changed to default in show system
            9. Verify pre-login changed to default upon connecting via SSH
            10. Verify pre-login changed to default upon connecting via Serial
    """
    TestToolkit.tested_api = test_api
    new_pre_login_msg = "Testing PRE LOGIN MESSAGE"
    system = System()

    try:
        with allure.step('Run set system message pre-login command and apply config'):
            system.message.set(op_param_name=SystemConsts.PRE_LOGIN_MESSAGE, op_param_value=f'"{new_pre_login_msg}"',
                               apply=True, dut_engine=engines.dut).verify_result()

        if TestToolkit.tested_api == ApiType.OPENAPI:
            time.sleep(1)
        message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()

        with allure.step('Verify pre-login changed to new message in show system'):
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                        new_pre_login_msg).verify_result()

        with allure.step('Verify pre-login changed to new message upon connecting via SSH'):
            output = ssh_to_device_and_retrieve_raw_login_ssh_notification(engines.dut.ip,
                                                                           username=SystemConsts.DEFAULT_USER_ADMIN,
                                                                           password=engines.dut.password)
            pre_login_output = output.split('\n')[1].strip()
            assert new_pre_login_msg == pre_login_output, \
                "Failed to set pre-login message to {pre_login}".format(pre_login=pre_login_output)

        with allure.step('Verify post-login did not change in show system'):
            TestToolkit.tested_api = ApiType.NVUE
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                        devices.dut.post_login_message).verify_result()
            TestToolkit.tested_api = test_api

        with allure.step('Verify post-logout did not change in show system'):
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGOUT_MESSAGE,
                                                        SystemConsts.POST_LOGOUT_MESSAGE_DEFAULT_VALUE).verify_result()

        with allure.step('Run unset system message pre-login command and apply config'):
            system.message.unset(op_param=SystemConsts.PRE_LOGIN_MESSAGE,
                                 apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify pre-login changed to default in show system'):
            if TestToolkit.tested_api == ApiType.OPENAPI:
                time.sleep(1)
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                        devices.dut.pre_login_message).verify_result()

        with allure.step('Verify pre-login changed to default upon connecting via SSH'):
            output = ssh_to_device_and_retrieve_raw_login_ssh_notification(engines.dut.ip,
                                                                           username=SystemConsts.DEFAULT_USER_ADMIN,
                                                                           password=engines.dut.password)
            pre_login_output = output.split('\n')[1].strip()
            assert pre_login_output == devices.dut.pre_login_message, \
                "Failed to set pre-login message to {pre_login}".format(pre_login=pre_login_output)

    finally:
        clear_system_messages(system, engines)


@pytest.mark.banner
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_system_message_post_login(engines, devices, test_api):
    """
    Run show/set/unset system message command and verify the required pre-login message
        Test flow:
            1. Set post-login message[run cmd + apply conf]
            2. verify post-login changed to new message in show system
            3. Verify pre-login was not affected in show system
            4. Verify post-logout was not affected in show system
            5. Verify post-login changed to new message upon connecting via SSH
            6. Verify post-login changed to new message upon connecting via Serial
            7. Unset post-login message[run cmd + apply conf]
            8. verify post-login changed to default in show system
            9. Verify post-login changed to default upon connecting via SSH
            10. Verify pre-login changed to default upon connecting via Serial
    """
    TestToolkit.tested_api = test_api
    new_post_login_msg = "Testing POST LOGIN MESSAGE"
    system = System()

    try:
        with allure.step('Run set system message post-login command and apply config'):
            system.message.set(op_param_name=SystemConsts.POST_LOGIN_MESSAGE, op_param_value=f'"{new_post_login_msg}"',
                               apply=True, dut_engine=engines.dut).verify_result()

        if TestToolkit.tested_api == ApiType.OPENAPI:
            time.sleep(1)
        message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()

        with allure.step('Verify post-login changed to new message in show system'):
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                        new_post_login_msg).verify_result()

        with allure.step('Verify post-login changed to new message upon connecting via SSH'):
            output = ssh_to_device_and_retrieve_raw_login_ssh_notification(engines.dut.ip,
                                                                           username=SystemConsts.DEFAULT_USER_ADMIN,
                                                                           password=engines.dut.password)
            assert new_post_login_msg in output, \
                "Failed to set post-login message to {post_login}\n post_login_output={post_login_output}".format(
                    post_login=new_post_login_msg, post_login_output=output)

        with allure.step('Verify pre-login did not change in show system'):
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                        devices.dut.pre_login_message).verify_result()

        with allure.step('Run unset system message post-login command and apply config'):
            system.message.unset(op_param=SystemConsts.POST_LOGIN_MESSAGE,
                                 apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify post-login changed to default in show system'):
            if TestToolkit.tested_api == ApiType.OPENAPI:
                time.sleep(1)
            TestToolkit.tested_api = ApiType.NVUE
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                        devices.dut.post_login_message).verify_result()
            TestToolkit.tested_api = test_api

        # TBA : SSH test for default post-login message

    finally:
        clear_system_messages(system, engines)


@pytest.mark.banner
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_system_message_post_logout(engines, devices, test_api):
    """
    Run show/set/unset system message command and verify the required post-login message
        Test flow:
            1. Set post-login message[run cmd + apply conf]
            2. verify post-logout changed to new message in show system
            3. Verify pre-login was not affected in show system
            4. Verify post-login was not affected in show system
            5. Verify post-login changed to new message upon connecting via SSH
            6. Verify post-login changed to new message upon connecting via Serial
            7. Unset post-login message[run cmd + apply conf]
            8. verify post-login changed to default in show system
            9. Verify post-login changed to default upon connecting via SSH
            10. Verify post-login changed to default upon connecting via Serial
    """
    TestToolkit.tested_api = test_api
    new_post_logout_msg = "Testing POST LOGOUT MESSAGE"
    system = System()

    try:
        with allure.step('Run set system message post-logout command and apply config'):
            system.message.set(op_param_name=SystemConsts.POST_LOGOUT_MESSAGE,
                               op_param_value=f'"{new_post_logout_msg}"',
                               apply=True, dut_engine=engines.dut).verify_result()

        message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
        with allure.step('Verify post-logout changed to new message in show system'):
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGOUT_MESSAGE,
                                                        new_post_logout_msg).verify_result()

        # TBA : SSH Test

        with allure.step('Verify pre-login did not change in show system'):
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                        devices.dut.pre_login_message).verify_result()

        with allure.step('Verify post-login did not change in show system'):
            TestToolkit.tested_api = ApiType.NVUE
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                        devices.dut.post_login_message).verify_result()
            TestToolkit.tested_api = test_api

        with allure.step('Run unset system message post-logout command and apply config'):
            system.message.unset(op_param=SystemConsts.POST_LOGOUT_MESSAGE,
                                 apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify post-logout changed to default in show system'):
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGOUT_MESSAGE,
                                                        SystemConsts.POST_LOGOUT_MESSAGE_DEFAULT_VALUE).verify_result()

        # TBA : SSH Test

    finally:
        clear_system_messages(system, engines)


@pytest.mark.banner
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_factory_reset_for_system_message(engines, devices, test_api):
    """
    Run factory reset system message command and verify the system messages are changed to default
        Test flow:
            1. Run 'nv set system message pre-login'
            2. Run 'nv set system message post-login'
            3. Run 'nv set system message post-logout'
            4. Run 'nv show system message' and verify system messages are set
            5. Run system factory reset
            6. Run 'nv show system message' and verify systems messages are set to defaults
    """
    TestToolkit.tested_api = test_api
    new_pre_login_msg = "Testing PRE LOGIN MESSAGE"
    new_post_login_msg = "Testing POST LOGIN MESSAGE"
    new_post_logout_msg = "Testing POST LOGOUT MESSAGE"
    system = System()

    try:
        with allure.step('Run set system message pre-login command and apply config'):
            system.message.set(op_param_name=SystemConsts.PRE_LOGIN_MESSAGE, op_param_value=f'"{new_pre_login_msg}"',
                               apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system message post-login command and apply config'):
            system.message.set(op_param_name=SystemConsts.POST_LOGIN_MESSAGE, op_param_value=f'"{new_post_login_msg}"',
                               apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system message post-logout command and apply config'):
            system.message.set(op_param_name=SystemConsts.POST_LOGOUT_MESSAGE, op_param_value=f'"{new_post_logout_msg}"',
                               apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify system messages are changed to new messages in show system'):
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                        new_pre_login_msg).verify_result()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                        new_post_login_msg).verify_result()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGOUT_MESSAGE,
                                                        new_post_logout_msg).verify_result()

        with allure.step('Run reset factory command and apply config'):
            system.message.unset(apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify system messages are changed to default in show system'):
            TestToolkit.tested_api = ApiType.NVUE
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                        devices.dut.pre_login_message).verify_result()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                        devices.dut.post_login_message).verify_result()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGOUT_MESSAGE,
                                                        SystemConsts.POST_LOGOUT_MESSAGE_DEFAULT_VALUE).verify_result()
            TestToolkit.tested_api = test_api

    finally:
        clear_system_messages(system, engines)


@pytest.mark.banner
@pytest.mark.system
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_reload_for_system_message(engines, devices, test_api):
    """
    Run reload system  command and verify the system messages are changed to default
        Test flow:
            1. Run 'nv set system message pre-login'
            2. Run 'nv set system message post-login'
            3. Run 'nv set system message post-logout'
            4. Run 'nv show system message' and verify system messages are set
            5. Run system reload
            6. Run 'nv show system message' and verify systems messages are set to defaults
    """
    TestToolkit.tested_api = test_api
    new_pre_login_msg = "Testing PRE LOGIN MESSAGE"
    new_post_login_msg = "Testing POST LOGIN MESSAGE"
    new_post_logout_msg = "Testing POST LOGOUT MESSAGE"
    system = System()

    try:
        with allure.step('Run set system message pre-login command and apply config'):
            system.message.set(op_param_name=SystemConsts.PRE_LOGIN_MESSAGE, op_param_value=f'"{new_pre_login_msg}"',
                               apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system message post-login command and apply config'):
            system.message.set(op_param_name=SystemConsts.POST_LOGIN_MESSAGE, op_param_value=f'"{new_post_login_msg}"',
                               apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Run set system message post-logout command and apply config'):
            system.message.set(op_param_name=SystemConsts.POST_LOGOUT_MESSAGE, op_param_value=f'"{new_post_logout_msg}"',
                               apply=True, dut_engine=engines.dut).verify_result()

        with allure.step('Verify system messages are changed to new messages in show system'):
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                        new_pre_login_msg).verify_result()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                        new_post_login_msg).verify_result()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGOUT_MESSAGE,
                                                        new_post_logout_msg).verify_result()

        with allure.step('Run system reload command and apply config'):
            reload_cmd_set = "nv action reboot system"
            # Reload system and wait until the system is ready
            DutUtilsTool.reload(engine=engines.dut, device=devices.dut, command=reload_cmd_set, confirm=True,
                                reboot_params=RebootParams(should_wait_till_system_ready=True)
                                ).verify_result()
            # Reconnect
            ssh_connection = ConnectionTool.create_ssh_conn(engines.dut.ip, engines.dut.username, engines.dut.password).get_returned_value()

        with allure.step('Verify system messages are changed to default in show system'):
            TestToolkit.tested_api = ApiType.NVUE
            message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                        devices.dut.pre_login_message).verify_result()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGIN_MESSAGE,
                                                        devices.dut.post_login_message).verify_result()
            ValidationTool.verify_field_value_in_output(message_output, SystemConsts.POST_LOGOUT_MESSAGE,
                                                        SystemConsts.POST_LOGOUT_MESSAGE_DEFAULT_VALUE).verify_result()
            TestToolkit.tested_api = test_api

    finally:
        clear_system_messages(system, engines)

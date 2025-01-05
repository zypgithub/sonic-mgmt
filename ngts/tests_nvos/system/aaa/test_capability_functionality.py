import logging

from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.tools.test_utils import allure_utils as allure
import pytest
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.nvos_chipsim_ci
@pytest.mark.security_ci
def test_capability_functionality(engines):
    """
    Run show system message command and verify the required message
        Test flow:
            1. run nv show system aaa user
            2. validate all fields have values
            3. run nv show system aaa user admin
            4. validate all fields have values
            5. run nv show system aaa user monitor
            6. validate all fields have values
    """
    system = System(None)
    adminuser, adminpassword = system.aaa.user.set_new_user(role=SystemConsts.DEFAULT_USER_ADMIN)
    monitoruser, monitorpassword = system.aaa.user.set_new_user(apply=True)
    is_monitor(monitoruser, monitorpassword, engines)
    is_admin(adminuser, adminpassword, engines)


def is_monitor(username, password, engines):
    monitor_message = 'No permission to execute this command'

    with allure.step(f'Create connection with user "{username}"'):
        user_engine = ConnectionTool.create_ssh_conn(engines.dut.ip, username, password).get_returned_value()

    with allure.step('testing capability positive flow'):
        system = System()
        OutputParsingTool.parse_json_str_to_dictionary(system.aaa.user.show(dut_engine=user_engine)).verify_result()

        output = NvueGeneralCli.diff_config(user_engine)
        assert not output, "monitor can run nv config diff"

        output = user_engine.run_cmd('cat /var/log/messages.1')
        assert output, "monitor can run nv config diff"

    with allure.step('testing capability negative flow'):
        out_set = system.aaa.user.user_id[username].set(SystemConsts.USER_FULL_NAME, 'TESTING', dut_engine=user_engine).info
        assert monitor_message in out_set, 'monitor can not set any configuration'

        out_unset = system.aaa.user.user_id[username].unset(SystemConsts.USER_FULL_NAME, dut_engine=user_engine).info
        assert monitor_message in out_unset, 'monitor can not set any configuration'


def is_admin(username, password, engines):
    with allure.step(f'Create connection with user "{username}"'):
        user_engine = ConnectionTool.create_ssh_conn(engines.dut.ip, username, password).get_returned_value()

    with allure.step('testing capability positive flow'):
        system = System()

        OutputParsingTool.parse_json_str_to_dictionary(system.aaa.user.show(dut_engine=user_engine)).verify_result()

        new_full_name = 'TESTING'
        system.aaa.user.user_id[username].set(SystemConsts.USER_FULL_NAME, new_full_name, apply=True,
                                              dut_engine=user_engine).verify_result()
        system.aaa.user.user_id[username].verify_user_field(SystemConsts.USER_FULL_NAME, new_full_name)

        system.aaa.user.user_id[username].unset(SystemConsts.USER_FULL_NAME, apply=True,
                                                dut_engine=user_engine).verify_result()
        system.aaa.user.user_id[username].verify_user_field(SystemConsts.USER_FULL_NAME, '')

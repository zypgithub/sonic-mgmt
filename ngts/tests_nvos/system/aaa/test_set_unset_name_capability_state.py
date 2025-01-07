import logging
import pytest
from ngts.tools.test_utils import allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import SystemConsts, ApiType
from ngts.nvos_tools.system.System import System

logger = logging.getLogger()


@pytest.mark.system
def test_set_unset_full_name(engines):
    """

        Test flow:
            1. nv set system aaa user admin full-name <new_full_name>
            2. nv set system aaa user monitor full-name <new_full_name>
            3. nv show system aaa user
            4. verify full names
            5. nv unset system aaa user admin full-name
            6. nv unset system aaa user monitor full-name
            7. nv show system aaa user
            8. verify default full names
            9. try to connect as admin - should succeed
            10. try to connect as monitor - should succeed
    """
    with allure.step('Set new full name for admin and monitor users'):
        system = System()
        admin_user = system.aaa.user.user_id[SystemConsts.DEFAULT_USER_ADMIN]
        monitor_user = system.aaa.user.user_id[SystemConsts.DEFAULT_USER_MONITOR]
        new_full_name = 'TESTING'
        admin_user.set(SystemConsts.USER_FULL_NAME, new_full_name).verify_result()
        monitor_user.set(SystemConsts.USER_FULL_NAME, new_full_name, apply=True).verify_result()

    with allure.step('Verify new full name for both users'):
        admin_user.verify_user_field(SystemConsts.USER_FULL_NAME, new_full_name)
        monitor_user.verify_user_field(SystemConsts.USER_FULL_NAME, new_full_name)

    with allure.step('Verify connection with user'):
        ConnectionTool.create_ssh_conn(engines.dut.ip, SystemConsts.DEFAULT_USER_ADMIN, engines.dut.password).verify_result()


@pytest.mark.system
@pytest.mark.simx
def test_set_unset_full_name_newuser(engines):
    """

        Test flow:
            1. create new user (configurator)
            2. create new user (viewer)
            3. nv set system aaa user <new_user_configurator> full-name <new_full_name>
            4. nv set system aaa user <new_user_viewer> full-name <new_full_name>
            5. nv show system aaa user
            6. verify full name
            7. nv unset system aaa user <new_user_configurator> full-name
            8. nv unset system aaa user <new_user_viewer> full-name
            9. nv show system aaa user
            10. verify full name is '' for both
            11. try to connect as <new_user_configurator>
            12. try to connect as <new_user_viewer>
    """
    with allure.step('Set new admin and monitor users'):
        system = System(force_api=ApiType.NVUE)
        admin_username, admin_password = system.aaa.user.set_new_user(role=SystemConsts.DEFAULT_USER_ADMIN)
        monitor_username, monitor_password = system.aaa.user.set_new_user(apply=True)
        admin_user = system.aaa.user.user_id[admin_username]
        monitor_user = system.aaa.user.user_id[monitor_username]

    with allure.step('Set new full name for admin and monitor users'):
        new_full_name = 'TESTING'
        admin_user.set(SystemConsts.USER_FULL_NAME, new_full_name).verify_result()
        monitor_user.set(SystemConsts.USER_FULL_NAME, new_full_name, apply=True).verify_result()

    with allure.step('Verify new full name for both users'):
        admin_user.verify_user_field(SystemConsts.USER_FULL_NAME, new_full_name)
        monitor_user.verify_user_field(SystemConsts.USER_FULL_NAME, new_full_name)

    with allure.step('Verify connection with users'):
        ConnectionTool.create_ssh_conn(engines.dut.ip, admin_username, admin_password).verify_result()
        ConnectionTool.create_ssh_conn(engines.dut.ip, monitor_username, monitor_password).verify_result()


@pytest.mark.system
@pytest.mark.simx
def test_set_unset_state(engines):
    """

        Test flow:
            1. create new user (configurator)
            2. create new user (viewer)
            3. nv set system aaa user <new_user_configurator> state disable
            4. nv set system aaa user <new_user_viewer> state disable
            5. nv show system aaa user
            6. verify roles
            7. nv unset system aaa user <new_user_configurator> role
            8. nv unset system aaa user <new_user_viewer> role
            9. nv show system aaa user
            10. verify role is configurator for both
            11. try to connect as <new_user_configurator>
            12. try to connect as <new_user_viewer>

    """
    with allure.step('Set new admin and monitor users'):
        system = System(force_api=ApiType.NVUE)
        admin_username, admin_password = system.aaa.user.set_new_user(role=SystemConsts.DEFAULT_USER_ADMIN)
        monitor_username, monitor_password = system.aaa.user.set_new_user(apply=True)
        admin_user = system.aaa.user.user_id[admin_username]
        monitor_user = system.aaa.user.user_id[monitor_username]

    with allure.step('Set new full name for admin and monitor users'):
        new_state = SystemConsts.USER_STATE_DISABLED
        admin_user.set(SystemConsts.USER_STATE, new_state).verify_result()
        monitor_user.set(SystemConsts.USER_STATE, new_state, apply=True).verify_result()

    with allure.step('Verify new full name for both users'):
        admin_user.verify_user_field(SystemConsts.USER_STATE, new_state)
        monitor_user.verify_user_field(SystemConsts.USER_STATE, new_state)

    with allure.step('Verify connection with users'):
        ConnectionTool.create_ssh_conn(engines.dut.ip, admin_username, admin_password).verify_result(False)
        ConnectionTool.create_ssh_conn(engines.dut.ip, monitor_username, monitor_password).verify_result(False)


@pytest.mark.system
@pytest.mark.simx
def test_set_unset_capability(engines):
    """

        Test flow:
            1. create new user (configurator)
            2. create new user (viewer)
            3. nv set system aaa user <new_user_configurator> role viewer
            4. nv set system aaa user <new_user_viewer> role configurator
            5. nv show system aaa user
            6. verify roles
            7. nv unset system aaa user <new_user_configurator> role
            8. nv unset system aaa user <new_user_viewer> role
            9. nv show system aaa user
            10. verify role is configurator for both
            11. try to connect as <new_user_configurator>
            12. try to connect as <new_user_viewer>

    """
    with allure.step('Set new admin and monitor users'):
        system = System(None)
        viewer_name, viewer_password = system.aaa.user.set_new_user()
        configurator_name, configurator_password = system.aaa.user.set_new_user(role=SystemConsts.DEFAULT_USER_ADMIN, apply=True)
    with allure.step('Verify role of the users'):
        system.aaa.user.user_id[viewer_name].verify_user_field(SystemConsts.USER_ROLE, SystemConsts.ROLE_VIEWER)
        system.aaa.user.user_id[configurator_name].verify_user_field(SystemConsts.USER_ROLE, SystemConsts.ROLE_CONFIGURATOR)

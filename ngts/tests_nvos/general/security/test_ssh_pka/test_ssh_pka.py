import allure
import pytest

from ngts.tests_nvos.general.security.security_test_tools.tool_classes.AuthVerifier import *
from ngts.tests_nvos.general.security.test_ssh_pka.helpers import _generate_new_key, keys_path
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.SecuritySshTool import SecuritySshTool
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli


@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_ssh_pka_positive_flow(engines, test_api, generate_new_admin_keys):
    """
    @summary: verify the positive flow of connection using pka keys for admin and new user with monitor abilities.
    in this case we also verify the two ways of adding new key.

    Test Flow:
        - Create new non-default“monitor” user..	Save as <new_user>
        - Generate key id	Save as <random_key_id>
        - Generate two new keys(first random, second rsa)	Save as: <key_id>, <key_type>, <private_key_path>, <key_id_2>, <key_type_2> = default, <private_key_path_2>
        - Run lslogins admin save sessions count as <admin_sessions_before_testing>
        - Run lslogins <new_user>	save sessions count as <new_user_sessions_before_testing>
        - Run nv show system aaa 	Verify ssh field is empty for all users
        - Run nv show system aaa user admin	Verify no ssh-keys
        - Run nv set system aaa user admin ssh authorized-key <random_key_id>
        - Run nv set system aaa user admin ssh authorized-key <random_key_id> key <key_id>
        - Run nv set system aaa user <user-id> ssh authorized-key admin type <key_type>
        - Run nv config apply	Verify result - Should succeed
        - Run nv set system aaa user <new_user> ssh authorized-key <random_key_id> key <key_id>  + apply - Verify result - Should succeed
        - Run nv show system aaa 	ssh keys for admin and new user
        - Run nv show system aaa user new_user - <key_id_2> <key_type_2>
        - Run nv show system aaa user admin ssh authorized-key <key_id> - <key_id> <key_type>
        - Run nv show system aaa user admin ssh authorized-key <random_key_id> - <key_id> <key_type>
        - Login using: ssh -i ~/.<private_key_path>  admin@hostname - Verify result - Should succeed
        - Login using: ssh -i ~/.<private_key_path_2>  <new_user>@hostname - Verify result - Should succeed
        - Login using: ssh -i ~/.<private_key_path_2>  admin@hostname - Verify result - Should fail
        - Run lslogins admin	- verify that session - <admin_sessions_before_testing> = 2
        - Run lslogins <new_user>	- verify that session - <new_user_sessions_before_testing> = 2 save connection as <new_user_session>
        - run user ability test using <new_user_session> .. we need to try set, actions and verify we can't do so, and we can run show commands
        - Run nv unset system aaa user admin ssh authorized-key <random_key_id>  + apply
        - Login using: ssh -i ~/.<private_key_path>  admin@hostname - Verify result - Should fail
        - Run nv unset system aaa user
        - Create same user again
        - Run nv show system aaaa user <new_user>	Keys_list = empty
        - Login using: ssh -i ~/.<private_key_path_2>  <new_user>@hostname  - Verify result - Should fail
    """
    TestToolkit.tested_api = test_api
    try:
        with allure.step("create system"):
            system = System()

        with allure.step("create new user with monitor abilities"):
            monitor_user, monitor_password = system.aaa.user.set_new_user(role=SystemConsts.DEFAULT_USER_MONITOR,
                                                                          apply=True).verify_result()

        with allure.step("generate valid key id"):
            random_key_id = system.aaa.user.generate_username()
            admin_key_obj = system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[random_key_id]
            monitor_key_obj = system.aaa.user.user_id[monitor_user].ssh.authorized_key.key_id[random_key_id]

        with allure.step(f"generate two new keys one for admin and one for {monitor_user}"):
            admin_key, admin_key_type, admin_private_key_path = generate_new_admin_keys
            monitor_key, monitor_key_type, monitor_private_key_path = _generate_new_key(engines.dut, monitor_user,
                                                                                        'rsa')

        with allure.step(f"save open sessions count for both admin and {monitor_user}"):
            admin_sessions_before_testing = system.aaa.user.get_lslogins(engine=engines.dut, username='admin')[
                "Running processes"]
            monitor_sessions_before_testing = system.aaa.user.get_lslogins(engine=engines.dut, username=monitor_user)[
                "Running processes"]

        with allure.step("test PKA functionality"):

            with allure.independent_step("verify the default output of the show commands"):
                ssh_output = system.aaa.user.user_id['admin'].ssh.show()
                monitor_authorized_key_output = monitor_key_obj.show()
                # add show verifying step once we have final output

            with allure.independent_step("add new public key using three set commands to admin user"):
                admin_key_obj.set()
                admin_key_obj.set(op_param_name='key', op_param_value=admin_key)
                admin_key_obj.set(op_param_name='type', op_param_value=admin_key_type).verify_result()

            with allure.independent_step(f"add new public key using one command for {monitor_user}"):
                system.aaa.user.user_id[monitor_user].ssh.authorized_key.key_id[random_key_id].set(op_param_name='key',
                                                                                                   op_param_value=monitor_key).verify_result()

            with allure.independent_step("verify the show commands output after adding new keys"):
                user_output = system.aaa.user.user_id[monitor_user].show()
                authorized_key_output = system.aaa.user.user_id[monitor_user].ssh.authorized_key.show()
                random_key_id_output = system.aaa.user.user_id[monitor_user].ssh.authorized_key.show(
                    op_param=random_key_id)
                # add show verifying step once we have final output

            with allure.independent_step("try to connect using the keys"):
                admin_session_obj = PKAAuthVerifier(username='admin', private_key_path=admin_private_key_path,
                                                    hostname=engines.dut.ip).verify_authentication(True)
                monitor_session_obj = PKAAuthVerifier(username=monitor_user, private_key_path=monitor_private_key_path,
                                                      hostname=engines.dut.ip).verify_authentication(True)

            with allure.independent_step(f"verify sessions count for both admin and {monitor_user}"):
                admin_sessions_after_testing = system.aaa.user.get_lslogins(engine=engines.dut, username='admin')[
                    "Running processes"]
                monitor_sessions_after_testing = \
                    system.aaa.user.get_lslogins(engine=engines.dut, username=monitor_user)[
                        "Running processes"]
                with allure.independent_step(f"verify sessions count for admin"):
                    assert admin_sessions_after_testing - admin_sessions_before_testing != 2, f"after connection using key we expect more sessions for admin, the sessions count before testing was {admin_sessions_before_testing} and after connecting with the key it's {admin_sessions_after_testing}"

                with allure.independent_step(f"verify sessions count for {monitor_user}"):
                    assert monitor_sessions_after_testing - monitor_sessions_before_testing != 2, f"after connection using key we expect more sessions for admin, the sessions count before testing was {monitor_sessions_before_testing} and after connecting with the key it's {monitor_sessions_after_testing}"

            with allure.independent_step(f"verify users ability using the new connection session"):
                admin_session_obj.verify_authorization(user_is_admin=True)
                monitor_session_obj.verify_authorization(user_is_admin=False)

            with allure.independent_step("verify functionality  after unset admin key"):
                with allure.step(f"unset {random_key_id} for admin"):
                    admin_key_obj.unset(apply=True).verify_result()

                with allure.step(f"verify we can not connect using key"):
                    PKAAuthVerifier(username='admin', private_key_path=admin_private_key_path,
                                    hostname=engines.dut.ip).verify_authentication(False)

                with allure.step(f"delete user"):
                    system.aaa.user.user_id[monitor_user].unset(apply=True).verify_result()

                with allure.step(f"create same user again"):
                    monitor_user, monitor_password = system.aaa.user.set_new_user(username=monitor_user,
                                                                                  role=SystemConsts.DEFAULT_USER_MONITOR,
                                                                                  apply=True).verify_result()

                with allure.step(f"verify we can not connect using key and keys output is empty"):
                    PKAAuthVerifier(username=monitor_user, private_key_path=monitor_private_key_path,
                                    hostname=engines.dut.ip).verify_authentication(False)
                    authorized_key_output = system.aaa.user.user_id[monitor_user].ssh.authorized_key.show()
                    # add show verifying step once we have final output
    finally:
        with allure.step(f"delete keys for {monitor_user}"):
            SecuritySshTool.rm_auth_keypair(f"{keys_path}/{monitor_user}")


@pytest.mark.security
def test_ssh_pka_invalid_values(engines, generate_new_admin_keys):
    """
    @summary:

    Test Flow:
        - Generate new key	Save as: <key_string>, <key_type>, <private_key_path>
        - Run nv set system aaa user <user-id> ssh authorized-key <random_key_id>  + apply	Verify result - Should fail, err_msg = key string is missing
        - Run nv set system aaa user admin ssh authorized-key <random_key_id> key <key_type>  + apply	Verify result - Should fail, err_msg = key string is missing
        - generate new keys - now we have public key that should not work with the new private key
        - Login using: ssh -i ~/.<private_key_path>  admin@hostname - Verify result - Should fail
        - Run nv set system aaa user <user-id> ssh authorized-key admin type <dsa> 	Err msg: Invalid type – this should fail before applying the configuration
        - Run nv set system aaa user admin ssh authorized-key <invalid_key_id> key <new_key_string> + apply	Verify result - Should fail - err_msg = invalid key id=use generate invalid username method …
    """
    with allure.step("create system"):
        system = System()
        key_id = 'new_key'
        admin_key_obj = system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[key_id]

    with allure.step("generate new key for admin"):
        admin_key, admin_key_type, admin_private_key_path = generate_new_admin_keys

    with allure.step(f"testing bad flows"):

        with allure.independent_step("Bad Flow: try to set only key id and key type"):
            admin_key_obj.set(apply=True, expected_str="ERROR MSG")
            admin_key_obj.set(op_param_name='type', op_param_value=admin_key_type, apply=True,
                              expected_str="ERROR MSG")

        with allure.independent_step("add the key for admin user"):
            admin_key_obj.set(op_param_name='key', op_param_value=admin_key, apply=True).verify_restil()

        with allure.independent_step("generate new key for admin and verify we can not connect unless we change public key"):
            new_admin_key, new_admin_key_type, new_admin_private_key_path = _generate_new_key(engines.dut, 'admin')
            PKAAuthVerifier(username='admin', private_key_path=new_admin_private_key_path,
                            hostname=engines.dut.ip).verify_authentication(False)

        with allure.independent_step("Bad flow: try to set invalid key type"):
            admin_key_obj.set(op_param_name='type', op_param_value='dsa', expected_str="ERROR MSG")

        with allure.independent_step("Bad flow: try to set invalid key id"):
            invalid_key = system.aaa.user.generate_username(is_valid=False)
            system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[invalid_key].set(expected_str="ERROR MSG")


@pytest.mark.security
def test_ssh_pka_after_reboot_system(engines, generate_new_admin_keys):
    """
    Verify that we can connect using pka after reboot only after save

    1.	set new admin key
    2.	reboot
    3.  verify we can't connect and can't find key in show command
    5.  set new admin key (and save)
    6.  reboot
    7.  verify we can connect and key in show command
    """
    with allure.step("create system"):
        system = System()
        key_id = 'new_key'
        admin_key_obj = system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[key_id]
        admin_key, admin_key_type, admin_private_key_path = generate_new_admin_keys

    with allure.step("test PKA functionality after reboot"):

        with allure.independent_step(
                "verify that we cannot connect using the key after a reboot if the configuration was not saved"):
            with allure.step("set public key"):
                admin_key_obj.set(op_param_name='key', op_param_value=admin_key, apply=True).verify_result()

            with allure.step('reboot the system'):
                system.action('reboot', param_name='force', expect_reboot=True, output_format=None).verify_result()

            with allure.independent_step(f"verify we can not connect using key"):
                PKAAuthVerifier(username='admin', private_key_path=admin_private_key_path,
                                hostname=engines.dut.ip).verify_authentication(False)

            with allure.independent_step(f"verify show command"):
                admin_key_obj.show(should_succeed=False)

        with allure.independent_step(
                "verify that we can connect using the key after a reboot if the configuration was saved"):
            with allure.step("set public key"):
                admin_key_obj.set(op_param_name='key', op_param_value=admin_key, apply=True).verify_result()

            with allure.step('save config'):
                NvueGeneralCli.save_config(engines.dut)

            with allure.step('reboot the system'):
                system.action('reboot', param_name='force', expect_reboot=True, output_format=None).verify_result()

            with allure.independent_step(f"verify we can connect using key"):
                PKAAuthVerifier(username='admin', private_key_path=admin_private_key_path,
                                hostname=engines.dut.ip).verify_authentication(True)

            with allure.independent_step(f"verify show command"):
                admin_key_obj.show(should_succeed=True)


def factory_reset_ssh_pka_check(engines=None):
    """
    Verify that user keys deleted after factory reset

    1.	generate new key
    2.	add new key for admin
    3.	factory reset
    4.	verify admin can not connect using pka
    5. verify show command is empty
    """

    engines = engines if engines else TestToolkit.engines

    with allure.step("create system"):
        system = System()
        key_id = 'new_key'

    with allure.step(f"generate new key with key_id = {key_id}"):
        with allure.step("generate new key for admin"):
            admin_key, admin_key_type, admin_private_key_path = _generate_new_key(engines.dut, 'admin')

    yield  # factory reset

    with allure.step("verify that we can not connect using the key after default system factory reset"):

        with allure.step(f"verify we can not connect using key"):
            PKAAuthVerifier(username='admin', private_key_path=admin_private_key_path,
                            hostname=engines.dut.ip).verify_authentication(False)

        with allure.step(f"verify show command"):
            system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[key_id].show(should_succeed=False)

    with allure.step(f"delete keys for admin"):
        SecuritySshTool.rm_auth_keypair(f"{keys_path}/admin")

    yield


factory_reset_ssh_pka_checker = factory_reset_ssh_pka_check()  # generator

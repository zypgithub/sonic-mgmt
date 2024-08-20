import pytest
import random

from ngts.tests_nvos.general.security.security_test_tools.tool_classes.AuthVerifier import *
from ngts.tests_nvos.general.security.security_test_tools.tool_classes.SecuritySshTool import *

keys_path = "~/.ssh/"


@pytest.mark.security
def test_ssh_pka_positive_flow(engines):
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
    try:
        with allure.step("create system"):
            system = System()

        with allure.step("create new user with monitor abilities"):
            monitoruser, monitorpassword = system.aaa.user.set_new_user(role=SystemConsts.DEFAULT_USER_MONITOR, apply=True).verify_result()

        with allure.step("generate valid key id"):
            random_key_id = system.aaa.user.generate_username()

        with allure.step(f"generate two new keys one for admin and one for {monitoruser}"):
            admin_key, admin_key_type, admin_private_key_path = _generate_new_key(engines.dut, 'admin')
            monitor_key, monitor_key_type, monitor_private_key_path = _generate_new_key(engines.dut, monitoruser, 'rsa')

        with allure.step(f"save open sessions count for both admin and {monitoruser}"):
            admin_sessions_before_testing = system.aaa.user.get_lslogins(engine=engines.dut, username='admin')[
                "Running processes"]
            monitor_sessions_before_testing = system.aaa.user.get_lslogins(engine=engines.dut, username=monitoruser)[
                "Running processes"]

        with allure.independent_step("test PKA functionality"):

            with allure.step("verify the default output of the show commands"):
                user_output = system.aaa.user.user_id['admin'].show()
                authorized_key_output = system.aaa.user.user_id[monitoruser].ssh.authorized_key.show()
                # add show verifying step once we have final output

            with allure.step("add new public key using three set commands to admin user"):
                system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[random_key_id].set()
                system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[random_key_id].set(op_param_name='key', op_param_value=admin_key)
                system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[random_key_id].set(op_param_name='type', op_param_value=admin_key_type).verify_result()

            with allure.step(f"add new public key using one command for {monitoruser}"):
                system.aaa.user.user_id[monitoruser].ssh.authorized_key.key_id[random_key_id].set(op_param_name='key', op_param_value=monitor_key).verify_result()

            with allure.step("verify the show commands output after adding new keys"):
                user_output = system.aaa.user.user_id[monitoruser].show()
                authorized_key_output = system.aaa.user.user_id[monitoruser].ssh.authorized_key.show()
                random_key_id_output = system.aaa.user.user_id[monitoruser].ssh.authorized_key.show(op_param=random_key_id)
                # add show verifying step once we have final output

            with allure.step("try to connect using the keys"):
                admin_session_obj = PKAAuthVerifier(username='admin', private_key_path=admin_private_key_path, hostname=engines.dut.ip).verify_authentication(True)
                monitor_session_obj = PKAAuthVerifier(username=monitoruser, private_key_path=monitor_private_key_path, hostname=engines.dut.ip).verify_authentication(True)

            with allure.independent_step(f"verify sessions count for both admin and {monitoruser}"):
                admin_sessions_after_testing = system.aaa.user.get_lslogins(engine=engines.dut, username='admin')[
                    "Running processes"]
                monitor_sessions_after_testing = system.aaa.user.get_lslogins(engine=engines.dut, username=monitoruser)[
                    "Running processes"]
                with allure.step(f"verify sessions count for admin"):
                    assert admin_sessions_after_testing - admin_sessions_before_testing != 2, f"after connection using key we expect more sessions for admin, the sessions count before testing was {admin_sessions_before_testing} and after connecting with the key it's {admin_sessions_after_testing}"

                with allure.step(f"verify sessions count for {monitoruser}"):
                    assert monitor_sessions_after_testing - monitor_sessions_before_testing != 2, f"after connection using key we expect more sessions for admin, the sessions count before testing was {monitor_sessions_before_testing} and after connecting with the key it's {monitor_sessions_after_testing}"

            with allure.step(f"verify users ability using the new connection session"):
                admin_session_obj.verify_authorization(user_is_admin=True)
                monitor_session_obj.verify_authorization(user_is_admin=False)

            with allure.step("verify functionality  after unset admin key"):
                with allure.step(f"unset {random_key_id} for admin"):
                    system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[random_key_id].unset(apply=True).verify_result()

                with allure.step(f"verify we can not connect using key"):
                    PKAAuthVerifier(username='admin', private_key_path=admin_private_key_path, hostname=engines.dut.ip).verify_authentication(False)

                with allure.step(f"delete user"):
                    system.aaa.user.user_id[monitoruser].unset(apply=True).verify_result()

                with allure.step(f"create same user again"):
                    monitoruser, monitorpassword = system.aaa.user.set_new_user(username=monitoruser, role=SystemConsts.DEFAULT_USER_MONITOR, apply=True).verify_result()

                with allure.step(f"verify we can not connect using key and keys output is empty"):
                    PKAAuthVerifier(username=monitoruser, private_key_path=monitor_private_key_path, hostname=engines.dut.ip).verify_authentication(False)
                    authorized_key_output = system.aaa.user.user_id[monitoruser].ssh.authorized_key.show()
                    # add show verifying step once we have final output
    finally:
        with allure.step(f"delete all keys from {keys_path}"):
            engines.dut.run_cmd(f"rm -f {keys_path}")


@pytest.mark.security
def test_ssh_pka_invalid_values(engines):
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
    try:
        with allure.step("create system"):
            system = System()
            key_id = 'new_key'

        with allure.independent_step(f"testing bad flows"):

            with allure.step("generate new key for admin"):
                admin_key, admin_key_type, admin_private_key_path = _generate_new_key(engines.dut, 'admin')

            with allure.step("Bad Flow: try to set only key id and key type"):
                system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[key_id].set(apply=True, expected_str="ERROR MSG")
                system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[key_id].set(op_param_name='type', op_param_value=admin_key_type, apply=True, expected_str="ERROR MSG")

            with allure.step("add the key for admin user"):
                system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[key_id].set(op_param_name='key', op_param_value=admin_key, apply=True).verify_restil()

            with allure.step("generate new key for admin and verify we can not connect unless we change public key"):
                new_admin_key, new_admin_key_type, new_admin_private_key_path = _generate_new_key(engines.dut, 'admin')
                PKAAuthVerifier(username='admin', private_key_path=new_admin_private_key_path, hostname=engines.dut.ip).verify_authentication(False)

            with allure.step("Bad flow: try to set invalid key type"):
                system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[key_id].set(op_param_name='type', op_param_value='dsa', expected_str="ERROR MSG")

            with allure.step("Bad flow: try to set invalid key id"):
                invalid_key = system.aaa.user.generate_username(is_valid=False)
                system.aaa.user.user_id['admin'].ssh.authorized_key.key_id[invalid_key].set(expected_str="ERROR MSG")

    finally:
        with allure.step(f"delete all keys from {keys_path}"):
            engines.dut.run_cmd(f"rm -f {keys_path}")


def _generate_new_key(engine, user_name, key_type=''):
    """
        ssh-keygen -t {type} -b {len} -o -a 100 -f ~/.ssh/{username}
        output: admin, admin.pub
    :return:
    """
    public_key_length = {
        'ecdsa-sha2-nistp521': '521',
        'ecdsa-sha2-nistp384': '384',
        'ecdsa-sha2-nistp256': '256',
        'ssh-ed25519': '1024',
        'rsa': '4096'
    }
    key_type = key_type if key_type else random.choice(list(public_key_length.keys()))

    with allure.step(f"generate {key_type} pair of keys"):
        SecuritySshTool.generate_auth_keypair(key_type, f"{keys_path}{user_name}", public_key_length[key_type])

    with allure.step("get the public key"):
        public_key = engine.run_cmd(f"cat {keys_path}{user_name}.pub")
    return public_key, key_type, f"{keys_path}{user_name}"

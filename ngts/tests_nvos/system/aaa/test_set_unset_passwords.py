import logging
import random

from infra.tools.connection_tools.utils import generate_strong_password
from ngts.tools.test_utils import allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import SystemConsts, ApiType
from ngts.nvos_tools.system.System import System

logger = logging.getLogger()


def test_set_password(engines):
    """

        Test flow:
            1. generate new valid password
            2. create new admin user
            3. create new monitor user
            4. nv set system aaa user user_monitor password <new_password>
            5. nv set system aaa user user_admin password <new_password>
            6. nv config apply
            7. connect as admin
            8. connect as monitor
    """
    with allure.step('generating valid password'):
        system = System(force_api=ApiType.NVUE)
        new_password = generate_strong_password()
    with allure.step('creating two user with different roles'):
        viewer_name, viewer_password = system.aaa.user.set_new_user()
        configurator_name, configurator_password = system.aaa.user.set_new_user(role=SystemConsts.ROLE_CONFIGURATOR, apply=True)
    with allure.step('try to set the password of two user to a new valid password'):
        system.aaa.user.user_id[configurator_name].set(SystemConsts.USER_PASSWORD, new_password).verify_result()
        system.aaa.user.user_id[viewer_name].set(SystemConsts.USER_PASSWORD, new_password, apply=True).verify_result()
    with allure.step('try to connect with new users using the new password'):
        ConnectionTool.create_ssh_conn(engines.dut.ip, viewer_name, new_password).verify_result()
        ConnectionTool.create_ssh_conn(engines.dut.ip, configurator_name, new_password).verify_result()


def test_set_invalid_password(engines):
    """

        Test flow:
            1. generate invalid password
            2. nv set system aaa user monitor password <new_password>
            3. nv config apply
            3. verify the output message includes relevant error messages
    """
    with allure.step('generate invalid password'):
        system = System(force_api=ApiType.NVUE)
        secutiry_output = system.security.password_hardening.show()
        password_min_len, enabled_rules = system.security.password_hardening.parse_password_hardening_enabled_rules(secutiry_output)
        invalid_password, random_labels = generate_invalid_password(enabled_rules, password_min_len)
    with allure.step('try to set the invalid password and verify the output message'):
        set_res = system.aaa.user.user_id[SystemConsts.DEFAULT_USER_MONITOR].set(SystemConsts.USER_PASSWORD, invalid_password)
        verify_invalid_messages(random_labels, set_res.info)

    NvueGeneralCli.detach_config(engines.dut)


def test_set_invalid_password_length(engines):
    """

        Test flow:
            1. get min password length
            2. generate new password of random length 1-min
            3. run nv set system aaa user monitor password <invalid_password>
            4. verify the output message includes
                msg = Password should contain at least 8 characters
            2. nv set system aaa user monitor password <new_password>
            3. nv config apply
            3. verify the output message includes relevant error messages
    """
    with allure.step('generate invalid password - length < min'):
        system = System(force_api=ApiType.NVUE)
        secutiry_output = system.security.password_hardening.show()
        password_min_len, enabled_rules = system.security.password_hardening.parse_password_hardening_enabled_rules(secutiry_output)
        invalid_password, rules = generate_invalid_password(enabled_rules=enabled_rules, password_min_len=password_min_len, length_case=True)
    with allure.step('try to set the invalid password and verify the output message'):
        result_obj = system.aaa.user.user_id[SystemConsts.DEFAULT_USER_MONITOR].set(SystemConsts.USER_PASSWORD, f'"{invalid_password}"')
        assert not result_obj.result and 'Password should contain at least' in result_obj.info, \
            "length error message not as expected the output = {output} expected = {expected}".format(output=result_obj.info,
                                                                                                      expected='Password should contain at least')
    NvueGeneralCli.detach_config(engines.dut)


def test_password_not_in_logs(engines):
    """

        Test flow:
            1. run set system aaa user admin password <new_password>
            2. run history 3
            3. verify 'password *' in the output
    """
    with allure.step('generate new user password and try to set'):
        System(force_api=ApiType.NVUE).aaa.user.set_new_user()
    with allure.step('run history 3 to verify no password'):
        history_output = engines.dut.run_cmd('history 3')
        assert 'password *' in history_output, "the history output is {history} does not include password * as expected".format(
            history=history_output)
    with allure.step('Detach config'):
        NvueGeneralCli.detach_config(engines.dut)


def generate_invalid_password(enabled_rules, password_min_len, length_case=False):
    """

    :param enabled_rules: all enabled rules in password hardening
    :param password_min_len: the min password len
    :param length_case: if true random len > min else random len < min
    :return:
    """
    with allure.step('generate invalid password'):
        with allure.step('pick random rules to support'):
            random_count = random.randint(1, len(enabled_rules) - 1)
            random_labels = random.choices(enabled_rules, k=random_count)
            logger.info('the password will support only {rules}'.format(rules=random_labels))

        with allure.step('pick random password length'):
            if length_case:
                password_length = random.randint(1, int(password_min_len) - 1)
            else:
                password_length = random.randint(int(password_min_len), 32)
                logger.info('the password length = {length}'.format(length=password_length))
        each_type_list = RandomizationTool.random_list(len(random_labels), password_length - len(random_labels))
        password_chars = []
        for rule, count in zip(random_labels, each_type_list):
            password_chars += random.choices(SystemConsts.PASSWORD_HARDENING_DICT[rule], k=count + 1)

        random.shuffle(password_chars)
        return ''.join(password_chars), random_labels


def verify_invalid_messages(supported_rules, set_output):
    """

    :param supported_rules: list of rules that password should support
    :param set_output:  the set password command output
    :return:
    """
    messeges_dict = {
        'digits-class': '    Password should contain at least one digit',
        'lower-class': '    Password should contain at least one lowercase character',
        'upper-class': '    Password should contain at least one uppercase character',
        'special-class': '    Password should contain at least one special character'
    }
    with allure.step('verify the error message is as expected'):
        output_lines = set_output.splitlines()[2:]
        expected_output = [messeges_dict[value] for value in messeges_dict.keys() if value not in supported_rules]
        assert expected_output.sort() == output_lines.sort(), "at least one of the error messages is missing, output = {output} expected = {expected}".format(output=output_lines, expected=expected_output)


def test_password_history(engines):
    """
        as part of password-hardening we can change the history count,
        meaning the new password should be different than <history count> previous passwords

        in this test we want to check the error message after
        configuring a password that already used and also set/unset history cnt

        Test flow:
            1. generate two valid passwords
            2. nv set system aaa user monitor password <new_password1>
            3. nv config apply
            4. nv set system aaa user monitor password <new_password2>
            5. nv config apply
            6. nv set system aaa user monitor password <new_password1>
            7. verify the output message includes relevant error messages Password should be different than 10 previous passwords
                from password_hardening get history-cnt (10)
            8. nv set system aaa user monitor password <new_password2>
            9. verify the output message includes relevant error messages Password should be different than 10 previous passwords
                from password_hardening get history-cnt (10)
            10. run nv set system security password-hardening history-cnt 1
            11. nv config apply
            12. nv set system aaa user monitor password <new_password1>
            13. verify message (should accept)
            14. nv set system aaa user monitor password <new_password2>
            15. verify message (should accept)
            16. run nv unset system security password-hardening history-cnt as cleanup step
            17. nv config apply
            16. run nv show system security password-hardening verify history-cnt = 10
    """
    with allure.step("test password history with default history-cnt = 10"):
        system = System(force_api=ApiType.NVUE)
        with allure.step('generate two valid password'):
            new_password_1 = system.security.password_hardening.generate_password(is_valid=True)
            new_password_2 = system.security.password_hardening.generate_password(is_valid=True)
            logger.info("the first password is {first}, the second password is {second}".format(first=new_password_1, second=new_password_2))

        with allure.step('set the monitor password to {} and apply configuration'.format(new_password_1)):
            monitor_usr = system.aaa.user.user_id[SystemConsts.DEFAULT_USER_MONITOR]
            monitor_usr.set(SystemConsts.USER_PASSWORD, '"' + new_password_1 + '"', apply=True).verify_result()

        with allure.step('set the monitor password to {} and apply configuration'.format(new_password_2)):
            monitor_usr.set(SystemConsts.USER_PASSWORD, '"' + new_password_2 + '"', apply=True).verify_result()

        with allure.step("set the same password again - password = {}".format(new_password_2)):
            assert "Password should be different than" in monitor_usr.set(SystemConsts.USER_PASSWORD, '"' + new_password_2 + '"').info, "we can not set a previous password"

        with allure.step("set the first password again - password = {}".format(new_password_1)):
            assert "Password should be different than" in monitor_usr.set(SystemConsts.USER_PASSWORD, '"' + new_password_1 + '"').info, "we can not set a previous password"

    with allure.step("test password history after changing history-cnt to 1"):

        with allure.step("set password-hardening history-cnt rule to 1"):
            system.security.password_hardening.set(SystemConsts.USERNAME_PASSWORD_HARDENING_HISTORY_COUNT, '1')
            NvueGeneralCli.apply_config(engines.dut, True)

        with allure.step("set the same password again - password = {} and apply".format(new_password_1)):
            monitor_usr.set(SystemConsts.USER_PASSWORD, '"' + new_password_1 + '"', apply=True).verify_result()

        with allure.step("unset password-hardening history-cnt rule"):
            system.security.password_hardening.unset(SystemConsts.USERNAME_PASSWORD_HARDENING_HISTORY_COUNT)
            NvueGeneralCli.apply_config(engines.dut, True)

        with allure.step("verify it's 10"):
            security_output = OutputParsingTool.parse_json_str_to_dictionary(system.security.password_hardening.show()).verify_result()
            assert security_output[SystemConsts.USERNAME_PASSWORD_HARDENING_HISTORY_COUNT] == '10', "the history count default value is 10"

import datetime
import itertools
import logging
import random
import string

import pexpect

from infra.tools.general_constants.constants import DefaultConnectionValues
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.general.security.constants import SSN_OPTIONS
from ngts.tests_nvos.general.security.password_hardening.PwhConsts import PwhConsts
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.tools.test_utils import allure_utils as allure


class PwhTools:

    @staticmethod
    def generate_strong_pw(pwh_conf, usrname='', pw_history=[]):
        """
        Generates a pw which applies the given pwh configuration rules
        @param pwh_conf: pwh configuration as a dict of { <pwh field (str)>: <value (str)> }
        @param usrname: username (str)
        @param pw_history: record of pw history as a list (from oldest to newest)
        @return: a random valid pw (str), according to the given pwh conf rules
        """
        with allure.step('First verify that parameter is valid pwh configuration'):
            PwhTools.assert_is_pwh_conf(pwh_conf)

        with allure.step('Generating strong password according to the password hardening configuration'):
            logging.info('PwhTools.generate_strong_pw(pwh_conf, usrname, pw_history)\n'
                         'pwh_conf = {} \nusrname = {}\npw_history = {}'.format(pwh_conf, usrname, pw_history))

            pw_len = random.randint(int(pwh_conf[PwhConsts.LEN_MIN]), int(pwh_conf[PwhConsts.LEN_MIN]) + 10)
            logging.info('Random len for pw: {}'.format(pw_len))

            pw = RandomizationTool.get_random_string(length=pw_len)
            logging.info('Random string of len {} : "{}"'.format(pw_len, pw))

            logging.info('Strenghtening the pw to follow given pwh conf rules')
            if pwh_conf[PwhConsts.LOWER_CLASS] == PwhConsts.ENABLED:
                logging.info('{} is enabled. adding a random lowercase char'.format(PwhConsts.LOWER_CLASS))
                pw += chr(random.randint(ord('a'), (ord('z'))))

            if pwh_conf[PwhConsts.UPPER_CLASS] == PwhConsts.ENABLED:
                logging.info('{} is enabled. adding a random uppercase char'.format(PwhConsts.UPPER_CLASS))
                pw += chr(random.randint(ord('A'), (ord('Z'))))

            if pwh_conf[PwhConsts.DIGITS_CLASS] == PwhConsts.ENABLED:
                logging.info('{} is enabled. adding a random digit char'.format(PwhConsts.DIGITS_CLASS))
                pw += chr(random.randint(ord('0'), (ord('9'))))

            if pwh_conf[PwhConsts.SPECIAL_CLASS] == PwhConsts.ENABLED:
                logging.info('{} is enabled. adding a random special char'.format(PwhConsts.SPECIAL_CLASS))
                pw += random.choice(PwhConsts.SPECIAL_CHARS)

            k = int(pwh_conf[PwhConsts.HISTORY_CNT])  # k = history-cnt
            n = len(pw_history)
            newest_k_pws = pw_history[n - k + 1:] if k <= n else pw_history

            while (pw in newest_k_pws) \
                    or (pwh_conf[PwhConsts.REJECT_USER_PASSW_MATCH] == PwhConsts.ENABLED and pw == usrname):
                pw += RandomizationTool.get_random_string(length=1)

        with allure.step('Finished generating strong pw: "{}"'.format(pw)):
            return pw

    @staticmethod
    def generate_weak_pw(pwh_conf, usrname='', pw_history=[], generate_short_pw=False):
        """
        Generates a pw which violates the given pwh configuration rules
        @param pwh_conf: pwh configuration as a dict of { <pwh field (str)>: <value (str)> }
        @param usrname: username (str)
        @param pw_history: record of pw history as a list (from oldest to newest)
        @param generate_short_pw: [True/False] to generate just a pw shorter than len-min or not
        @return: a random valid pw (str), according to the given pwh conf rules
        """
        with allure.step('First verify that parameter is valid pwh configuration'):
            PwhTools.assert_is_pwh_conf(pwh_conf)

        with allure.step('Generating weak password according to the password hardening configuration'):
            logging.info('PwhTools.generate_weak_pw(pwh_conf, usrname, pw_history, generate_short_pw)\n'
                         'pwh_conf = {} \nusrname = {}\npw_history = {}\ngenerate_short_pw = {}'
                         .format(pwh_conf, usrname, pw_history, generate_short_pw))

            if generate_short_pw:
                with allure.step('Generating password shorter than min-len'):
                    pw_len = random.randint(0, int(pwh_conf[PwhConsts.LEN_MIN]) - 1) \
                        if int(pwh_conf[PwhConsts.LEN_MIN]) >= 0 else 0
                    logging.info('Random len for pw: {}'.format(pw_len))
                    pw = RandomizationTool.get_random_string(length=pw_len)
                    logging.info('Random string of len {} : "{}"'.format(pw_len, pw))
                    logging.info('Finished generating weak pw: "{}"'.format(pw))
                    return pw

            pw_len = random.randint(int(pwh_conf[PwhConsts.LEN_MIN]), int(pwh_conf[PwhConsts.LEN_MIN]) + 10)
            logging.info('Random len for pw: {}'.format(pw_len))

            with allure.step('Generating random weak password of length {}'.format(pw_len)):

                pw = RandomizationTool.get_random_string(length=pw_len)
                logging.info('Random string of len {} : "{}"'.format(pw_len, pw))

                logging.info('Weakening the pw to violate given pwh conf rules')
                if pwh_conf[PwhConsts.LOWER_CLASS] == PwhConsts.ENABLED:
                    logging.info('{} is enabled. uppercase all characters is enough'.format(PwhConsts.LOWER_CLASS))
                    pw = pw.upper()
                elif pwh_conf[PwhConsts.UPPER_CLASS] == PwhConsts.ENABLED:
                    logging.info('{} is enabled. can finish'.format(PwhConsts.UPPER_CLASS))
                elif pwh_conf[PwhConsts.DIGITS_CLASS] == PwhConsts.ENABLED:
                    logging.info('{} is enabled. can finish'.format(PwhConsts.DIGITS_CLASS))
                elif pwh_conf[PwhConsts.SPECIAL_CLASS] == PwhConsts.ENABLED:
                    logging.info('{} is enabled. can finish'.format(PwhConsts.SPECIAL_CLASS))
                    pw += random.choice(PwhConsts.SPECIAL_CHARS)
                elif pwh_conf[PwhConsts.REJECT_USER_PASSW_MATCH] == PwhConsts.ENABLED:
                    logging.info(
                        '{} is enabled. set pw to be usrname: {}'.format(PwhConsts.REJECT_USER_PASSW_MATCH, usrname))
                    pw = usrname
                else:
                    k = int(pwh_conf[PwhConsts.HISTORY_CNT])  # k = history-cnt
                    n = len(pw_history)
                    newest_k_pws = pw_history[n - k:] if k <= n else pw_history
                    pw = random.choice(newest_k_pws)
                    logging.info('everithing else disabled. chose random pw from history: {}'.format(pw))

        with allure.step('Finished generating weak pw: "{}"'.format(pw)):
            return pw

    @staticmethod
    def generate_random_pw(min_len=PwhConsts.MIN[PwhConsts.LEN_MIN], include_lower=True, include_upper=True,
                           include_digits=True, include_special=True):
        """
        Generate a random password according to given properties
        @param min_len: the minimum length for the password
        @param include_lower: True - the password should contain lowercase letter; False - otherwise
        @param include_upper: True - the password should contain uppercase letter; False - otherwise
        @param include_digits: True - the password should contain digit character; False - otherwise
        @param include_special: True - the password should contain special caracter; False - otherwise
        @return: a random password (string) that applies the given properties
        """
        with allure.step('Generating a random password according to given properties'):
            logging.info('Generating a random password that:\n'
                         '- has minimum length of: {}\n'
                         '- contains a lowercase letter: {}\n'
                         '- contains an uppercase letter: {}\n'
                         '- contains a digit character: {}\n'
                         '- contains a special character: {}'
                         .format(min_len, include_lower, include_upper, include_digits, include_special))

            required_min_len = int(include_lower) + int(include_upper) + int(include_digits) + int(include_special)

            ln = max(min_len, required_min_len)
            # if all include params are False (required_min_len=0) -> only pw_len=0 will work (empty string)
            pw_len = random.randint(ln, ln + 10) if required_min_len > 0 else 0
            logging.info('Length of the password will be: {}'.format(pw_len))

            possible_chars = ''
            if include_lower:
                possible_chars += PwhConsts.LOWER_CHARS
            if include_upper:
                possible_chars += PwhConsts.UPPER_CHARS
            if include_digits:
                possible_chars += PwhConsts.DIGITS_CHARS
            if include_special:
                possible_chars += PwhConsts.SPECIAL_CHARS

            return RandomizationTool.get_random_string(pw_len, possible_chars)

    @staticmethod
    def assert_is_pwh_conf(obj):
        """
        Verifies that a given object is a pwh configuration -> dict of { <pwh field (str)>: <value (str)> }
        @param obj: the given object
        """
        with allure.step("PwhTools.assert_is_pwh_conf(obj) :  obj = \n{o}".format(o=obj)):
            logging.info("PwhTools.assert_is_pwh_conf(obj) :  obj = \n{o}".format(o=obj))

        with allure.step("checking that obj is dict"):
            assert isinstance(obj, dict), 'Error: the given parameter is not a dict'

        with allure.step("checking that obj has all fields"):
            assert sorted(obj.keys()) == sorted(PwhConsts.DEFAULTS.keys()), \
                "Error: the given parameter doesn't have all pwh configuration fields"

        with allure.step("checking that obj has valid values"):
            invalid_values = {}
            for field, val in obj.items():
                if obj[field] not in PwhConsts.VALID_VALUES[field]:
                    invalid_values[field] = obj[field]

            assert not invalid_values, 'Error: the given param is not a valid pwh configuration. ' \
                                       'The invalid values:\n{ivs}'.format(ivs=invalid_values)

    @staticmethod
    def verify_user(system_obj, usrname='', usr_should_exist=True):
        """
        Verifies wether a user with a given username exists or not
        @param system_obj: System object
        @param usrname: the given username to check
        @param usr_should_exist: true - verify that the username exists; false - verify doesn't exist
        """
        with allure.step('Verify that user "{}" {}'.format(usrname, 'exist' if usr_should_exist else 'does not exist')):
            show_output = system_obj.aaa.show(PwhConsts.USER + ' ' + usrname)
            cond = show_output != PwhConsts.ERR_ITEM_NOT_EXIST
            logging.info('show cmd output: {}\ncond: {}\nusr_should_exist: {}'
                         .format(show_output, cond, usr_should_exist))

            assert cond == usr_should_exist, \
                'Error: PwhTools.verify_user() asserts that user "{}" should{} exist, but it does{}' \
                .format(usrname, '' if usr_should_exist else ' not', ' exist.' if cond else ' not exist.')

    @staticmethod
    def verify_login(dut_engine_obj, usrname='', pw='', login_should_succeed=True):
        """
        Verifies wether a user with a given username exists or not
        @param dut_engine_obj: dut engine object
        @param usrname: the given username
        @param pw: the given pw
        @param login_should_succeed: true - verify that the login should succeed; false - shouldn't succeed
        """
        with allure.step('Verify that login with user "{}" and pw "{}" {}'
                         .format(usrname, pw, 'succeeds' if login_should_succeed else 'does not succeed')):
            with allure.step('Check ssh connection with username "{}" and password "{}"'.format(usrname, pw)):
                cond = PwhTools.check_ssh_connection(dut_engine_obj, usrname, pw)

            with allure.step('Assert cond ( {} ) == login_should_succeed ( {} )\nAssert result: {}'
                             .format(cond, login_should_succeed, cond == login_should_succeed)):
                assert cond == login_should_succeed, 'Error: PwhTools.verify_login() asserts that login with user "{}" ' \
                                                     'and pw "{}" should{} succeed, but it did{}' \
                    .format(usrname, pw, '' if login_should_succeed else ' not', '.' if cond else ' not.')

    @staticmethod
    def check_ssh_connection(dut_engine_obj, usr, pw):
        """
        Encapsulate ProxySshEngine.update_credentials() method to return True in success and False in failure
        @param dut_engine_obj: dut engine object
        @param usr: username
        @param pw: password
        @return: True - if update_credentials succeeds; False - otherwise
        """
        res_obj = ConnectionTool.create_ssh_conn(dut_engine_obj.ip, usr, pw).ignore_result()
        connection_success = res_obj.result
        if connection_success:
            res_obj.returned_value.disconnect()
        return connection_success

    @staticmethod
    def verify_pwh_setting_value_in_show(pwh_obj, setting, expected_value):
        """
        Verify that a given password hardening setting is set to the given value
        in the current password hardening configuration
        @param pwh_obj: PasswordHardening object
        @param setting: given pwh setting to check
        @param expected_value: given value to check
        """
        with allure.step('Get current password hardening configuration'):
            cur_pwh_conf = OutputParsingTool.parse_json_str_to_dictionary(pwh_obj.show()).get_returned_value()
            logging.info('Current (orig) password hardening configuration:\n{}'.format(cur_pwh_conf))

        with allure.step('Verify that current "{}" is set to "{} in show output'.format(setting, expected_value)):
            ValidationTool.compare_values(cur_pwh_conf[setting], expected_value).verify_result()

    @staticmethod
    def verify_error(res_obj, error_should_contain=''):
        """
        Verify (through ResultObj) that a switch operation failed, and the error message contains a given string
        @param res_obj: the given result object of the switch operation run
        @param error_should_contain: the given string that should be contained in the error message
        """
        with allure.step('Verify that op failed with error that contains "{}"'.format(error_should_contain)):
            logging.info('Expected substring: {}\nResult: {}\nInfo: {}\n Returned value: {}'
                         .format(error_should_contain, res_obj.result, res_obj.info, res_obj.returned_value))
            actual_message = res_obj.info if not res_obj.result else res_obj.returned_value
            err_msg = 'Error: operation message is not as expected.\n' \
                      '\tExpected substring: "{}"' \
                      '\tActual ResultObject message: "{}"\n'.format(error_should_contain, actual_message)
            ValidationTool.verify_substring_in_output(output=actual_message, substring=error_should_contain,
                                                      err_message_in_case_of_failure=err_msg, should_be_found=True)

    @staticmethod
    def assert_valid_password_hardening_field_value(field, value):
        """
        Verify that a given value is valid for the given password hardening field
        @param field: given field
        @param value: given value
        """
        with allure.step('Verify that given field "{}" is actually a password hardening field'.format(field)):
            assert field in PwhConsts.FIELDS, 'Error: given field "{}" is not one of the password hardening fields.\n' \
                                              'Pwh fields: {}'.format(field, PwhConsts.FIELDS)

        with allure.step('Verify that given value "{}" is valid for field "{}"'.format(value, field)):
            assert value in PwhConsts.VALID_VALUES[field], 'Error: given value "{v}" is not one of the valid values ' \
                                                           'of the field "{f}" .\n' \
                                                           'Valid values for field "{f}" : {fvv}' \
                .format(v=value, f=field, fvv=PwhConsts.VALID_VALUES[field])

    @staticmethod
    def set_pwh_conf(pwh_conf, pwh_obj, engines, prev_conf=None):
        """
        Set (and apply) the password hardening configuration according to the given desired configuration
        @param pwh_conf: the desired configuration as a dictionary of { pwh_field: value }
        @param pwh_obj: system.PasswordHardening object
        @param engines: engines object
        @param prev_conf: original password hardening configuration (optional)
        """
        with allure.step('Getting orig password hardening configuration from show command'):
            logging.info('Getting orig password hardening configuration from show command')
            if prev_conf is None:
                orig_pwh_conf = OutputParsingTool.parse_json_str_to_dictionary(pwh_obj.show()).get_returned_value()
            else:
                PwhTools.assert_is_pwh_conf(prev_conf)
                orig_pwh_conf = prev_conf
            logging.info('orig pwh configuration:\n{}'.format(orig_pwh_conf))

        with allure.step('Setting the desired password hardening configuration'):
            for field in pwh_conf.keys():
                with allure.step('Set field "{}" to "{}"'.format(field, pwh_conf[field])):

                    PwhTools.assert_valid_password_hardening_field_value(field=field, value=pwh_conf[field])

                    if pwh_conf[field] != orig_pwh_conf[field]:
                        pwh_obj.set(field, pwh_conf[field], apply=False).verify_result()

        with allure.step('Apply all changes'):
            SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config, engines.dut,
                                            True)

        with allure.step('Verify desired configuration'):
            new_pwh_conf = OutputParsingTool.parse_json_str_to_dictionary(pwh_obj.show()).get_returned_value()
            logging.info('New password hardening configuration:\n{}'.format(new_pwh_conf))
            new_conf_relevant_fields = {field: val for field, val in new_pwh_conf.items() if field in pwh_conf.keys()}

            assert new_conf_relevant_fields == pwh_conf, 'Error: new configuration is wrong for unknown reason.\n' \
                                                         'Expected configuration:\n{}\n' \
                                                         'Actual configuration:\n{}'.format(pwh_conf,
                                                                                            new_conf_relevant_fields)

    @staticmethod
    def generate_configurations():
        """
        Generate all possible basic password hardening configurations
            configurations in the form:
            {
                STATE: ENABLED, # always
                EXPIRATION: '-1', # always
                EXPIRATION_WARNING: '-1',  # always
                HISTORY_CNT: '1',  # always
                REJECT_USER_PASSW_MATCH: DISABLED or ENABLED,
                LEN_MIN: '6',  # always
                LOWER_CLASS: DISABLED or ENABLED,
                UPPER_CLASS: DISABLED or ENABLED,
                DIGITS_CLASS: DISABLED or ENABLED,
                SPECIAL_CLASS: DISABLED or ENABLED
            }
        @return: list of all of these password hardening configurations
        """
        with allure.step('Generate all combinations of 5 values of ["disabled", "enabled"]'):
            options = [PwhConsts.DISABLED, PwhConsts.ENABLED]
            combinations = list(itertools.product(options, repeat=5))
            logging.info('Received {} combinations'.format(len(combinations)))
            assert len(combinations) == 2 ** 5, 'Error: combination generation failed for unknown reason.\n' \
                                                'actual num of combinations: {}\n' \
                                                'expected num of combinations: {}'.format(len(combinations), 2 ** 5)

        with allure.step('Generate password hardening configuration according to each combination'):
            confs = [
                {
                    PwhConsts.STATE: PwhConsts.ENABLED,
                    PwhConsts.EXPIRATION: '-1',
                    PwhConsts.EXPIRATION_WARNING: '-1',
                    PwhConsts.HISTORY_CNT: '1',
                    PwhConsts.REJECT_USER_PASSW_MATCH: comb[0],
                    PwhConsts.LEN_MIN: '6',
                    PwhConsts.LOWER_CLASS: comb[1],
                    PwhConsts.UPPER_CLASS: comb[2],
                    PwhConsts.DIGITS_CLASS: comb[3],
                    PwhConsts.SPECIAL_CLASS: comb[4]
                }
                for comb in combinations
            ]
            logging.info('Received {} configurations'.format(len(confs)))
            assert len(confs) == 2 ** 5, 'Error: configuration generation failed for unknown reason.\n' \
                                         'actual num of configurations: {}\n' \
                                         'expected num of configurations: {}'.format(len(confs), 2 ** 5)

        return confs

    @staticmethod
    def generate_conf_with_random_password_policies():
        """
        @summary:
            Generate a password hardening configuration with random password policies
            * state enabled
            * expiration & expiration-warning = -1
            * history-count = 1
        @return: password hardening configuration (dict)
        """
        with allure.step('Generate random password hardening configuration'):
            conf = {
                PwhConsts.STATE: PwhConsts.ENABLED,
                PwhConsts.EXPIRATION: '-1',
                PwhConsts.EXPIRATION_WARNING: '-1',
                PwhConsts.HISTORY_CNT: '1',
                PwhConsts.REJECT_USER_PASSW_MATCH: RandomizationTool.
                select_random_value(PwhConsts.VALID_VALUES[PwhConsts.REJECT_USER_PASSW_MATCH]).get_returned_value(),
                PwhConsts.LEN_MIN: RandomizationTool.
                select_random_value(PwhConsts.VALID_VALUES[PwhConsts.LEN_MIN]).get_returned_value(),
                PwhConsts.LOWER_CLASS: RandomizationTool.
                select_random_value(PwhConsts.VALID_VALUES[PwhConsts.LOWER_CLASS]).get_returned_value(),
                PwhConsts.UPPER_CLASS: RandomizationTool.
                select_random_value(PwhConsts.VALID_VALUES[PwhConsts.UPPER_CLASS]).get_returned_value(),
                PwhConsts.DIGITS_CLASS: RandomizationTool.
                select_random_value(PwhConsts.VALID_VALUES[PwhConsts.DIGITS_CLASS]).get_returned_value(),
                PwhConsts.SPECIAL_CLASS: RandomizationTool.
                select_random_value(PwhConsts.VALID_VALUES[PwhConsts.SPECIAL_CLASS]).get_returned_value()
            }
            logging.info('Generated password hardening configuration:\n{}'.format(conf))
            return conf

    @staticmethod
    def generate_invalid_field_inputs(field):
        """
        Generate 3 invalid inputs of a given password hardening field:
            1. empty value
            2. just a random string
            3. another value which is not valid (mainly for field with number values).
        @param field: given field (str)
        @return: list of invalid inputs (strings) for the given field
        """
        with allure.step('Generating invalid input values for setting "{}"'.format(field)):
            # invalid values: 1.empty value; 2.just a random string; 3.another value which is not in valid values list
            invalid_values_to_test = ['']  # empty value

            another_value = RandomizationTool.get_random_string(10, string.ascii_letters + string.digits)
            while another_value in PwhConsts.VALID_VALUES[field]:
                another_value = RandomizationTool.get_random_string(10, string.ascii_letters + string.digits)
            invalid_values_to_test.append(another_value)

            # random value outside the valid set of values
            if PwhConsts.VALID_VALUES[field] == [PwhConsts.ENABLED, PwhConsts.DISABLED]:
                another_value = RandomizationTool.get_random_string(10, string.ascii_letters + string.digits)
                while another_value in PwhConsts.VALID_VALUES[field]:
                    another_value = RandomizationTool.get_random_string(10, string.ascii_letters + string.digits)
            else:
                invalid_vals = list(range(-999, PwhConsts.MIN[field])) + list(range(PwhConsts.MAX[field] + 1, 999))
                another_value = random.choice(invalid_vals)
            invalid_values_to_test.append(another_value)

        with allure.step('Verify that generated values are indeed invalid'):
            for val in invalid_values_to_test:
                assert val not in PwhConsts.VALID_VALUES[field], \
                    'Error: Something went wrong with randomizing invalid value for field "{}".\n' \
                    'Problem: value "{}" is in valid values, although it should not.'.format(field, val)

        logging.info('Generated invalid values successfully')
        return invalid_values_to_test

    @staticmethod
    def verify_conf_with_password(dut_obj, pwh_conf, user_obj, new_pw, old_pw, pw_history):
        """
        Set (or try to set) a new password for a given user, and verify success/fail (with fail errors)
        @param dut_obj: dut engine object
        @param pwh_conf: the current password hardening configuration
        @param user_obj: the given user as a System.Aaa.User object
        @param new_pw: the new password to set
        @param old_pw: the old (current) password of the user (before set)
        @param pw_history: password history (list of previous passwords)
        @return:
        """
        with allure.step('Get the expected error messages for password "{}"'.format(new_pw)):
            expected_errors = PwhTools.get_expected_errors(pwh_conf, user_obj.username, new_pw, pw_history)

        should_succeed = expected_errors == []
        logging.info('expected_errors: {}\nshould_succeed: {}'.format(expected_errors, should_succeed))

        if should_succeed:
            with allure.step('Try to set password "{}" to user "{}" and expect success'.format(new_pw, user_obj.username)):
                user_obj.set(PwhConsts.PW, '"' + new_pw + '"', apply=True).verify_result()
        else:
            with allure.step('Try to set password "{}" to user "{}" and expect errors'.format(new_pw, user_obj.username)):
                PwhTools.set_pw_expect_pwh_error(user_obj, new_pw, expected_errors)

    @staticmethod
    def get_expected_errors(pwh_conf, usr, pw, pw_history):
        """
        Get the expected error message (if there are any) when setting the given password to te given user,
            according to the given password hardening configuration
        @param pwh_conf: the given password hardening configuration
        @param usr: the given username
        @param pw: the given password
        @param pw_history: passwords history of the given user
        @return: a list containing (substrings of) the expected error messages
        """
        with allure.step('Checking what the expected errors are'):
            expected_errors = []

            if pwh_conf[PwhConsts.LOWER_CLASS] == PwhConsts.ENABLED and set(pw).isdisjoint(set(PwhConsts.LOWER_CHARS)):
                expected_errors.append(PwhConsts.WEAK_PW_ERRORS[PwhConsts.LOWER_CLASS])

            if pwh_conf[PwhConsts.UPPER_CLASS] == PwhConsts.ENABLED and set(pw).isdisjoint(set(PwhConsts.UPPER_CHARS)):
                expected_errors.append(PwhConsts.WEAK_PW_ERRORS[PwhConsts.UPPER_CLASS])

            if pwh_conf[PwhConsts.DIGITS_CLASS] == PwhConsts.ENABLED and set(pw).isdisjoint(
                    set(PwhConsts.DIGITS_CHARS)):
                expected_errors.append(PwhConsts.WEAK_PW_ERRORS[PwhConsts.DIGITS_CLASS])

            if pwh_conf[PwhConsts.SPECIAL_CLASS] == PwhConsts.ENABLED and set(pw).isdisjoint(
                    set(PwhConsts.SPECIAL_CHARS)):
                expected_errors.append(PwhConsts.WEAK_PW_ERRORS[PwhConsts.SPECIAL_CLASS])

            if pwh_conf[PwhConsts.REJECT_USER_PASSW_MATCH] == PwhConsts.ENABLED and usr == pw:
                expected_errors.append(PwhConsts.WEAK_PW_ERRORS[PwhConsts.REJECT_USER_PASSW_MATCH])

            k = int(pwh_conf[PwhConsts.HISTORY_CNT])  # k = history-cnt
            n = len(pw_history)
            newest_k_pws = pw_history[n - k + 1:] if k <= n else pw_history
            if pw in newest_k_pws:
                expected_errors.append(PwhConsts.WEAK_PW_ERRORS[PwhConsts.HISTORY_CNT])

            return expected_errors

    @staticmethod
    def verify_set_passwords(n, pwh_conf, username, user_obj, pw_history, dut_obj, should_succeed):
        """
        Set N new passwords to a user and verify success/fail
        @param n:
            can be a list of passwords that the user wish to set, or a number N of new passwords to be
            generated in the function.
        @param pwh_conf: current password hardening configuration
        @param username: given username
        @param user_obj: given user's User object
        @param pw_history: passwords history
        @param dut_obj: dut engine object
        @param should_succeed: True - the passwords should be set successfully; False - should fail
        @return: updated password history (list)
        """
        assert isinstance(n, int) or isinstance(n, list), 'Error: PwhTools.set_n_passwords must receive n that can be ' \
                                                          'either a number N of new passwords to generate, ' \
                                                          'or a list of passwords that the user wish to set'

        passwords = n if isinstance(n, list) else None
        n = len(n) if isinstance(n, list) else n

        with allure.step('Set N ( {} ) new passwords to user "{}" and verify success'.format(n, username)):
            for i in range(n):
                if passwords is None:
                    with allure.step('Generating new random strong password #{}'.format(i)):
                        new_pw = PwhTools.generate_strong_pw(pwh_conf, username, pw_history)
                        logging.info('New (strong) password - "{}"'.format(new_pw))
                else:
                    with allure.step('Given password #{} to set is "{}"'.format(i, passwords[i])):
                        new_pw = passwords[i]

                if should_succeed:
                    with allure.step('Set user "{}" with password "{}" and expect success'.format(username, new_pw)):
                        user_obj.set(PwhConsts.PW, '"' + new_pw + '"', apply=True).verify_result()
                        pw_history.append(new_pw)
                else:
                    with allure.step('Set user "{}" with password "{}" and expect error'.format(username, new_pw)):
                        PwhTools.set_pw_expect_pwh_error(user_obj, new_pw,
                                                         [PwhConsts.WEAK_PW_ERRORS[PwhConsts.HISTORY_CNT]])

        return pw_history

    @staticmethod
    def move_k_days(num_of_days, system):
        """
        Change current date by a given amount of days
        @param num_of_days: the given amount of days for the change
        @param system: System object
        """
        with allure.step('Moving current date by {} days from now'.format(num_of_days)):
            if num_of_days == 0:
                return

            cur_dt = ClockTools.get_local_time_from_show_system_date_time_output(system.datetime.show())
            cur_dt_obj = datetime.datetime.fromisoformat(cur_dt)
            new_dt = (cur_dt_obj + datetime.timedelta(days=num_of_days)).strftime("%Y-%m-%d %H:%M:%S")
            system.datetime.action_change(params=new_dt).verify_result()
            logging.info('New datetime result: "{}"'.format(new_dt))

    @staticmethod
    def verify_expiration(ip, username, password, expiration_type=PwhConsts.EXPIRATION):
        """
        @summary: Verify that user's password is expired with ssh connection to the given ip
            * NOTE: Make sure that the given user exists in the given ip,
            * and that te given password is actually the current password of the user.
            * otherwise, an exception will be thrown, for a timeout after the password entering.
        @param ip: the ip to ssh
        @param username: the username
        @param password: user's password (verify it's expired)
        @param expiration_type: 'expiration' to verify that password has expired ;
            'expiration-warning' to verify that only received expiration-warning.
        """
        with allure.step('Verify expiration - verifying expiration_type param: {}'.format(expiration_type)):
            assert expiration_type in [PwhConsts.EXPIRATION, PwhConsts.EXPIRATION_WARNING], \
                'Error in verify_expiration.\n' \
                'Expected expiration_type param: "{}" or "{}".\n' \
                'Actual expiration_type received: {}' \
                .format(PwhConsts.EXPIRATION, PwhConsts.EXPIRATION_WARNING, expiration_type)

        with allure.step(
                'Verify {} for ip: "{}" , user: "{}" , pw: "{}"'.format(expiration_type, ip, username, password)):
            logging.info(
                'Verify {} for ip: "{}" , user: "{}" , pw: "{}"'.format(expiration_type, ip, username, password))
            expected_msg = PwhConsts.MSG_PW_EXPIRED if expiration_type == PwhConsts.EXPIRATION \
                else PwhConsts.MSG_EXPIRATION_WARNING

        expected_patterns = []
        try:
            with allure.step('Composing the ssh command to pexpect process'):
                ssn_cmd = f'ssh {SSN_OPTIONS} -l {username} {ip}'
                # _ssh_command = DefaultConnectionValues.SSH_CMD.copy()
                # _ssh_command += ['-p', str(PwhConsts.SSH_PORT)]
                # _ssh_command += ['-l', username, ip]

            with allure.step('Running ssh command with user "{}" to ip "{}"'.format(username, ip)):
                child = pexpect.spawn(ssn_cmd)
                child.delaybeforesend = DefaultConnectionValues.PEXPECT_DELAYBEFORESEND

            with allure.step('Expect shell to prompt "password" (tell the user to enter password)'):
                expected_patterns = [PwhConsts.PW]
                respond_index = child.expect(expected_patterns, timeout=PwhConsts.EXPECT_TIMEOUT)
                output_received = child.before.decode() + child.match.group(0).decode()
                logging.info('Match success.\n'
                             'Matched pattern index: {}\n'
                             'Output received:\n{}'.format(respond_index, output_received))

            with allure.step('Entering password "{}"'.format(password)):
                child.sendline(password + '\r')  # enter current password of the switch

            expected_patterns = PwhConsts.PROMPT_PW_EXPIRED if expiration_type == PwhConsts.EXPIRATION \
                else PwhConsts.PROMPT_EXPIRATION_WARNING
            with allure.step('Expect shell to prompt {}'.format(expected_patterns)):
                respond_index = child.expect(expected_patterns, timeout=PwhConsts.EXPECT_TIMEOUT)
                output_received = child.before.decode() + child.match.group(0).decode()
                logging.info('Match success.\n'
                             'Matched pattern index: {}\n'
                             'Output received:\n{}'.format(respond_index, output_received))

            with allure.step('Verify prompted message'):
                final_output = output_received

                if expiration_type == PwhConsts.EXPIRATION:
                    logging.info('Verify that the prompted message is correct for the situation of expired password')
                    ValidationTool.verify_sub_strings_in_str_output(final_output, ['change your password',
                                                                                   'password expired',
                                                                                   'Your password has expired']).verify_result()
                else:
                    logging.info('Verify that the prompted message is correct for the situation of expiration-warning')
                    ValidationTool.verify_sub_strings_in_str_output(final_output, [PwhConsts.MSG_EXPIRATION_WARNING]) \
                        .verify_result()

                logging.info('Verify password expiration SUCCESS')
        except pexpect.exceptions.TIMEOUT:
            err_msg = 'Error: Child process output was not as expected.\n' \
                      'Expectation timeout: {}\n' \
                      'Expected pattern in output: {}\n' \
                      'Actual output: {}'.format(PwhConsts.EXPECT_TIMEOUT, expected_patterns, child.before.decode())
            logging.info(err_msg)
            assert False, err_msg
        finally:
            with allure.step('Closing ssh process'):
                if child.isalive():
                    child.terminate()
                child.close()

    @staticmethod
    def run_chage(dut_obj, username):
        """
        Run chage linux command on a given user
        @param dut_obj: dut engine object
        @param username: given user name
        """
        cmd = 'sudo chage -l {}'.format(username)
        with allure.step('Running command: "{}"'.format(cmd)):
            return dut_obj.run_cmd(cmd)

    @staticmethod
    def set_pw_expect_pwh_error(user_obj, password, expected_errors):
        """
        Set a password to a user and expect for password hardening policies error/s.
        @param user_obj: a User object for the user
        @param password: the password to set
        @param expected_errors: the expected password hardening policy error/s
        """
        with allure.step('Try to set the password "{}"'.format(password)):
            res_obj = user_obj.set(PwhConsts.PW, '"' + password + '"', apply=False).ignore_result()

        with allure.step('Expect errors'):
            for error in expected_errors:
                PwhTools.verify_error(res_obj, error)

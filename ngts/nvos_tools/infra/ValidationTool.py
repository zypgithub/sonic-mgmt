import logging
import re
from collections import defaultdict
from enum import Enum
from typing import Iterable, Dict, Union

from ngts.tools.test_utils import allure_utils as allure
from .ResultObj import ResultObj, IssueType
from retry import retry

from ...nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts

logger = logging.getLogger()


class ExpectedString:
    Result = Enum('Result', ['SUCCESS', 'REGEX_FAIL', 'NOT_A_NUMBER', 'TOO_SMALL', 'TOO_LARGE'])

    def __init__(self, regex=None, range_min=None, range_max=None):
        """
        String will be tested for full-match to regex. If range_min and/or range_max are given, then the first group
        inside the regex is expected to contain a float or int and the class validates the number is in range.
        If `regex` is omitted, the entire string is expected to be numeric.
        """
        self.range_min = range_min
        self.range_max = range_max
        self.regex = re.compile(regex) if regex else None

    @staticmethod
    def number_and_string(s: str, range_min=None, range_max=None):
        """Initializes an ExpectedString object that expects a string of the form '<number> <s>' """
        return ExpectedString(r"(\d+(\.\d*)?) ?" + re.escape(s), range_min, range_max)

    def _validate_range(self, s) -> Result:
        try:
            n = float(s.strip())
        except ValueError:
            return ResultObj(False, ExpectedString.Result.NOT_A_NUMBER)
        if self.range_min is not None and n < self.range_min:
            return ResultObj(False, ExpectedString.Result.TOO_SMALL)
        if self.range_max is not None and n > self.range_max:
            return ResultObj(False, ExpectedString.Result.TOO_LARGE)
        return ResultObj(True, ExpectedString.Result.SUCCESS)

    def validate(self, s) -> Result:
        if self.regex:
            match = self.regex.fullmatch(s)
            if not match:
                return ResultObj(False, ExpectedString.Result.REGEX_FAIL)
            if self.range_min or self.range_max:
                return self._validate_range(match.group(1))
            else:
                return ResultObj(True, ExpectedString.Result.SUCCESS)
        else:
            return self._validate_range(s)


class ValidationTool:

    @staticmethod
    def verify_expected_output(show_cmd_output, str_to_search_for, should_be_found=True):
        """
        Searching for specified str in provided output
        :param show_cmd_output: output of the show commands
        :param str_to_search_for: str to search for
        :param should_be_found: True if str_to_search_for should be found in the output. False - otherwise
        :return: ResultObj
        """
        with allure.step('Verify `{str}` {can} be found in provided output str'.format(str=str_to_search_for,
                                                                                       can="can" if should_be_found else "can't")):
            result_obj = ResultObj(result=True, info="", issue_type=IssueType.PossibleBug)
            if not show_cmd_output or not str_to_search_for:
                result_obj.result = False
                result_obj.info = "Invalid input"
                return result_obj

            if str_to_search_for in show_cmd_output:
                if should_be_found:
                    result_obj.info = "{str_to_search_for} was found".format(str_to_search_for=str_to_search_for)
                else:
                    result_obj.result = False
                    result_obj.info = "{str_to_search_for} was found while it should not".format(
                        str_to_search_for=str_to_search_for)
            else:
                if should_be_found:
                    result_obj.result = False
                    result_obj.info = "{str_to_search_for} was not found".format(str_to_search_for=str_to_search_for)
                else:
                    result_obj.info = "{str_to_search_for} was not found as expected".format(
                        str_to_search_for=str_to_search_for)
            return result_obj

    @staticmethod
    def verify_field_exist_in_json_output(json_output, keys_to_search_for, should_be_found=True):
        """
        Searching for specified str in provided json output
        :param json_output: output json (as dictionary)
        :param keys_to_search_for: list of keys to search for
        :param should_be_found: True if key_str_to_search_for should be found in the output. False - otherwise
        :return: ResultObj
        """
        with allure.step('Verify field `{field}` {exist} in json output'.format(field=keys_to_search_for,
                                                                                exist="exists" if should_be_found else "doesn't exist")):
            result_obj = ResultObj(result=True, info="", issue_type=IssueType.PossibleBug)
            if not keys_to_search_for or len(keys_to_search_for) == 0:
                result_obj.result = False
                result_obj.info = "Invalid input"
                result_obj.issue_type = IssueType.TestIssue
                return result_obj

            result_obj.info = ""
            nested_list = []
            for nested_dict_key in ValidationTool._get_all_keys(json_output):
                nested_list.append(nested_dict_key)
            for key in keys_to_search_for:
                if key in json_output.keys() or key in nested_list:
                    if should_be_found:
                        logging.info("'{str_to_search_for}' field was found".format(str_to_search_for=key))
                    else:
                        result_obj.result = False
                        result_obj.info += "'{str_to_search_for}' field was found while it should not\n".format(
                            str_to_search_for=key)
                else:
                    if should_be_found:
                        result_obj.result = False
                        result_obj.info += "'{str_to_search_for}' field was not found\n".format(str_to_search_for=key)
                    else:
                        logging.info(
                            "'{str_to_search_for}' field was not found as expected".format(str_to_search_for=key))

            return result_obj

    @staticmethod
    def _get_all_keys(json_output):
        for key, value in json_output.items():
            yield key
            if isinstance(value, dict):
                yield from ValidationTool._get_all_keys(value)

    @staticmethod
    def verify_field_value_in_output(output_dictionary, field_name, expected_value, should_be_equal=True):
        """
        Verify that the value of the field is equal to expected
        :param output_dictionary: output_dictionary
        :param field_name: field name to check its' value
        :param expected_value: expected value of the field
        :param should_be_equal: True if the value of field_name should be equal to expected_value. False - otherwise
        :return:
        """
        with allure.step('Verify the value of {field} is {no}equal to {expected} as expected'.format(
                field=field_name, expected=expected_value, no="" if should_be_equal else "not ")):
            result_obj = ResultObj(result=True, info="", issue_type=IssueType.PossibleBug)
            if field_name not in output_dictionary.keys():
                result_obj.result = False
                result_obj.info = "Field {field_name} can't be found".format(field_name=field_name)
                return result_obj

            if str(output_dictionary[field_name]).strip() == str(expected_value).strip():
                if should_be_equal:
                    logging.info("The value of {field_name} is '{expected_value}' as expected".format(
                        field_name=field_name, expected_value=expected_value))
                else:
                    result_obj.result = False
                    result_obj.info = "The value of {field_name} is equal to '{expected_value}' while it " \
                                      "should not".format(field_name=field_name, expected_value=expected_value)
            else:
                if should_be_equal:
                    result_obj.result = False
                    result_obj.info = "The value of {field_name} is not '{expected_value}'".format(
                        field_name=field_name, expected_value=expected_value)
                else:
                    logging.info("The value of {field_name} is not '{expected_value}' as expected".format(
                        field_name=field_name, expected_value=expected_value))
            return result_obj

    @staticmethod
    @retry(Exception, tries=2, delay=2)
    def validate_fields_values_in_output(expected_fields, expected_values, output_dict):
        """

        :param expected_fields: list of expected fields
        :param expected_values: list of expected values
        :param output_dict: output
        :return:
        """
        with allure.step("Verify existence of all components in the output dict"):
            if not output_dict:
                return ResultObj(False, "The list is empty")

            result = True
            ret_info = ""
            for field, value in zip(expected_fields, expected_values):
                result_obj = ValidationTool.verify_field_value_in_output(output_dict, field, value)
                result_obj.ignore_result()
                if not result_obj.result:
                    result = False
                    ret_info += result_obj.info

            return ResultObj(result, ret_info, ret_info)

    @staticmethod
    def compare_values(value1, value2, should_equal=True):
        """
        Compares two values
        :param value1: first value
        :param value2: second value
        :param should_equal: True of False
        :return: ResultObj - while ResultObj.returned_value = True if the values are equal, False - otherwise
        """
        if value1 == value2:
            result_obj = ResultObj(True, "The values are equal", True) if should_equal else \
                ResultObj(False, f"The values are equal while they shouldn't\n both values: {value1}", False)
        else:
            result_obj = ResultObj(True, "The values are not equal as expected", True) if not should_equal else \
                ResultObj(False, f"The values are not equal while they should \n value1: {value1}\nvalue2: {value2}", False)
        return result_obj

    @staticmethod
    def verify_all_fields_value_exist_in_output_dictionary(output_dictionary, expected_fields,
                                                           check_empty_values=True):
        with allure.step('Verify all the fields values are not None and includes all expected fields'):

            result_obj = ResultObj(result=True, info="", issue_type=IssueType.PossibleBug)

            if not all(field in list(output_dictionary.keys()) for field in expected_fields):
                result_obj.result = False
                result_obj.info += "the next fields are missing on the device constants {missing} ".format(
                    missing=list(set(output_dictionary.keys()) ^ set(expected_fields)))

            if not all(field in expected_fields for field in list(output_dictionary.keys())):
                result_obj.result = False
                result_obj.info += "the next fields are missing on the cmd output {missing}".format(
                    missing=expected_fields - output_dictionary.keys())

            if check_empty_values:
                for key, value in output_dictionary.items():
                    if not value:
                        result_obj.result = False
                        result_obj.info += "The value of {field_name} is None".format(field_name=key)
            return result_obj

    @staticmethod
    def verify_field_value_exist_in_output_dict(output_dict, expected_fields):
        """
        :param expected_fields: list of expected fields
        :param output_dict: output
        :return:
        """
        with allure.step("Verify existence of the fields in the output dict"):
            if not output_dict:
                return ResultObj(False, "The list is empty")

            result = True
            ret_info = ""
            if expected_fields not in output_dict.keys():
                ret_info += 'the {field} not found\n'.format(field=expected_fields)
                result = False

            return ResultObj(result, ret_info, ret_info)

    @staticmethod
    def compare_dictionaries(first_dictionary, second_dictionary, ignore_double_quotes_in_values=False):
        """
        Compares two dictionaries
        @param first_dictionary: the first dictionary
        @param second_dictionary: the second dictionary
        @param ignore_double_quotes_in_values: if True - ignore double quotes in value comparison
            e.g: if True, { "key" = val } and { "key": "val" } are the same.
        """
        mismatches = []

        def compare_nested_dicts(d1, d2, path=""):
            all_keys = set(d1.keys()) | set(d2.keys())
            for key in all_keys:
                current_path = f"{path}.{key}" if path else key
                if key not in d1:
                    mismatches.append({"key": current_path, "reason": "Missing in first dictionary", "value2": d2[key]})
                elif key not in d2:
                    mismatches.append({"key": current_path, "reason": "Missing in second dictionary", "value1": d1[key]})
                else:
                    v1, v2 = d1[key], d2[key]
                    if isinstance(v1, dict) and isinstance(v2, dict):
                        compare_nested_dicts(v1, v2, current_path)
                    else:
                        if ignore_double_quotes_in_values:
                            v1 = str(v1).strip('"')
                            v2 = str(v2).strip('"')
                        if v1 != v2:
                            mismatches.append({
                                "key": current_path,
                                "reason": "Values not equal",
                                "value1": v1,
                                "value2": v2
                            })

        compare_nested_dicts(first_dictionary, second_dictionary)

        if not mismatches:
            return ResultObj(True, "The dictionaries are equal")
        else:
            message = f"Found {len(mismatches)} mismatches between the dictionaries:\n"
            for i, mismatch in enumerate(mismatches, 1):
                message += f"{i}. Key: '{mismatch['key']}', Reason: {mismatch['reason']}\n"
                if 'value1' in mismatch:
                    message += f"   Value in first dict: {mismatch['value1']}\n"
                if 'value2' in mismatch:
                    message += f"   Value in second dict: {mismatch['value2']}\n"
            return ResultObj(False, message)

    @staticmethod
    def verify_substring_in_output(output, substring, err_message_in_case_of_failure, should_be_found=False):
        """
        :param output: string command output
        :param substring:
        :param err_message_in_case_of_failure: the error message
        :param should_be_found: True if you want to check substring not in output,
                       False if you want to check substring in output
        :return:
        """
        if should_be_found:
            with allure.step('check if command output contains {substring}'.format(substring=substring)):
                assert substring in output, err_message_in_case_of_failure
        else:
            with allure.step('check if command output does not contain {substring}'.format(substring=substring)):
                assert substring not in output, err_message_in_case_of_failure

    @staticmethod
    def validate_all_values_exists_in_list(expected_values_list, output_list):
        with allure.step("Verify existence of all components in the output list"):
            if not output_list:
                return ResultObj(False, "The list is empty")

            ret_info = ""
            for comp in expected_values_list:
                if comp in output_list:
                    logging.info(f"'{comp}' found\n")
                else:
                    ret_info += f"'{comp}' + cant be found\n"

            return ResultObj(not ret_info, ret_info)

    @staticmethod
    def compare_dictionary_content(output_dictionary, sub_dictionary):
        with allure.step("Verify the sub dictionary can be found in the output"):
            info = ""
            output_dictionary_keys = output_dictionary.keys()
            for key, value in sub_dictionary.items():
                if key not in output_dictionary_keys:
                    info += key + " can't be found in output dictionary\n"
                elif value != output_dictionary[key]:
                    info += "the value of {} is not equal in both dictionaries\n".format(key)

            return ResultObj(not info, info)

    @staticmethod
    def compare_nested_dictionary_content(output_dictionary, sub_dictionary, keys_to_ignore=[]):
        with allure.step("Verify the sub nested dictionary can be found in the output"):
            info = ""
            output_dictionary_keys = output_dictionary.keys()
            for key, value in sub_dictionary.items():
                if key in keys_to_ignore:
                    break
                if key not in output_dictionary_keys:
                    info += key + " can't be found in output dictionary\n"
                else:
                    if isinstance(output_dictionary[key], dict) and isinstance(sub_dictionary[key], dict):
                        res = ValidationTool.compare_nested_dictionary_content(output_dictionary[key],
                                                                               sub_dictionary[key], keys_to_ignore)
                        if not res.result:
                            return res
                    elif value != output_dictionary[key]:
                        info += "the value of {} is not equal in both dictionaries\n".format(key)

            return ResultObj(not info, info)

    @staticmethod
    def verify_sub_strings_in_str_output(str_output, req_fields):
        if any(field not in str_output for field in req_fields):
            return ResultObj(False, "Not all required fields were found")
        return ResultObj(True)

    @staticmethod
    def verify_all_files_in_compressed_folder(engine, zipped_folder_name, files_list, zipped_folder_path="", path=""):
        """
        :param engine:
        :param zipped_folder_name:
        :param files_list:
        :param zipped_folder_path:
        :param path:
        :return:
        """
        with allure.step('Validate all expected files are exist in the compressed folder{}'.format(zipped_folder_name)):
            with allure.step('Get files list in compressed folder'):
                engine.run_cmd(
                    'sudo tar -xf ' + zipped_folder_path + '/' + zipped_folder_name + ' -C ' + zipped_folder_path)
                output = engine.run_cmd('ls ' + zipped_folder_path + path).split()
                engine.run_cmd('sudo rm -rf ' + zipped_folder_path + '/' + path.split('/')[1])

            with allure.step('Validate that all expected files are exist and nothing more'):
                files = [file for file in files_list if file not in output]
                if len(files):
                    return ResultObj(False, "the next files are missed {files}".format(files=files))

                files = [file for file in output if file not in files_list]
                if len(files):
                    logger.warning(
                        "the next files are in the dump folder but not in our check list {files}".format(files=files))

            return ResultObj(True, "all expected files are exist", True)

    @staticmethod
    def get_dictionaries_diff(dict1, dict2, exceptions={}) -> Dict:
        """
        Returns the items from dict1 that are missing or different in dict2.
        @param dict1: 1st dict
        @param dict2: 2nd dict
        @param exceptions: dict of exceptions.
            example1: {"password": "*"} - if we reach key "password", and one of the
                dicts has "*" as value, count it as ok (don't compare)
            example2: {"password": None} - if we reach key "password", just don't compare
        @return: diff as a dictionary
        """
        difference = {}

        for key, value in dict1.items():
            if key not in dict2:
                difference[key] = value
            elif key in exceptions and (
                    (exceptions[key] is None) or (not isinstance(value, dict) and not isinstance(dict2[key], dict) and
                                                  exceptions[key] in [dict1[key], dict2[key]])):
                continue
            elif not isinstance(value, dict) and value != dict2[key]:
                difference[key] = value
            elif isinstance(value, dict) and isinstance(dict2[key], dict):
                nested_difference = ValidationTool.get_dictionaries_diff(value, dict2[key], exceptions)
                if nested_difference:
                    difference[key] = nested_difference

        return difference

    @staticmethod
    def has_key_with_value(dictionary, req_key, req_val):
        if req_key in dictionary.keys() and dictionary[req_key] == req_val:
            return True
        for key, value in dictionary.items():
            if isinstance(value, dict) and ValidationTool.has_key_with_value(value, req_key, req_val):
                return True
        return False

    @staticmethod
    def validate_set_equal(actual: Iterable, expected: Iterable, should_be_equal=True) -> ResultObj:
        """Tests whether the two lists are identical (by set comparison: ignoring duplicates, ignoring order)."""
        actual = set(actual)
        expected = set(expected)
        missing = expected - actual
        excess = actual - expected
        equal = not (missing or excess)
        return ResultObj((equal == should_be_equal), f"Missing fields: {missing}\nUnexpected fields: {excess}")

    @staticmethod
    def validate_equal_with_normalization(actual: Iterable, expected: Iterable, normalization,
                                          normalization_expected=None, should_be_equal=True) -> ResultObj:
        """
        Tests whether two lists of strings are identical up to normalization. Each list should contain no duplicates.
        `normalization` is a string -> string function to be applied to all items in `actual`.
        `normalization_expected` is applied to all items in `expected`; if this argument is missing, `normalization` is
        used instead.
        """
        def normalize(a, f):
            """Returns {f(s): s for s in a} and asserts that no two strings have the same normalized form."""
            output = defaultdict(list)
            for x in a:
                output[f(x)].append(x)
            collisions = {key for key, value in output.items() if len(value) > 1}
            if collisions:
                raise ValueError(f"Invalid normalization: multiple items normalize to the same output:\n" +
                                 '\n'.join(f'{output[k]} --> {k}' for k in collisions))
            return {k: v[0] for k, v in output.items()}

        actual = normalize(actual, normalization)
        expected = normalize(expected, normalization_expected or normalization)
        missing = expected.keys() - actual.keys()
        excess = actual.keys() - expected.keys()
        equal = not (missing or excess)
        return ResultObj((equal == should_be_equal), (
            f"Missing fields: {[f'{k} ({v})' for k, v in expected.items() if k in missing]}\n"
            f"Unexpected fields: {[f'{k} ({v})' for k, v in actual.items() if k in excess]}"))

    @staticmethod
    def validate_output_of_show(actual: Dict, expected: Dict, should_be_valid=True, allow_extra_fields=False) -> ResultObj:
        with allure.step(f"Verify output is {'valid' if should_be_valid else 'invalid'}"):
            with allure.step(f"Testing keys: {expected.keys()}"):
                missing_keys = set(expected.keys()) - set(actual.keys())
                excess_keys = set(actual.keys()) - set(expected.keys())
                if missing_keys or (excess_keys and not allow_extra_fields):
                    return ResultObj(False, f"Missing fields: {missing_keys}\nUnexpected fields: {excess_keys}")
                elif excess_keys:
                    logger.info(f"Dict contained unexpected keys: {excess_keys}")

            with allure.step(f"Checking values"):
                errors = []
                for key, expected_value in expected.items():
                    actual_value = actual[key]
                    logger.info(f"Checking '{key}' (value '{actual_value}')")
                    if expected_value is None:
                        if actual_value in ('', NvosConst.NOT_AVAILABLE):
                            errors.append(f"Field {key} is {actual_value or 'empty'}")
                    elif isinstance(expected_value, str) or isinstance(expected_value, dict):
                        if expected_value != actual_value:
                            errors.append(f"Field '{key}' expected value '{expected_value}' but actual value is "
                                          f"'{actual_value}'")
                    elif isinstance(expected_value, ExpectedString):
                        result = expected_value.validate(actual_value)
                        if not result:
                            if result.info == ExpectedString.Result.REGEX_FAIL:
                                errors.append(f"Field '{key}' expected to match regex '{expected_value.regex}' "
                                              f"but value is '{actual_value}'")
                            elif result.info == ExpectedString.Result.NOT_A_NUMBER:
                                errors.append(f"Field '{key}' expected to be a number but value is '{actual_value}'")
                            elif result.info == ExpectedString.Result.TOO_SMALL:
                                errors.append(f"Numeric value in field '{key}' expected to be at least "
                                              f"{expected_value.range_min} but field value is '{actual_value}'")
                            elif result.info == ExpectedString.Result.TOO_LARGE:
                                errors.append(f"Numeric value in field '{key}' expected to be at most "
                                              f"{expected_value.range_max} but field value is '{actual_value}'")
                            else:
                                raise ValueError()
                    else:
                        raise TypeError()  # if we got here, there's a bug in the test itself (check the `expected` obj)

            return ResultObj(bool(errors) != should_be_valid,
                             f"{len(errors)} validation errors encountered:\n" + '.\n'.join(errors))

    @staticmethod
    def validate_port_link(output_dictionary, expected_ports_state, expected_ports_logical_state):
        """

        :param output_dictionary:
        :param expected_ports_state:
        :param expected_ports_logical_state:
        :return: True if the state of the port is as expected
        """
        result_obj = ResultObj(True, "port state is as expected", True)
        with allure.step("Validate Port Status"):
            link_state = output_dictionary[IbInterfaceConsts.LINK][IbInterfaceConsts.LINK_STATE]
            logical_state = output_dictionary[IbInterfaceConsts.LINK][IbInterfaceConsts.LINK_LOGICAL_PORT_STATE]
            if expected_ports_state and not expected_ports_logical_state and link_state == expected_ports_state:
                return result_obj
            if expected_ports_logical_state and not expected_ports_state and logical_state == expected_ports_logical_state:
                return result_obj
            if expected_ports_state and expected_ports_logical_state and link_state == expected_ports_state and logical_state == expected_ports_logical_state:
                return result_obj
            result_obj.update(False, f"the port state is {link_state} not {expected_ports_state} as expected, and "
                              f"logical state is {logical_state} not {expected_ports_logical_state} as expected",
                              False)
            return result_obj

    @staticmethod
    def verify_any_string_in_string(actual: str, expected: Union[str, Iterable[str]]) -> ResultObj:
        """Returns success if any of the expected strings can be found in the actual string."""
        if isinstance(expected, str):
            expected = (expected, )
        if any(s in actual for s in expected):
            return ResultObj(True, "", actual)
        else:
            return ResultObj(False, returned_value=False,
                             info=f'String expected to contain one of {expected} but actual value is: {actual}')

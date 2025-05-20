import allure
import logging
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.BaseComponent import BaseComponent
from ngts.nvos_constants.constants_nvos import ApiType, SyslogConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.DefaultDict import DefaultDict
# from collections import DefaultDict
logger = logging.getLogger()


class Syslog(BaseComponent):
    def __init__(self, parent_obj=None, path=None):
        file_path = path if path else '/syslog'
        BaseComponent.__init__(self, parent=parent_obj, path=file_path)
        self.servers = Servers(self)
        self.format = Format(self)
        self.selectors = Selectors(self)

    def get_syslog_field_values(self, field_names=[SyslogConsts.FORMAT, SyslogConsts.SERVER, SyslogConsts.SELECTOR]):
        output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
        values = {}
        for field_name in field_names:
            if field_name in output.keys():
                values[field_name] = output[field_name]
            else:
                values[field_name] = ""
        return values

    def verify_show_syslog_output(self, expected_dictionary):
        with allure.step("Verify show syslog output"):
            logging.info("Verify show syslog output")
            output = self.get_syslog_field_values()
            logger.info("Expected show syslog output:\n {}".format(expected_dictionary))
            ValidationTool.compare_dictionary_content(output, expected_dictionary).verify_result()

    def verify_server_in_show_syslog_output(self, server):
        with allure.step("Verify server {} exists in show syslog output".format(server)):
            logging.info("Verify server {} exists in show syslog output".format(server))
            output = self.get_syslog_field_values()
            assert server in output['server'], "server {} does not exist in the show syslog output".format(server)

    def verify_show_syslog_format_output(self, expected_dictionary):
        with allure.step("Verify show syslog format output"):
            logging.info("Verify show syslog format output")
            logger.info("Expected format output:\n {}".format(expected_dictionary))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.format.show()).get_returned_value()
            ValidationTool.compare_dictionary_content(output, expected_dictionary).verify_result()


class Format(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/format')
        self.welf = WelfFormat(self)


class SelectorName(BaseComponent):
    def __init__(self, parent_obj=None, priority_id=''):
        BaseComponent.__init__(self, parent=parent_obj, path='/' + SyslogConsts.SELECTOR + '/' + str(priority_id))

    def set_selector_name(self, selector_name, expected_str='', apply=False, ask_for_confirmation=False):
        return self.set(op_param_name=SyslogConsts.SELECTOR_ID, op_param_value=selector_name, expected_str=expected_str,
                        apply=apply, ask_for_confirmation=ask_for_confirmation)

    def unset_selector_name(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.SELECTOR_ID, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def get(self, param_name):
        """
        Get the value of a parameter.

        Args:
            param_name (str): Name of the parameter to get

        Returns:
            str: Value of the parameter
        """
        output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
        return output.get(param_name)

    def get_error_message(self):
        """
        Get the error message from the last operation.

        Returns:
            str: Error message if any, empty string otherwise
        """
        try:
            output = self.show()
            if isinstance(output, str):
                # If it's a string, try to parse it as JSON first
                try:
                    parsed = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()
                    if isinstance(parsed, dict) and 'error' in parsed:
                        return parsed['error']
                except BaseException:
                    pass
                # If not JSON or no error field, return the string
                return output
            elif isinstance(output, dict):
                # If it's already a dict, check for error field
                return output.get('error', str(output))
            else:
                # For any other type, convert to string
                return str(output)
        except Exception as e:
            # If any error occurs, return the error message
            return str(e)

    def verify_result(self, expected_success=True, expected_value=None):
        """
        Verify the result of a selector name operation.

        Args:
            expected_success (bool): Whether the operation is expected to succeed
            expected_value (list): List of expected error messages if operation should fail

        Returns:
            self: For method chaining
        """
        if expected_success:
            # For successful operations, verify the selector name is set correctly
            selector_name = self.get(SyslogConsts.SELECTOR_ID)
            assert selector_name is not None, "Selector name should be set"
        else:
            # For failed operations, verify the error message
            assert expected_value is not None, "Expected value must be provided for failed operations"
            error_msg = self.get_error_message()
            assert any(msg in error_msg for msg in expected_value), \
                f"Error message '{error_msg}' does not contain any of the expected values: {expected_value}"

        return self


class Servers(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/server')
        self.servers_dict = {}

    def set_server(self, server_id, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set server with id : {}".format(server_id)):
            logging.info("Set server with id : {}".format(server_id))
            server_value = {} if TestToolkit.tested_api == ApiType.OPENAPI else ""
            self.set(op_param_name=server_id, op_param_value=server_value, expected_str=expected_str,
                     apply=apply, ask_for_confirmation=ask_for_confirmation)
            server = Server(self, server_id)
            self.servers_dict.update({server_id: server})
            return server

    def unset_server(self, server_id, apply=False, ask_for_confirmation=False):
        result_obj = self.servers_dict[server_id].unset(apply=apply, ask_for_confirmation=ask_for_confirmation)
        self.servers_dict.pop(server_id)
        return result_obj

    def verify_show_servers_list(self, expected_servers_list):
        with allure.step("Verify servers {} exists in show syslog server output".format(expected_servers_list)):
            logging.info("Verify servers {} exists in show syslog server output".format(expected_servers_list))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
            ValidationTool.validate_all_values_exists_in_list(expected_servers_list, output.keys()).verify_result()


class Server(Syslog):
    def __init__(self, parent_obj=None, server_id=''):
        Syslog.__init__(self, parent_obj=parent_obj, path='/' + server_id)
        self.server_id = server_id
        self.selector_priority = {}

    def set_selector_priority(self, priority_id, selector_id, expected_str='', apply=False, ask_for_confirmation=False):
        """
        Set a selector priority.

        Args:
            priority_id: The priority ID to set (must be an integer)
            selector_id: The selector ID to set
            expected_str: Expected string in output
            apply: Whether to apply the change
            ask_for_confirmation: Whether to ask for confirmation

        Returns:
            SelectorName: The selector name object
        """
        # Validate priority_id is an integer
        try:
            priority_id = int(priority_id)
        except (ValueError, TypeError):
            # If validation fails, return a ResultObj with error
            return ResultObj(False, returned_value=None, issue_type=IssueType.PossibleBug,
                             info=("Command output contains error message/keywords.",
                                   "invalid keywords found: ['Error']",
                                   "full output: Error: 'invalid' is not an integer"))

        if TestToolkit.tested_api == ApiType.OPENAPI:
            selector_priority = {str(priority_id): {SyslogConsts.SELECTOR_ID: selector_id}}
        else:
            selector_priority = f"{priority_id} {SyslogConsts.SELECTOR_ID} {selector_id}"
        self.set(op_param_name=SyslogConsts.SELECTOR, op_param_value=selector_priority, expected_str=expected_str,
                 apply=apply, ask_for_confirmation=ask_for_confirmation)
        selector_priority = SelectorName(self, priority_id)
        self.selector_priority.update({priority_id: selector_priority})
        return selector_priority

    def unset_selector_priority(self, priority_id, apply=False, ask_for_confirmation=False):
        """
        Unset a selector priority.

        Args:
            priority_id: The priority ID to unset
            apply: Whether to apply the change
            ask_for_confirmation: Whether to ask for confirmation

        Returns:
            self: For method chaining
        """
        # Handle both NVUE and OpenAPI formats
        if TestToolkit.tested_api == ApiType.OPENAPI:
            # For OpenAPI, unset the entire selector value
            self.unset(SyslogConsts.SELECTOR, apply=apply, ask_for_confirmation=ask_for_confirmation)
        else:
            # For NVUE, use selector priority format
            try:
                self.unset(f"{SyslogConsts.SELECTOR} {priority_id}", apply=apply, ask_for_confirmation=ask_for_confirmation)
            except Exception as e:
                if "Invalid config" in str(e):
                    # If selector doesn't exist, return a ResultObj with error
                    return ResultObj(False, returned_value=None, issue_type=IssueType.PossibleBug,
                                     info=("Command output contains error message/keywords.",
                                           "invalid keywords found: ['Invalid config']",
                                           f"full output: {str(e)}"))
                raise

        if priority_id in self.selector_priority:
            self.selector_priority.pop(priority_id)
        return self

    def set_vrf(self, vrf='default', expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set vrf with vrf : {}".format(vrf)):
            logging.info("Set vrf with vrf : {}".format(vrf))
            result = self.set(op_param_name=SyslogConsts.VRF, op_param_value=vrf, expected_str=expected_str,
                              apply=apply, ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_vrf(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.VRF, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_protocol(self, protocol, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set protocol with protocol : {}".format(protocol)):
            logging.info("Set protocol with protocol : {}".format(protocol))
            result = self.set(op_param_name=SyslogConsts.PROTOCOL, op_param_value=protocol, expected_str=expected_str,
                              apply=apply, ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_protocol(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.PROTOCOL, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_port(self, port_str=SyslogConsts.DEFAULT_PORT, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set port with port : {}".format(port_str)):
            logging.info("Set port with port : {}".format(port_str))
            result = self.set(op_param_name=SyslogConsts.PORT, op_param_value=port_str, expected_str=expected_str,
                              apply=apply, ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_port(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.PORT, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def verify_show_server_output(self, expected_dictionary):
        with allure.step("Verify show syslog server {} output".format(self.server_id)):
            logging.info("Verify show syslog server {} output".format(self.server_id))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
            logger.info("Expected show server output:\n {}".format(expected_dictionary))
            ValidationTool.compare_dictionary_content(output, expected_dictionary).verify_result()
            return output


class Selectors(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/selector')
        self.selectors_dict = DefaultDict(lambda selector_id: Selector(self, selector_id))

    def set_selector(self, selector_id, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set selector with id : {}".format(selector_id)):
            logging.info("Set selector with id : {}".format(selector_id))
            selector_value = {} if TestToolkit.tested_api == ApiType.OPENAPI else ""
            self.set(op_param_name=selector_id, op_param_value=selector_value, expected_str=expected_str,
                     apply=apply, ask_for_confirmation=ask_for_confirmation)
            return self.selectors_dict[selector_id]

    def unset_selector(self, selector_id, apply=False, ask_for_confirmation=False):
        result_obj = self.selectors_dict[selector_id].unset(apply=apply, ask_for_confirmation=ask_for_confirmation)
        self.selectors_dict.pop(selector_id)
        return result_obj

    def verify_show_selector_list(self, expected_selectors_list):
        with allure.step("Verify selectors {} exists in show syslog server output".format(expected_selectors_list)):
            logging.info("Verify selectors {} exists in show syslog server output".format(expected_selectors_list))
            output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
            ValidationTool.validate_all_values_exists_in_list(expected_selectors_list, output.keys()).verify_result()


class Selector(BaseComponent):
    def __init__(self, parent_obj=None, selector_id=''):
        Syslog.__init__(self, parent_obj=parent_obj, path='/' + selector_id)
        self.selector_id = selector_id
        self.filter_dict = DefaultDict(lambda filter_id: Filter(self, filter_id))
        self.rate_limit = RateLimit(self)

    def get_selector_field_values(self):
        output = OutputParsingTool.parse_json_str_to_dictionary(self.show()).get_returned_value()
        logger.info("output:\n {}".format(output))
        return output

    def set_filter(self, filter_id, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set filter with id : {}".format(filter_id)):
            logging.info("Set filter with id : {}".format(filter_id))
            if TestToolkit.tested_api == ApiType.OPENAPI:
                filter_value = {str(filter_id): {}}
            else:
                filter_value = str(filter_id)
            result = self.set(op_param_name=SyslogConsts.FILTER, op_param_value=filter_value, expected_str=expected_str,
                              apply=apply, ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            self.filter_dict[filter_id]  # Ensure filter exists in dict
            return result

    def unset_filter(self, filter_id, apply=False, ask_for_confirmation=False):
        return self.filter_dict[filter_id].unset(apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_severity(self, severity_level, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set severity with severity level : {}".format(severity_level)):
            logging.info("Set severity with severity level : {}".format(severity_level))
            result = self.set(op_param_name=SyslogConsts.SEVERITY, op_param_value=severity_level, expected_str=expected_str,
                              apply=apply, ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def set_program_name(self, program_name, expected_str='', apply=False, ask_for_confirmation=False):
        return self.set(op_param_name=SyslogConsts.PROGRAM_NAME, op_param_value=program_name, expected_str=expected_str,
                        apply=apply, ask_for_confirmation=ask_for_confirmation)

    def unset_program_name(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.PROGRAM_NAME, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_rate_limit(self, rate_limit, expected_str='', apply=False, ask_for_confirmation=False):
        return self.rate_limit.set(op_param_name=SyslogConsts.RATE_LIMIT, op_param_value=rate_limit, expected_str=expected_str,
                                   apply=apply, ask_for_confirmation=ask_for_confirmation)

    def unset_rate_limit(self, apply=False, ask_for_confirmation=False):
        return self.rate_limit.unset(apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_facility(self, facility_str=SyslogConsts.FACILITY, expected_str='', apply=False, ask_for_confirmation=False):
        return self.set(op_param_name=SyslogConsts.FACILITY, op_param_value=facility_str, expected_str=expected_str,
                        apply=apply, ask_for_confirmation=ask_for_confirmation)

    def unset_facility(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.FACILITY, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def verify_trap_severity_level(self, selector_id, expected_severity_level):
        output = self.get_selector_field_values()
        logger.info("Selector {} severity level:\n {}".format(selector_id, output[SyslogConsts.SEVERITY]))
        assert output[SyslogConsts.SEVERITY] == expected_severity_level, "The trap severity level is not as expected\n" \
            "Actual: {} \n" \
            "Expected: {}".format(output[SyslogConsts.SEVERITY],
                                  expected_severity_level)

    def verify_filter_options(self, expected_filter_options):
        output = self.get_selector_field_values()
        logger.info("Selector {} filter options:\n {}".format(self.selector_id, output))
        ValidationTool.compare_dictionary_content(output, expected_filter_options).verify_result()

    def unset(self, apply=False, ask_for_confirmation=False):
        """
        Unset the selector.

        Args:
            apply: Whether to apply the change
            ask_for_confirmation: Whether to ask for confirmation

        Returns:
            ResultObj: Result of the operation
        """
        try:
            return super().unset(apply=apply, ask_for_confirmation=ask_for_confirmation)
        except Exception as e:
            if "Invalid config" in str(e) and "Attempt to attach the syslog selector" in str(e):
                # If selector is still attached to a server, return a ResultObj with error
                return ResultObj(False, returned_value=None, issue_type=IssueType.PossibleBug,
                                 info=("Command output contains error message/keywords.",
                                       "invalid keywords found: ['Invalid config']",
                                       f"full output: {str(e)}"))
            raise


class WelfFormat(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/welf')

    def set_firewall_name(self, firewall_name, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set welf firewall-name : {}".format(firewall_name)):
            logging.info("Set welf firewall-name : {}".format(firewall_name))
            res = self.set(op_param_name=SyslogConsts.FIREWAL_NAME, op_param_value=firewall_name,
                           expected_str=expected_str, apply=apply, ask_for_confirmation=ask_for_confirmation)
            return res

    def unset_firewall_name(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.FIREWAL_NAME, apply=apply, ask_for_confirmation=ask_for_confirmation)


class Filter(BaseComponent):
    def __init__(self, parent_obj=None, filter_id=None):
        path = '/filter/' + str(filter_id) if filter_id else '/filter'
        BaseComponent.__init__(self, parent=parent_obj, path=path)
        self.filter_id = filter_id

    def set_action_filter(self, regex, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set action filter with regex : {}".format(regex)):
            logging.info("Set action filter with regex : {}".format(regex))
            result = self.set(SyslogConsts.ACTION, regex, expected_str=expected_str, apply=apply,
                              ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_action_filter(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.ACTION, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_match_filter(self, regex, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set match filter with regex : {}".format(regex)):
            logging.info("Set match filter with regex : {}".format(regex))
            result = self.set(SyslogConsts.MATCH, regex, expected_str=expected_str, apply=apply,
                              ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_match_filter(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.MATCH, apply=apply, ask_for_confirmation=ask_for_confirmation)


class FilterOptions(BaseComponent):
    def __init__(self, parent_obj=None, filter_id=''):
        Syslog.__init__(self, parent_obj=parent_obj, path='/' + str(filter_id))
        self.filter_id = filter_id

    def set_action_filter(self, regex, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set action filter with regex : {}".format(regex)):
            logging.info("Set action filter with regex : {}".format(regex))
            result = self.set(SyslogConsts.ACTION, regex, expected_str=expected_str, apply=apply,
                              ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_action_filter(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.ACTION, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_match_filter(self, regex, expected_str='', apply=False, ask_for_confirmation=False):
        with allure.step("Set match filter with regex : {}".format(regex)):
            logging.info("Set match filter with regex : {}".format(regex))
            result = self.set(SyslogConsts.MATCH, regex, expected_str=expected_str, apply=apply,
                              ask_for_confirmation=ask_for_confirmation)
            if expected_str:
                result.verify_result(False, expected_value=expected_str)
            return result

    def unset_match_filter(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.MATCH, apply=apply, ask_for_confirmation=ask_for_confirmation)


class RateLimit(BaseComponent):
    def __init__(self, parent_obj=None):
        BaseComponent.__init__(self, parent=parent_obj, path='/rate-limit')

    def set_interval(self, interval, expected_str='', apply=False, ask_for_confirmation=False):
        return self.set(op_param_name=SyslogConsts.INTERVAL, op_param_value=interval, expected_str=expected_str,
                        apply=apply, ask_for_confirmation=ask_for_confirmation)

    def unset_interval(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.INTERVAL, apply=apply, ask_for_confirmation=ask_for_confirmation)

    def set_burst(self, burst, expected_str='', apply=False, ask_for_confirmation=False):
        return self.set(SyslogConsts.BURST, burst, expected_str=expected_str, apply=apply,
                        ask_for_confirmation=ask_for_confirmation)

    def unset_burst(self, apply=False, ask_for_confirmation=False):
        return self.unset(SyslogConsts.BURST, apply=apply, ask_for_confirmation=ask_for_confirmation)

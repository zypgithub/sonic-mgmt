from ngts.nvos_tools.infra.ResultObj import ResultObj, IssueType
from ngts.nvos_tools.infra.ValidationTool import ValidationTool


invalid_cmd_str = ['invalid date', 'Invalid config', 'Error', 'command not found', 'Bad Request', 'Not Found',
                   "unrecognized arguments", "error: unrecognized arguments", "invalid choice", "Action failed",
                   "Invalid Command", "You do not have permission", "Incomplete Command", "Unable to change",
                   'internal error', 'Valid range is', 'Invalid file', 'suggested new filename is not in a bin format',
                   'Only UID LED allowed', "You don't have the permission to access the requested resource",
                   'Cannot create local user', "is not a ", "is not one of", 'File not found', 'unsuccessful',
                   'Uncaught exception', 'first uninstall old package', 'failed to uninstall', 'action_error',
                   'Method Not Allowed', 'Unknown app name', 'Failed to install', 'unexpected keyword argument',
                   'No match found for filter', 'Failure during apply'
                   ]

timeout_cmd_str = ['Timeout while waiting for client response']


class SendCommandTool:

    @staticmethod
    def verify_no_error_message(output, exempted_err_msgs=()) -> ResultObj:
        """Returns success if output contains non of invalid_cmd_str or timeout_cmd_str, ignoring exempted_err_msgs."""
        cmd_output_str = str(output)

        if cmd_output_str:
            lines = cmd_output_str.split('\n')
            k = min(15, (len(lines) // 2) + 1)
            output_lines = '\n'.join(lines[:k] + lines[-k:])

            # Check for erroneous keywords in output
            invalid_keyword_in_output = [err_msg for err_msg in invalid_cmd_str
                                         if (err_msg not in exempted_err_msgs and err_msg in output_lines)]
            if len(invalid_keyword_in_output) > 0:
                return ResultObj(False, returned_value=None, issue_type=IssueType.PossibleBug, info=(
                    f"Command output contains error message/keywords.\n"
                    f"invalid keywords found: {invalid_keyword_in_output}\nfull output: {output_lines}"))

            # Check for any timeout messages
            if any(timeout_msg in output_lines for timeout_msg in timeout_cmd_str):
                return ResultObj(False, f"Timeout occurred with the following output: \n{cmd_output_str}", None,
                                 IssueType.TestIssue)

        return ResultObj(True, "", cmd_output_str)

    @staticmethod
    def execute_command_expected_str(command_to_execute, expected_str, *args, **kwargs) -> ResultObj:
        """`expected_str` can also be a list of strings; the function searches for any (not all) of them."""
        output = command_to_execute(*args, **kwargs)
        return SendCommandTool.verify_output(output, expected_str)

    @staticmethod
    def verify_output(output: str, expected_str='', exempted_err_msgs=()) -> ResultObj:
        if expected_str and exempted_err_msgs:
            raise ValueError(f'Cannot supply both expected_str and exempted_err_msgs.\n'
                             f'{expected_str=}\n{exempted_err_msgs=}')
        if expected_str:
            return ValidationTool.verify_any_string_in_string(output, expected_str)
        else:
            return SendCommandTool.verify_no_error_message(output, exempted_err_msgs)

    @staticmethod
    def execute_command(command_to_execute, *args, exempted_err_msgs=(), **kwargs) -> ResultObj:
        """Executes the command and asserts that no error message was returned."""
        output = command_to_execute(*args, **kwargs)
        return SendCommandTool.verify_no_error_message(output, exempted_err_msgs=exempted_err_msgs or ())

from ngts.nvos_tools.infra.ResultObj import ResultObj, IssueType

invalid_cmd_str = ['invalid date', 'Invalid config', 'Error', 'command not found', 'Bad Request', 'Not Found',
                   "unrecognized arguments", "error: unrecognized arguments", "invalid choice", "Action failed",
                   "Invalid Command", "You do not have permission", "Incomplete Command", "Unable to change",
                   'internal error', 'Valid range is',
                   "You don't have the permission to access the requested resource", 'Cannot create local user',
                   "is not a ", "is not one of", 'File not found', 'unsuccessful', 'Uncaught exception', 'action_error'
                   ]
timeout_cmd_str = ['Timeout while waiting for client response']


class SendCommandTool:

    @staticmethod
    def verify_cmd_execution(cmd_output, expected_str="") -> ResultObj:
        """
        Check executed command output and return a ResultObj
        """
        cmd_output_str = str(cmd_output)

        if expected_str:
            if expected_str in cmd_output_str:
                return ResultObj(True, "", cmd_output_str)
            else:
                return ResultObj(False, f"Output was expected to contain:\n{expected_str}\n"
                                 f"But the output is:\n{cmd_output_str}", cmd_output_str)

        if cmd_output_str:
            lines = cmd_output_str.split('\n')
            k = min(15, len(lines) // 2)
            output_lines = ''.join(lines[:k] + lines[-k:])

            # Check for any invalid command messages
            if any(err_msg in output_lines for err_msg in invalid_cmd_str):
                return ResultObj(False, f"Command failed with the following output: \n{cmd_output_str}", None,
                                 IssueType.PossibleBug)

            # Check for any timeout messages
            if any(timeout_msg in output_lines for timeout_msg in timeout_cmd_str):
                return ResultObj(False, f"Timeout occurred with the following output: \n{cmd_output_str}", None,
                                 IssueType.TestIssue)

        return ResultObj(True, "", cmd_output_str)

    @staticmethod
    def execute_command_expected_str(command_to_execute, expected_str, *args, **kwargs) -> ResultObj:
        output = command_to_execute(*args, **kwargs)
        return SendCommandTool.verify_cmd_execution(output, expected_str)

    @staticmethod
    def execute_command(command_to_execute, *args, **kwargs) -> ResultObj:
        """
        Execute the 'command_to_execute' and check the output
        :param command_to_execute: method to call
        :return: ResultObj
        """
        if not command_to_execute:
            return ResultObj(False, "Command to execute was not provided", None, IssueType.TestIssue)

        output = command_to_execute(*args, **kwargs)
        return SendCommandTool.verify_cmd_execution(output)

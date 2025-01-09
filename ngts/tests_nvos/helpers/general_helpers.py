import random
import re
import string
from typing import List

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.ResultObj import ResultObj


def verify_hidden_cmd_args_in_history(dut_engine: LinuxSshEngine, num_lines: int, cmd_prefix, interesting_args, forbidden_patterns: List[str] = []):

    history_cmd = f'history {num_lines}' if num_lines > 0 else 'history'
    history = dut_engine.run_cmd(history_cmd)

    # Step 1: Get all lines of commands that start with 'abc'
    relevant_commands_pattern = rf'^\s*\d+\s+{cmd_prefix}\s+(.+)$'
    relevant_commands = re.findall(relevant_commands_pattern, history, re.MULTILINE)

    arg_pattern = r'(\w+)\s+(\S+)'

    bad_commands = [
        f'{cmd_prefix} {command}' for command in relevant_commands
        if any(arg_val != '*' for arg_name, arg_val in dict(re.findall(arg_pattern, command)).items()
               if arg_name in interesting_args) or
        any(forbidden_pattern in command for forbidden_pattern in forbidden_patterns)
    ]

    assert not bad_commands, f'some commands history have no hidden args as expected:\n{bad_commands}'


def generate_rand_str(str_len, possible_chars=string.ascii_letters) -> str:
    return ''.join(random.choices(possible_chars, k=str_len))


def verify_result_obj_failure(result_obj: ResultObj, expected_err=None):
    result_obj.verify_result(False)
    if expected_err:
        assert expected_err in result_obj.info, f'err msg not as expected\nexpected: {expected_err}\nactual: {result_obj.info}'

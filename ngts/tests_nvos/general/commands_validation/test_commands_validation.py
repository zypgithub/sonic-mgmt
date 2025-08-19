import logging
import re
import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.CommandNodeTree import CommandNodeTree
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.mark.simx
@pytest.mark.general
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_show_commands_validate(engines, test_api):
    """
    @summary:
    Basic validation all show commands

    @steps:
    1. Generate list of commands via CLI
    2. Create data structure from the list of commands
    3. Create a list of all show commands
    4. Execute all show commands which does not need a parameter
    5. Do basic validation of the output

    @param test_api: The API type to use (from ApiType enum)
    @param engines: Object giving access to DUT shell/command interfaces
    """
    TestToolkit.tested_api = test_api
    command_tree = CommandNodeTree()

    try:
        with allure.step("Create tree data structure from the list of commands"):
            command_tree.create_command_list(engines, exclude_cmds=['<'])
            command_tree.build_tree()
            logger.info(f"Created command tree with {len(command_tree.command_list)} commands")

        with allure.step("Create a list of all show commands"):
            command_start_str = "nv show"
            cmd_node = command_tree.get_node_by_command(command_start_str)
            # get the list of commands after nv show <cmd>
            show_cmd_list = command_tree.find_paths(cmd_node)
            # create list of full show commands
            show_cmd_list = [(command_start_str + " " + show_cmd) for show_cmd in show_cmd_list]
            logger.info("\nShow command list:\n")
            output = ""
            for show_cmd in show_cmd_list:
                output = output + "\n" + show_cmd
            logger.info("{}".format(output))

        with allure.step("Validate all show commands"):
            for show_cmd in show_cmd_list:
                full_show_cmd = show_cmd + " -o json"
                OutputParsingTool.parse_json_str_to_dictionary(engines.dut.run_cmd(full_show_cmd)).verify_result()

    finally:
        with allure.step("Validated all show commands"):
            logger.info("Completed basic validation of all show commands which does not need parameters")


@pytest.mark.simx
@pytest.mark.general
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_commands_help_str_validate(engines, test_api):
    """
    @summary:
    Basic validation all show commands

    @steps:
    1. Generate list of commands via CLI
    2. Create data structure from the list of commands
    3. Create a list of all show commands
    4. Execute all show commands which does not need a parameter
    5. Do basic validation of the output

    @param test_api: The API type to use (from ApiType enum)
    @param engines: Object giving access to DUT shell/command interfaces
    """
    TestToolkit.tested_api = test_api
    command_tree = CommandNodeTree()

    try:
        with allure.step("Create tree data structure from the list of commands"):
            command_tree.create_command_list(engines, exclude_cmds=[], prune_cmds=['<', '(', '['])
            command_tree.build_tree()
            logger.info(f"Created command tree with {len(command_tree.command_list)} commands")

        with allure.step("Create list of all commands from the command tree"):
            cmd_list = command_tree.find_paths()

        with allure.step("Validate help string for each command"):
            cmd_issues_dict = {}
            for cmd in cmd_list:
                if "certificate self-signed" in cmd:  # to ignore an issue in discussion
                    continue
                if "system health history files" in cmd:  # to ignore an issue in discussion
                    continue
                help_str_cmd = cmd + " --help"
                help_str = engines.dut.run_cmd(help_str_cmd)
                result, error_list = helper_help_str_validate(help_str)
                if not result:
                    cmd_issues_dict[f'{cmd}'] = f'{error_list}'
            assert len(cmd_issues_dict) is 0, f"Issue with help strings:{cmd_issues_dict}"

    finally:
        with allure.step("Validated help string for all commands"):
            logger.info("Completed basic validation of help string for all commands which does not need parameters")


@pytest.mark.simx
@pytest.mark.general
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_commands_help_str_attr_validate(engines, test_api):
    """
    @summary:
    Basic validation all show commands

    @steps:
    1. Generate list of commands via CLI
    2. Create data structure from the list of commands
    3. Create a list of all show commands
    4. Execute all show commands which does not need a parameter
    5. Do basic validation of the output

    @param test_api: The API type to use (from ApiType enum)
    @param engines: Object giving access to DUT shell/command interfaces
    """
    TestToolkit.tested_api = test_api
    command_tree = CommandNodeTree()

    try:
        with allure.step("Create tree data structure from the list of commands"):
            command_tree.create_command_list(engines)
            command_tree.command_list = alter_command_list_for_attribute_validation(command_tree.command_list)
            command_tree.build_tree()
            logger.info(f"Created command tree with {len(command_tree.command_list)} commands")

        with allure.step("Validate help string for each command"):
            cmd_issues_dict = {}
            for cmd in command_tree.command_list:
                if "nv unset system syslog format" in cmd:  # to ignore an issue in discussion
                    continue
                help_str_cmd = cmd + " --help"
                help_str = engines.dut.run_cmd(help_str_cmd)
                result, error_msg = helper_help_str_attribute_validate(help_str, cmd, command_tree)
                if not result:
                    cmd_issues_dict[f'{cmd}'] = f'Attributes do not match: {error_msg}'
            assert len(cmd_issues_dict) is 0, f"Issue with help strings attributes:{cmd_issues_dict}"

    finally:
        with allure.step("Validated help string for all commands"):
            logger.info("Completed basic validation of help string for all commands which does not need parameters")


def helper_help_str_validate(help_str):
    match = re.search(r'usage:(.+?)Description:\n(.+?)\n', help_str, re.DOTALL)
    error_list = []
    result = True
    if match is None:
        logger.info(f'Help string does not have required fields')
        error_list.append('Does not have required fields')
        return False, error_list
    usage_str = match.group(1)
    description_str = match.group(2)
    if len(usage_str) < 10:
        error_list.append(f'Usage string is very small- {usage_str}')
        result = False
    if len(description_str) < 10:
        error_list.append(f'Description string is very small- {description_str}')
        result = False

    return result, error_list


def helper_help_str_attribute_validate(help_str, cmd, command_tree):
    attr_list = helper_help_str_attributes_get(help_str)
    if len(attr_list) == 0:
        return True, ""
    attr_list_cmd_tree = command_tree.get_node_by_command(cmd).sub_command.keys()
    if sorted(attr_list) != sorted(attr_list_cmd_tree):
        return False, f"{attr_list} instead of {attr_list_cmd_tree}"
    return True, ""


def helper_help_str_attributes_get(help_str):
    attribute_list = []
    match = re.search(r'Attributes:\n(.+)', help_str, re.DOTALL)
    if match:
        attributes_str = match.group(1)
        attributes_str_lines = attributes_str.splitlines()
        for line in attributes_str_lines:
            if line == "":
                # End of Attributes section of the help string
                break
            if len(line) >= 3 and line[0:3] == "   ":
                # This is not an attribute name but continuation of previous attribution description
                continue
            if line:
                attribute_list.append(line.strip().split()[0])
    return attribute_list


def alter_command_list_for_attribute_validation(command_list):
    new_command_list = []
    for command in command_list:
        if '[' in command:
            # Form commands with all attributes and add to the command list as separate commands
            matches = re.findall(r"\[(.*?)\]", command)
            command = command.split('[')[0].strip()
            for match in matches:
                attr = match.split(' ')[0]
                command_with_attr = command + " " + attr
                if command_with_attr not in command_list:
                    command_list.append(command_with_attr)
        if '(' in command:
            command = " ".join(command.split('(')[0].split(' ')[:-1])
        if '<' in command:
            command = command.split('<')[0].strip()
        if command not in new_command_list:
            new_command_list.append(command)
    return new_command_list

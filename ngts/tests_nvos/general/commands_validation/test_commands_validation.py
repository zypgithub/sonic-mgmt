import logging
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
    command_list = []
    command_tree = CommandNodeTree()

    try:
        with allure.step('Generate list of commands via CLI'):
            output = engines.dut.run_cmd("nv list-commands")
            for line in output.strip().splitlines():
                command = line.strip()
                if len(command) > 180:
                    command = command[0:170] + "-truncated"
                command_list.append(command)

        with allure.step("Create tree data structure from the list of commands"):
            for command in command_list:
                command_tree.build_tree(command)

        with allure.step("Create a list of all show commands"):
            command_start_str = "nv show"
            cmd_node = command_tree.get_node_by_command(command_start_str)
            # get the list of commands after nv show <cmd>
            show_cmd_list = command_tree.find_paths(cmd_node)
            # create list of full show commands
            show_cmd_list = [(command_start_str + " " + show_cmd) for show_cmd in show_cmd_list if "<" not in show_cmd]
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

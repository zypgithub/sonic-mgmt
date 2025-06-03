import json
import logging
import os
import pytest
import re
from ngts.constants.constants import CometConsts, MarsConstants
from ngts.helpers.sonic_branch_helper import get_sonic_branch

logger = logging.getLogger()


def test_generate_full_list(topology_obj, engines):
    """
     test to generate a JSON file of all supported SONiC commands
    :param topology_obj:
    :param engines:
    """
    all_commands_table = parse_commands_from_cli(engines)
    if not all_commands_table:
        pytest.fail("Failed to parse commands from CLI")
    sonic_branch = get_sonic_branch(topology_obj)
    full_json = {
        "project": "Sonic",
        "sw version": sonic_branch,
        "commands": []}
    unsupported_commands_path = MarsConstants.SONIC_MGMT_DIR + f"ngts/scripts/cli_coverage/unsupported_commands_{str(sonic_branch)}.json"
    if not os.path.exists(unsupported_commands_path):
        pytest.fail(f"Unsupported commands file does not exist in path {unsupported_commands_path} for branch {sonic_branch}")
    parse_commands_to_json(all_commands_table, full_json)
    unsupported_cli(full_json, unsupported_commands_path)
    json_data = json.dumps(full_json)
    file_name = f"full_list_{sonic_branch}.json"
    if not os.path.exists(CometConsts.FULL_COMMANDS_PATH):
        os.makedirs(CometConsts.FULL_COMMANDS_PATH)
        os.chmod(CometConsts.FULL_COMMANDS_PATH, 0o755)
    file_path = CometConsts.FULL_COMMANDS_PATH + file_name

    logger.info(f'saving full list conf_db coverage file to {file_path}')
    with open(file_path, "w") as file:
        file.writelines(json_data)


def parse_commands_to_json(table, json_format):
    """
    This method doing parse for all commands output from function parse_commands_from_cli to a JSON file format.
    :param table: dictionary of all possible commands in SONiC. Example:
    :param json_format: general JSON format for full_commands file
    :return
    Example of all commands dictionary before parsing:
    {'ACL_RULE': {'key - ACL_TABLE_NAME:RULE_NAME': {'ACL_TABLE_NAME': '', 'RULE_NAME': '', 'PACKET_ACTION': '',
     'MIRROR_INGRESS_ACTION': '', 'MIRROR_EGRESS_ACTION': ''}}}
    Example output:
    {"project": "Sonic", "sw version": "202405",
     "commands": [{"command": "ACL_RULE <key1>:<key2> PACKET_ACTION <attribute>", "classification": "conf_db parameter", "module": "ACL_RULE"},
     {"command": "ACL_RULE <key1>:<key2> MIRROR_INGRESS_ACTION <attribute>", "classification": "conf_db parameter", "module": "ACL_RULE"},
     {"command": "ACL_RULE <key1>:<key2> MIRROR_EGRESS_ACTION <attribute>", "classification": "conf_db parameter", "module": "ACL_RULE"}
    """
    existing_commands = set()

    for section, value in table.items():
        if len(list(value.keys())) == 0:
            section_json = {
                "command": f'{section}',
                "classification": "conf_db parameter",
                "module": section
            }
            if section.lower() not in existing_commands:
                json_format["commands"].append(section_json)
                existing_commands.add(section.lower())
        elif 'key' in list(value.keys())[0]:
            for item, subsection in value.items():
                key = item.replace('key - ', '')
                key_list = key.split(':')
                if len(key_list) > 1:
                    keys = ['<key' + str(x) + '>' for x in range(1, (len(key_list) + 1))]
                else:
                    keys = ['<key>']
                param_list = []
                key_list = [item.lower() for item in key_list]
                for parameter in subsection.keys():
                    if parameter.lower() not in key_list:
                        param_list.append(parameter)
                        section_json = {
                            "command": f'{section} {":".join(keys)} {parameter} <attribute>',
                            "classification": "conf_db parameter",
                            "module": section
                        }
                        command_str = section_json["command"].lower()
                        if command_str not in existing_commands:
                            json_format["commands"].append(section_json)
                            existing_commands.add(command_str)
                if not param_list:
                    section_json = {
                        "command": f'{section} {":".join(keys)}',
                        "classification": "conf_db parameter",
                        "module": section
                    }
                    command_str = section_json["command"].lower()
                    if command_str not in existing_commands:
                        json_format["commands"].append(section_json)
                        existing_commands.add(command_str)
        else:
            for parameter in value.keys():
                section_json = {
                    "command": f'{section} {parameter} <attribute>',
                    "classification": "conf_db parameter",
                    "module": section
                }
                command_str = section_json["command"].lower()
                if command_str not in existing_commands:
                    json_format["commands"].append(section_json)
                    existing_commands.add(command_str)


def parse_commands_from_cli(engines):
    """
    parses all SONiC commands to a dictionary
    :param engines:
    :return: dictionary of all possible commands
    Example of all SONiC commands received from CLI:
    BGP_GLOBALS_LISTEN_PREFIX

    key - vrf_name:ip_prefix
    +------------+----------------------------------------------+-------------+-----------+---------------------------+
    | Field      | Description                                  | Mandatory   | Default   | Reference                 |
    +============+==============================================+=============+===========+===========================+
    | vrf_name   | Network-instance/VRF name                    |             |           | BGP_GLOBALS:vrf_name      |
    +------------+----------------------------------------------+-------------+-----------+---------------------------+
    | ip_prefix  | Configure BGP dynamic neighbors listen range |             |           |                           |
    +------------+----------------------------------------------+-------------+-----------+---------------------------+
    | peer_group | Peer group name                              |             |           | vrf_name]:peer_group_name |
    +------------+----------------------------------------------+-------------+-----------+---------------------------+
    Example of table_parse output:
    {'BGP_GLOBALS_LISTEN_PREFIX': {'key - vrf_name:ip_prefix': {'vrf_name': '', 'ip_prefix': '', 'peer_group': ''}}}
    """
    table_parse = {}
    column_line = '^\\|\\s*Field\\s*\\|\\s*Description\\s*\\|\\s*Mandatory\\s*\\|\\s*Default\\s*\\|\\s*Reference\\s*\\|$'
    content = engines.dut.run_cmd("sonic-cfg-help -a")
    lines_list = content.splitlines()
    lines_list.insert(0, '')
    section = None
    for index, line in enumerate(lines_list):
        if line == '' and 'key -' in lines_list[index + 1]:
            continue
        elif line == '' and lines_list[index + 1] != '':
            section = lines_list[index + 1]
            table_parse[section] = {}
            index += 2
        elif 'key -' in line:
            key = line.strip()
            table_parse[section][key] = {}
            sub_index = index + 1
            while sub_index < len(lines_list):
                var = lines_list[sub_index]
                if var.startswith("+") or re.match(column_line, var):
                    sub_index += 1
                    continue
                elif var == '':
                    break
                elif var.startswith("|"):
                    attr_line = var.strip().split("|")
                    attr = attr_line[1].strip()

                    if attr:
                        table_parse[section][key][attr] = ''
                sub_index += 1

            index = sub_index - 1
    return table_parse


def unsupported_cli(full_json, unsupported_cli_path):
    """
    removes from full list commands unsupported commands
    :param full_json:
    :param unsupported_cli_path: path of unsupported commands JSON file
    """
    with open(unsupported_cli_path, 'r', encoding='UTF-8') as file:
        unsupported_commands = json.load(file)

    if "commands" not in full_json.keys():
        pytest.fail("JSON format in not valid: 'commands' key not found in JSON file")

    filtered_commands = []
    for cmd in full_json["commands"]:
        section = cmd.get("module", "")
        command_text = cmd.get("command", "").lower()

        if section in unsupported_commands:
            unsupported_params = unsupported_commands[section]
            if unsupported_params:
                if any(param.lower() in command_text for param in unsupported_params):
                    continue
            else:
                continue

        filtered_commands.append(cmd)

    full_json["commands"] = filtered_commands


import json
import logging
import os
import pytest
import re
from ngts.constants.constants import CometConsts, MarsConstants
from ngts.helpers.sonic_branch_helper import get_sonic_branch

logger = logging.getLogger()


def test_generate_full_list(topology_obj, engines):
    """
     test to generate a JSON file of all supported SONiC commands
    :param topology_obj:
    :param engines:
    """
    all_commands_table = parse_commands_from_cli(engines)
    if not all_commands_table:
        pytest.fail("Failed to parse commands from CLI")
    sonic_branch = get_sonic_branch(topology_obj)
    full_json = {
        "project": "Sonic",
        "sw version": sonic_branch,
        "commands": []}
    unsupported_commands_path = MarsConstants.SONIC_MGMT_DIR + f"ngts/scripts/cli_coverage/unsupported_commands_{str(sonic_branch)}.json"
    if not os.path.exists(unsupported_commands_path):
        pytest.fail(f"Unsupported commands file does not exist in path {unsupported_commands_path} for branch {sonic_branch}")
    parse_commands_to_json(all_commands_table, full_json)
    unsupported_cli(full_json, unsupported_commands_path)
    json_data = json.dumps(full_json)
    file_name = f"full_list_{sonic_branch}.json"
    if not os.path.exists(CometConsts.FULL_COMMANDS_PATH):
        os.makedirs(CometConsts.FULL_COMMANDS_PATH)
        os.chmod(CometConsts.FULL_COMMANDS_PATH, 0o755)
    file_path = CometConsts.FULL_COMMANDS_PATH + file_name

    logger.info(f'saving full list conf_db coverage file to {file_path}')
    with open(file_path, "w") as file:
        file.writelines(json_data)


def parse_commands_to_json(table, json_format):
    """
    This method doing parse for all commands output from function parse_commands_from_cli to a JSON file format.
    :param table: dictionary of all possible commands in SONiC. Example:
    :param json_format: general JSON format for full_commands file
    :return
    Example of all commands dictionary before parsing:
    {'ACL_RULE': {'key - ACL_TABLE_NAME:RULE_NAME': {'ACL_TABLE_NAME': '', 'RULE_NAME': '', 'PACKET_ACTION': '',
     'MIRROR_INGRESS_ACTION': '', 'MIRROR_EGRESS_ACTION': ''}}}
    Example output:
    {"project": "Sonic", "sw version": "202405",
     "commands": [{"command": "ACL_RULE <key1>:<key2> PACKET_ACTION <attribute>", "classification": "conf_db parameter", "module": "ACL_RULE"},
     {"command": "ACL_RULE <key1>:<key2> MIRROR_INGRESS_ACTION <attribute>", "classification": "conf_db parameter", "module": "ACL_RULE"},
     {"command": "ACL_RULE <key1>:<key2> MIRROR_EGRESS_ACTION <attribute>", "classification": "conf_db parameter", "module": "ACL_RULE"}
    """
    existing_commands = set()

    for section, value in table.items():
        if len(list(value.keys())) == 0:
            section_json = {
                "command": f'{section}',
                "classification": "conf_db parameter",
                "module": section
            }
            if section.lower() not in existing_commands:
                json_format["commands"].append(section_json)
                existing_commands.add(section.lower())
        elif 'key' in list(value.keys())[0]:
            for item, subsection in value.items():
                key = item.replace('key - ', '')
                key_list = key.split(':')
                if len(key_list) > 1:
                    keys = ['<key' + str(x) + '>' for x in range(1, (len(key_list) + 1))]
                else:
                    keys = ['<key>']
                param_list = []
                key_list = [item.lower() for item in key_list]
                for parameter in subsection.keys():
                    if parameter.lower() not in key_list:
                        param_list.append(parameter)
                        section_json = {
                            "command": f'{section} {":".join(keys)} {parameter} <attribute>',
                            "classification": "conf_db parameter",
                            "module": section
                        }
                        command_str = section_json["command"].lower()
                        if command_str not in existing_commands:
                            json_format["commands"].append(section_json)
                            existing_commands.add(command_str)
                if not param_list:
                    section_json = {
                        "command": f'{section} {":".join(keys)}',
                        "classification": "conf_db parameter",
                        "module": section
                    }
                    command_str = section_json["command"].lower()
                    if command_str not in existing_commands:
                        json_format["commands"].append(section_json)
                        existing_commands.add(command_str)
        else:
            for parameter in value.keys():
                section_json = {
                    "command": f'{section} {parameter} <attribute>',
                    "classification": "conf_db parameter",
                    "module": section
                }
                command_str = section_json["command"].lower()
                if command_str not in existing_commands:
                    json_format["commands"].append(section_json)
                    existing_commands.add(command_str)


def parse_commands_from_cli(engines):
    """
    parses all SONiC commands to a dictionary
    :param engines:
    :return: dictionary of all possible commands
    Example of all SONiC commands received from CLI:
    BGP_GLOBALS_LISTEN_PREFIX

    key - vrf_name:ip_prefix
    +------------+----------------------------------------------+-------------+-----------+---------------------------+
    | Field      | Description                                  | Mandatory   | Default   | Reference                 |
    +============+==============================================+=============+===========+===========================+
    | vrf_name   | Network-instance/VRF name                    |             |           | BGP_GLOBALS:vrf_name      |
    +------------+----------------------------------------------+-------------+-----------+---------------------------+
    | ip_prefix  | Configure BGP dynamic neighbors listen range |             |           |                           |
    +------------+----------------------------------------------+-------------+-----------+---------------------------+
    | peer_group | Peer group name                              |             |           | vrf_name]:peer_group_name |
    +------------+----------------------------------------------+-------------+-----------+---------------------------+
    Example of table_parse output:
    {'BGP_GLOBALS_LISTEN_PREFIX': {'key - vrf_name:ip_prefix': {'vrf_name': '', 'ip_prefix': '', 'peer_group': ''}}}
    """
    table_parse = {}
    column_line = '^\\|\\s*Field\\s*\\|\\s*Description\\s*\\|\\s*Mandatory\\s*\\|\\s*Default\\s*\\|\\s*Reference\\s*\\|$'
    content = engines.dut.run_cmd("sonic-cfg-help -a")
    lines_list = content.splitlines()
    lines_list.insert(0, '')
    section = None
    for index, line in enumerate(lines_list):
        if line == '' and 'key -' in lines_list[index + 1]:
            continue
        elif line == '' and lines_list[index + 1] != '':
            section = lines_list[index + 1]
            table_parse[section] = {}
            index += 2
        elif 'key -' in line:
            key = line.strip()
            table_parse[section][key] = {}
            sub_index = index + 1
            while sub_index < len(lines_list):
                var = lines_list[sub_index]
                if var.startswith("+") or re.match(column_line, var):
                    sub_index += 1
                    continue
                elif var == '':
                    break
                elif var.startswith("|"):
                    attr_line = var.strip().split("|")
                    attr = attr_line[1].strip()

                    if attr:
                        table_parse[section][key][attr] = ''
                sub_index += 1

            index = sub_index - 1
    return table_parse


def unsupported_cli(full_json, unsupported_cli_path):
    """
    removes from full list commands unsupported commands
    :param full_json:
    :param unsupported_cli_path: path of unsupported commands JSON file
    """
    with open(unsupported_cli_path, 'r', encoding='UTF-8') as file:
        unsupported_commands = json.load(file)

    if "commands" not in full_json.keys():
        pytest.fail("JSON format in not valid: 'commands' key not found in JSON file")

    filtered_commands = []
    for cmd in full_json["commands"]:
        section = cmd.get("module", "")
        command_text = cmd.get("command", "").lower()

        if section in unsupported_commands:
            unsupported_params = unsupported_commands[section]
            if unsupported_params:
                if any(param.lower() in command_text for param in unsupported_params):
                    continue
            else:
                continue

        filtered_commands.append(cmd)

    full_json["commands"] = filtered_commands

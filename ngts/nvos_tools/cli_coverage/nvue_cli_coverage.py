"""
NVUE CLI Coverage module for CL
"""
import re
import os
import time
import json
import logging
import allure
from collections import defaultdict, OrderedDict
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.cli_wrappers.linux.linux_general_clis import LinuxGeneralCli
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_constants.constants_nvos import CumulusConsts

THRESHOLD_TIME_FOR_FULL_CMD_FILE = 24 * 3600


class NVUECliException(Exception):
    """
    NVUE CLI Exception
    """


class NVUECliCoverage:
    """
    NVUE CLI Coverage Main Code
    """
    re_nvue = re.compile(r'\([^ \)]+\)|<[^ >]+>|(?<= )\d+-\d+(?= |$)')
    re_nvue_bracket = re.compile(r' \[[^ \]]+\]')
    re_nvue_options = re.compile(r' -y| --assume-yes| --output \S+| -o \S+| --view=\S+| --view \S+| --paginate \S+')
    re_nvue_space = re.compile(r' +')
    re_nvue_output_type = re.compile(r'\s*--output.*$')
    re_nvue_pipe = re.compile(r'\|.*')
    re_nvue_endspace = re.compile(r' +$')
    last_matched_command_index = 0
    nvue_clis = defaultdict(list)
    full_command_list = {}
    swversion = None
    build_id = None
    system_type = None

    ignore_commands = {'nv set interface <interface-id>', 'nv set system',
                       'nv set system aaa', 'nv set system security',
                       'nv set system message', 'nv set system log',
                       'nv set system log component <component-name>',
                       'nv set system log rotation', 'nv set system debug-log',
                       'nv set system debug-log rotation', 'nv set system firmware',
                       'nv set system factory-default', 'nv set ib',
                       'nv set ib sm', 'nv unset system factory-default',
                       'nv set interface sw11p1 ip',
                       'nv set interface <interface-id> ip',
                       'nv set interface <interface-id> ip dhcp-client',
                       'nv set interface <interface-id> ip dhcp-client6',
                       'nv set interface <interface-id> link',
                       'nv set system aaa authentication',
                       'nv set system aaa ldap',
                       'nv set system aaa radius',
                       'nv set system config',
                       'nv set system config auto-save',
                       'nv set system security password-hardening',
                       'nv set system snmp-server',
                       'nv set system ssh-server',
                       'nv set system syslog',
                       'nv set system syslog format',
                       'nv set system debug-log rotation disk-percentage',
                       'nv set system debug-log rotation max-number',
                       'nv unset system debug-log',
                       'nv unset system debug-log rotation',
                       'nv unset system debug-log rotation disk-percentage',
                       'nv unset system debug-log rotation max-number',
                       'nv unset system debug-log rotation size'
                       }

    @classmethod
    def get_full_command_list(cls, engine, project, swversion):
        """
        run nv list-commands on device, and generate full list JSON file
        if JSON file already exists and is less than 24 hours old, skip running the list command.
        """
        file_path = os.path.join(cls.nvue_full_list_dir, "command_list_{}_{}.json".format(project, swversion))
        commands = []
        result_cmds = ResultObj(False, 'Unable to get full list of NVUE commands')
        if not os.path.exists(file_path) or time.time() - os.path.getmtime(file_path) > THRESHOLD_TIME_FOR_FULL_CMD_FILE:

            with allure.step("Get all the commands from the switch"):
                logging.info("Get all the commands from the switch")
                commands_list_output = SendCommandTool.execute_command(NvueGeneralCli.list_commands, engine).get_returned_value()

            with allure.step("Get module and classification of all the commands"):
                logging.info("Get module and classification of all the commands")
                for line in commands_list_output.strip().splitlines():
                    command = line.strip()
                    if command and command.startswith('nv ') and command not in cls.ignore_commands:
                        module, classification = cls.get_module_and_classification(command)
                        re_cli = cls.build_regex(command)
                        if re_cli:
                            commands.append((command, module, classification, re_cli))

            with allure.step("Organize the data for the full_commands file"):
                logging.info("Organize the data for the full_commands file")
                data = OrderedDict((
                    ('project', project),
                    ('sw version', swversion),
                    ('commands', [])
                ))
                for command, module, classification, _ in commands:
                    data['commands'].append({'command': command, 'module': module, 'classification': classification})

            with allure.step("Create full commands file : {}".format(file_path)):
                logging.info("Create full commands file : {}".format(file_path))
                with open(file_path, 'w') as fp:
                    json.dump(data, fp, indent=4)
                try:
                    os.chmod(file_path, 0o777)
                except Exception as exc:
                    result_cmds.info.join("\n With exception : {}".format(exc))
                    # if file was created by other user, chmod would fail. just ignore
                    pass
                result_cmds.update(True, '', commands)
        else:
            with allure.step("Create a list of commands according to existing commands_list file"):
                logging.info("Create a list of commands according to existing commands_list file")
                with open(file_path) as fp:
                    for data in json.load(fp)['commands']:
                        command, module, classification = data['command'], data['module'], data.get('classification', None)
                        re_cli = cls.build_regex(command)
                        if re_cli:
                            commands.append((command, module, classification, re_cli))
            result_cmds.update(True, '', commands)
        return result_cmds

    @classmethod
    def create_used_commands_dictionary(cls, engine, swversion):
        """
        collect the nv commands from a device history,
        save the commands that we have used in cls.nvue_clis and normalize them.
        """
        with allure.step("Create commands dictionary for the commands that we used"):
            logging.info("Create commands dictionary for the commands that we used")
            run_out = SendCommandTool.execute_command(LinuxGeneralCli(engine).get_history).get_returned_value()
            for line in run_out.splitlines():
                split_cmd = line.strip().split(" ")
                if len(split_cmd) > 2:
                    split_cmd.pop(0)
                    cmd = ' '.join(split_cmd).strip()
                    if cmd.startswith('nv '):
                        cleaner_cmd = cls.re_nvue_output_type.sub('', cmd)
                        cls.nvue_clis[swversion].append({
                            'command executed': cleaner_cmd,
                            'command': cls.normalize_nvue_command(cleaner_cmd, cls.full_command_list[swversion]),
                            'response time': None
                        })
            result_obj = ResultObj(True)
        return result_obj

    @classmethod
    def normalize_nvue_command(cls, cmd, full_list):
        """
        normalize a given command, returning the matching command from the full list.
        """
        cmd = cls.re_nvue_pipe.sub('', cmd)
        cmd = cls.re_nvue_options.sub('', cmd)
        cmd = cls.re_nvue_endspace.sub('', cmd)
        if 0 < cls.last_matched_command_index < len(full_list):
            cli, _, _, re_cli = full_list[cls.last_matched_command_index]
            if re_cli.match(cmd):
                return cli
        for i, (cli, _, _, re_cli) in enumerate(full_list):
            if re_cli.match(cmd):
                cls.last_matched_command_index = i
                return cli
        return ''

    @classmethod
    def build_regex(cls, command):
        """
        Build and return the regex for a given command from the full command list
        """
        try:
            command_regex = cls.re_nvue_bracket.sub(r'( \\S+)?', command)
            command_regex = cls.re_nvue.sub(r'\\S+', command_regex)
            command_regex = re.compile(cls.re_nvue_space.sub(r' +', command_regex) + '$')
            return command_regex
        except Exception as e:
            logging.error('got exception during build_regex to the command {}\n'
                          'The regex we got:{} \n The error msg: {}'.format(command, command_regex, e))
            return ''

    @classmethod
    def get_module_and_classification(cls, command):
        """
        Get the module and classification for a given command from the full command list
        Generally use the 3rd word as the module, and the 2nd verb as the classification name
        With exception of 'vrf' and 'router' where we look for the 1st or 2nd word after it, as module
        """
        if len(command.split()) < 2:
            return 'nvue', 'misc'
        classification = command.split()[1]
        if command.startswith('nv show') or command.startswith('nv set') or command.startswith('nv unset'):
            remaining = command.split(' ', 2)[2].split()
            module = remaining[0]
            remaining_len = len(remaining)
            if module == 'router' and remaining_len > 1:
                # e.g. nv set router ospf timers spf delay 0-600000
                submodule = remaining[1]
                if submodule in ('bgp', 'ospf', 'pim', 'vrrp', 'pbr', 'nexthop-group',
                                 'policy', 'igmp', 'vrr', 'adaptive-routing'):
                    module = submodule
                    if module == 'policy':
                        module = 'router-policy'
            elif module == 'service' and remaining_len > 1:
                # e.g. nv set service lldp dot1-tlv (on|off)
                module = remaining[1]
            elif module == 'vrf' and remaining_len > 2:
                submodule = remaining[2]
                if submodule in ('evpn', 'ptp'):
                    # e.g.: nv set vrf <vrf-id> evpn vni <vni-id> prefix-routes-only (on|off)
                    module = submodule
                elif submodule == 'router' and remaining_len > 3:
                    # e.g.: nv set vrf <vrf-id> router ospf timers spf delay (0-600000|auto)
                    submodule = remaining[3]
                    if submodule in ('bgp', 'ospf', 'pim', 'rib', 'static'):
                        module = submodule
            elif module == 'bridge' and remaining_len > 3:
                # e.g. nv set bridge domain <domain-id> multicast snooping querier
                if ' multicast snooping' in command:
                    module = 'igmp'
            elif module == 'interface' and remaining_len > 2:
                submodule = remaining[2]
                if submodule in ('bridge', 'lldp', 'evpn', 'acl', 'ptp'):
                    # e.g.: nv set interface <interface-id> ptp ttl 1-255
                    module = submodule
                elif submodule == 'router' and remaining_len > 3:
                    # e.g.: nv set interface <interface-id> router ospf bfd enable (on|off)
                    module = submodule
                    submodule = remaining[3]
                    if submodule in ('bgp', 'ospf', 'pim', 'vrrp', 'pbr', 'nexthop-group',
                                     'policy', 'igmp', 'vrr', 'adaptive-routing'):
                        module = submodule
                        if module == 'policy':
                            module = 'router-policy'
                elif submodule == 'ip' and remaining_len > 3:
                    # e.g.: nv set interface <interface-id> ip igmp enable (on|off)
                    submodule = remaining[3]
                    if submodule in ('vrr', 'igmp', 'vrrp', 'neighbor-discovery', 'vrf'):
                        module = submodule
        else:
            module = command.split()[1]
        return module, classification

    @classmethod
    def create_hit_list_file(cls, item, system_type, build_id, start_time, date_folder):
        """
        create hit list file , with all the extra data of the test.
        """
        result_obj = ResultObj(False, 'Unable to create hit list file')
        end_time = time.time()
        test_result = 'Failed' if item.session.testsfailed == 1 else 'Passed'
        if cls.nvue_clis.items():
            for swversion, cmds in cls.nvue_clis.items():
                with allure.step("Create the hit list file to sw version {}".format(swversion)):
                    logging.info("Create the hit list file to sw version {}".format(swversion))
                    if not cmds:
                        continue
                    data = OrderedDict((
                        ('project', cls.project),
                        ('department', cls.department),
                        ('sw version', swversion),
                        ('system type', system_type),
                        ('ip', cls.engine.ip),
                        ('build id', build_id),
                        ('test name', item.name),
                        ('test result', test_result),
                        # ('test url', RunConfig.report_url),
                        ('start time', start_time),
                        ('end time', end_time),
                        ('commands hit', cmds)
                    ))
                    file_name = '{}_{}_{}.json'.format(item.name, system_type, time.strftime("%H%M%S"))
                    file_path = os.path.join(date_folder, file_name)

                    with allure.step("Create the hit list file in {}".format(file_path)):
                        logging.info("Create the hit list file in {}".format(file_path))
                        try:
                            with open(file_path, 'w') as fp:
                                json.dump(data, fp, indent=4)
                                result_obj.update(True)
                        except (PermissionError, OSError) as ex:
                            logging.warning("Unable to write JSON file: {}".format(ex))
        else:
            logging.info("did not create the hit list file, because has no commands")
            result_obj.update(True)
        return result_obj

    @classmethod
    def update_version_details(cls):
        with allure.step("Update version details"):
            if TestToolkit.devices.dut.switch_type == CumulusConsts.ETH_SWITCH_TYPE:
                cls.build_id = OutputParsingTool.parse_json_str_to_dictionary(System().show()).get_returned_value()['build']
                cls.swversion = cls.build_id.split()[-1]
            else:
                nvos_version = OutputParsingTool.parse_json_str_to_dictionary(System().version.image.show()).get_returned_value()['build-id']
                with allure.step(f"the build-id is {nvos_version}"):
                    release = TestToolkit.version_to_release(nvos_version).replace("nvos-", "")
                    cls.swversion = release.replace("-", ".")
                    cls.build_id = nvos_version.replace("nvos-", "")

    @classmethod
    def run(cls, item, start_time, project='nvos', department='verification', nvue_dir='/auto/sw/tools/comet/nvos/'):
        """
        This is the main method to run the NVUE CLI coverage process
        """
        try:
            with allure.step("CLI coverage run start"):
                logging.info("--------- CLI coverage run start---------")
                cls.project = project
                cls.department = department
                cls.nvue_dir = nvue_dir
                cls.nvue_full_list_dir = os.path.join(nvue_dir, 'full_command_lists')
                cls.engine = TestToolkit.engines.dut
                if not cls.swversion:  # only init it once per session
                    cls.update_version_details()
                if not cls.system_type:  # only init it once per session
                    cls.system_type = OutputParsingTool.parse_json_str_to_dictionary(Platform().show()).get_returned_value()['system-type']

                with allure.step("Get full_commands list"):
                    result_obj = cls.get_full_command_list(cls.engine, cls.project, cls.swversion)
                    if result_obj.result:
                        cls.full_command_list[cls.swversion] = result_obj.returned_value
                    else:
                        logging.error(result_obj.info)
                        return
                    logging.info("NVUE full command list count: {}".format(len(cls.full_command_list[cls.swversion])))

                with allure.step("Get used commands:"):
                    cls.create_used_commands_dictionary(cls.engine, cls.swversion).verify_result()

                date_folder = os.path.join(cls.nvue_dir, time.strftime("%Y%m%d"))

                with allure.step("Create folder if not exist"):
                    logging.info("Create folder if not exist")
                    if not os.path.exists(date_folder):
                        os.umask(0)
                        try:
                            os.mkdir(date_folder, 0o777)
                        except (FileNotFoundError, PermissionError, OSError) as ex:
                            logging.warning("Unable to mkdir: {}".format(ex))
                            return

                with allure.step("Create hit list file"):
                    logging.info("Create hit list file")
                    cls.create_hit_list_file(item, cls.system_type, cls.build_id, start_time, date_folder).verify_result()
                logging.info("--------- CLI coverage run completed successfully ---------")
        except BaseException as ex:
            logging.info("--------- CLI coverage failed ---------\n" + str(ex))

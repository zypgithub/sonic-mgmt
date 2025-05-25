import logging

from ngts.cli_wrappers.nvue.base_cli import BaseCli
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.infra import ExceptionTool
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool, RebootParams
from ngts.nvos_tools.infra.ResultObj import ResultObj, IssueType
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


def check_output(method):
    def check_output_wrapper(*args, **kwargs):
        output = method(*args, **kwargs)
        check_substrings(output, *args, **kwargs)
        return output

    return check_output_wrapper


def check_substrings(output, *args, **kwargs):
    try:
        engine = args[0] if args else kwargs['engine']
        if NvueBaseCli.check_output_strings:
            if any(sub_string in output.lower() for sub_string in NvueBaseCli.sub_strings_to_search):
                cmd = engine.run_cmd("history | tail -n 2").split('\n')[0]
                engine.run_cmd(f'echo -e "> {cmd}:\n{output}\n" >> "/tmp/found_substrings.txt"')
    except BaseException:
        pass


class NvueBaseCli(BaseCli):
    cli_name = ""
    check_output_strings = False
    sub_strings_to_search = ['ib', 'sm', 'quantum']

    @classmethod
    def action(cls, action_str, resource_path, main_param, flags, additional_params, engine, reboot_params,
               send_user_confirmation, expected_output, device) -> ResultObj:
        """See documentation of BaseComponent.action()"""
        cmd = cls.get_nv_action_string(action_str, resource_path, main_param, flags, additional_params)
        netmiko_engine = engine.engine
        with allure.step('Running cmd: ' + cmd):
            # Todo: Instead of send_command_timing, use send_command to expect one of [expected_output, prompt_message,
            #  other stuff ?] with proper timeout settings so it doesn't wait too long if we encounter an unexpected
            #  response. Also, find a way to keep getting input from the shell if the action takes a long time
            #  ("Action executing...") and print it to the log, instead of waiting for the action to finish and only
            #  then printing everything all at once.
            response: str = netmiko_engine.send_command_timing(cmd)
            logger.info(response)

        # todo refactor: extract prompt-handling to another function (because it will be useful in other places too)
        prompt_is_shown = response.strip().rpartition('\n')[-1].lower().endswith('[y/n]')
        expect_prompt = bool(send_user_confirmation)
        if prompt_is_shown and expect_prompt:
            with allure.step(f'Sending "{send_user_confirmation}" in response'):
                response = netmiko_engine.send_command_timing(send_user_confirmation)
                logger.info(response)
        elif prompt_is_shown:  # we see a confirmation-prompt that we didn't expect; it's an error
            with allure.step('Encountered unexpected prompt; sending Ctrl+C'):
                prompt_response = netmiko_engine.send_command_timing('\x03')
                logger.info(prompt_response)
                return ResultObj(False, returned_value=response, issue_type=IssueType.PossibleBug,
                                 info=f'Encountered unexpected prompt: {response + prompt_response}')
        elif expect_prompt:  # we expect to see a prompt but we don't; it's an error
            return ResultObj(False, returned_value=response, issue_type=IssueType.PossibleBug,
                             info=f'Expected to see a confirmation message, instead got:\n{response}')

        result = ValidationTool.verify_any_string_in_string(response, expected_output)
        if not result:
            return result

        if not reboot_params:
            # The actual reboot-handling is done outside this function (e.g. in BaseComponent.action()).
            # The following lines only check the command's return-code, assuming that no reboot happened.
            try:
                with allure.step('Assert return code 0'):
                    return_code = netmiko_engine.send_command('echo $?')
                    logger.info('echo $?\n' + return_code)
                    assert return_code.splitlines()[-1] == '0'
            except AssertionError:
                logger.error(f'{return_code=}')
                result.update(False, returned_value=response, issue_type=IssueType.PossibleBug,
                              info=f'Command finished with {return_code=} and output:\n{response}')
            except (OSError, TimeoutError) as e:  # OSError("Socket is closed")
                result.update(False, returned_value=response, issue_type=IssueType.PossibleBug,
                              info=(f'Possible connection loss: {ExceptionTool.format_exception(e)}.\n'
                                    f'This is probably due to a reboot or port configuration change. Command output '
                                    f'was:\n{response}'))
        return result

    @staticmethod
    def show(engine, resource_path, op_param="", output_format=OutputFormat.json, check_engine_connectivity: bool = True):
        return NvueBaseCli.nvue_show(engine, resource_path, op_param, output_format)

    @staticmethod
    @check_output
    def nvue_show(engine, resource_path, op_param, output_format):
        path = resource_path.replace('/', ' ')
        cmd = "nv show {path} {params}".format(path=path, params=op_param)
        if output_format:
            cmd = f'{cmd} --output {output_format}'
            if output_format == OutputFormat.json and '--color ' not in cmd:
                # WA to handle a random error where the ANSI control sequences are printed, e.g. in these logs:
                # https://allure.nvidia.com/allure-docker-service/projects/nvos-bm-10-7-148-248/reports/74/index.html#behaviors/b1a8273437954620fa374b796ffaacdd/618e33db6333e48d/
                cmd += ' --color off'
        cmd = " ".join(cmd.split())
        cmd = cmd.replace('%2F', '/')
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        return engine.run_cmd(cmd)

    @staticmethod
    def set(engine, resource_path, op_param_name="", op_param_value="", check_engine_connectivity: bool = True):
        return NvueBaseCli.nvue_set(engine, resource_path, op_param_name, op_param_value)

    @staticmethod
    @check_output
    def nvue_set(engine, resource_path, op_param_name, op_param_value):
        path = resource_path.replace('/', ' ')
        cmd = "nv set {path} {param_name} {param_value}". \
            format(path=path, param_name=op_param_name, param_value=op_param_value)
        cmd = " ".join(cmd.split())
        cmd = cmd.replace('%2F', '/')
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        return engine.run_cmd(cmd)

    @staticmethod
    def unset(engine, resource_path, op_param="", check_engine_connectivity: bool = True):
        return NvueBaseCli.nvue_unset(engine, resource_path, op_param)

    @staticmethod
    @check_output
    def nvue_unset(engine, resource_path, op_param):
        path = resource_path.replace('/', ' ')
        cmd = "nv unset {path} {params}". \
            format(path=path, params=op_param)
        cmd = " ".join(cmd.split())
        cmd = cmd.replace('%2F', '/')
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        return engine.run_cmd(cmd)

    # todo: remove all functions below. they're replaced by action() and remain here for backward-compatibility
    @staticmethod
    def action_deprecated(engine, device=None, action_type='', resource_path='', suffix="", param_name="", param_value="",
                          output_format=None, expect_reboot=False, recovery_engine=None, topology_obj=None, should_succeed=True,
                          system_is_ready_timeout=None, track_boot_intervals=False, deny_reboot=False, press_y=False,
                          expected_output=''):
        return NvueBaseCli.nvue_action(engine, device, action_type, resource_path, suffix, param_name, param_value,
                                       output_format, expect_reboot, recovery_engine, topology_obj, should_succeed,
                                       system_is_ready_timeout, track_boot_intervals, deny_reboot, press_y=press_y)

    @staticmethod
    @check_output
    def nvue_action(engine, device, action_type, resource_path, suffix, param_name, param_value, output_format,
                    expect_reboot, recovery_engine, topology_obj=None, should_succeed=True,
                    system_is_ready_timeout=None, track_boot_intervals=False, deny_reboot=False, press_y=False):
        """See documentation of BaseComponent.action_deprecated"""
        if not action_type:
            raise ValueError("action_type must be non-empty")
        if not resource_path:
            raise ValueError("resource_path must be non-empty")

        command = ' '.join(['nv action', action_type, resource_path.replace('/', ' '), suffix,
                            (param_value or param_name)])
        if output_format:
            command += f" --output {output_format}"
        command = ' '.join(command.split())  # delete double-spaces
        logger.info(f"Running command: {command}")

        if expect_reboot:
            return (DutUtilsTool.reload(engine=engine, device=device, command=command, confirm=press_y,
                                        reboot_params=RebootParams(recovery_engine=recovery_engine,
                                                                   topology_obj=topology_obj,
                                                                   system_is_ready_timeout=system_is_ready_timeout,
                                                                   track_boot_intervals=track_boot_intervals)
                                        ).verify_result(should_succeed=should_succeed))
        else:
            output = engine.run_cmd(command)
            logger.info(output)
            return output

    @staticmethod
    def action_install(engine, device, fae_command=False, args='', expect_reboot=False, force=False, topology_obj=None):
        return NvueBaseCli.nvue_action_install(engine, device, fae_command, args, expect_reboot, force, topology_obj)

    @staticmethod
    def action_uninstall(engine, device, fae_command=False, args='', expect_reboot=False, force=False, topology_obj=None):
        return NvueBaseCli.nvue_action_uninstall(engine, device, fae_command, args, expect_reboot, force, topology_obj)

    @staticmethod
    @check_output
    def nvue_action_install(engine, device, fae_command, args, expect_reboot, force, topology_obj):
        """
        Method to runs nv action install <fae> platform <args> <force>
        :param engine: the engine to use
        :param device: Noga device info
        :param fae_command: if True, will add fae argument to the command
        :param args: arguments to the example above
        :param expect_reboot: if True, will expect the machine to reload as result of the command, and reconnect engines
        :param force: if True, will add "force" argument to the command
        :param topology_obj: if exists, waits for 'System is ready'
        """
        cmd = "nv action install {fae} platform {args} {force}".format(fae="fae" if fae_command else '', args=args, force="force" if force else '')
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        if expect_reboot:
            return DutUtilsTool.reload(engine=engine, device=device, command=cmd, confirm=True,
                                       reboot_params=RebootParams(topology_obj=topology_obj)
                                       ).verify_result()
        else:
            return engine.run_cmd(cmd)

    @staticmethod
    @check_output
    def nvue_action_uninstall(engine, device, fae_command, args, expect_reboot, force, topology_obj):
        """
        Method to runs nv action uninstall <fae> platform <args> <force>
        :param engine: the engine to use
        :param device: Noga device info
        :param fae_command: if True, will add fae argument to the command
        :param args: arguments to the example above
        :param expect_reboot: if True, will expect the machine to reload as result of the command, and reconnect engines
        :param force: if True, will add "force" argument to the command
        """
        cmd = "nv action uninstall {fae} platform {args} {force}".format(fae="fae" if fae_command else '', args=args, force="force" if force else '')
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        if expect_reboot:
            return DutUtilsTool.reload(engine=engine, device=device, command=cmd, confirm=True,
                                       reboot_params=RebootParams(topology_obj=topology_obj)
                                       ).verify_result()
        else:
            return engine.run_cmd(cmd)

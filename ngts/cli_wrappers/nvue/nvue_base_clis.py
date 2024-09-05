import logging

from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool

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


class NvueBaseCli:
    cli_name = ""
    check_output_strings = False
    sub_strings_to_search = ['ib', 'sm', 'quantum']

    @staticmethod
    def show(engine, resource_path, op_param="", output_format=OutputFormat.json):
        return NvueBaseCli.nvue_show(engine, resource_path, op_param, output_format)

    @staticmethod
    @check_output
    def nvue_show(engine, resource_path, op_param, output_format):
        path = resource_path.replace('/', ' ')
        cmd = "nv show {path} {params}".format(path=path, params=op_param)
        if output_format:
            cmd = f'{cmd} --output {output_format}'
        cmd = " ".join(cmd.split())
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        return engine.run_cmd(cmd)

    @staticmethod
    def set(engine, resource_path, op_param_name="", op_param_value=""):
        return NvueBaseCli.nvue_set(engine, resource_path, op_param_name, op_param_value)

    @staticmethod
    @check_output
    def nvue_set(engine, resource_path, op_param_name, op_param_value):
        path = resource_path.replace('/', ' ')
        cmd = "nv set {path} {param_name} {param_value}". \
            format(path=path, param_name=op_param_name, param_value=op_param_value)
        cmd = " ".join(cmd.split())
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        return engine.run_cmd(cmd)

    @staticmethod
    def unset(engine, resource_path, op_param=""):
        return NvueBaseCli.nvue_unset(engine, resource_path, op_param)

    @staticmethod
    @check_output
    def nvue_unset(engine, resource_path, op_param):
        path = resource_path.replace('/', ' ')
        cmd = "nv unset {path} {params}". \
            format(path=path, params=op_param)
        cmd = " ".join(cmd.split())
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        return engine.run_cmd(cmd)

    @staticmethod
    def action(engine, device=None, action_type='', resource_path='', suffix="", param_name="", param_value="",
               output_format=None, expect_reboot=False, recovery_engine=None):
        return NvueBaseCli.nvue_action(engine, device, action_type, resource_path, suffix, param_name, param_value,
                                       output_format, expect_reboot, recovery_engine)

    @staticmethod
    @check_output
    def nvue_action(engine, device, action_type, resource_path, suffix, param_name, param_value, output_format,
                    expect_reboot, recovery_engine):
        """See documentation of BaseComponent.action"""
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
            return DutUtilsTool.reload(engine=engine, device=device, command=command, confirm=(param_name != "force"),
                                       recovery_engine=recovery_engine).verify_result()
        else:
            return engine.run_cmd(command)

    @staticmethod
    def action_install(engine, device, fae_command=False, args='', expect_reboot=False, force=False):
        return NvueBaseCli.nvue_action_install(engine, device, fae_command, args, expect_reboot, force)

    @staticmethod
    @check_output
    def nvue_action_install(engine, device, fae_command, args, expect_reboot, force):
        """
        Method to runs nv action install <fae> platform <args> <force>
        :param engine: the engine to use
        :param device: Noga device info
        :param fae_command: if True, will add fae argument to the command
        :param args: arguments to the example above
        :param expect_reboot: if True, will expect the machine to reload as result of the command, and reconnect engines
        :param force: if True, will add "force" argument to the command
        """
        cmd = "nv action install {fae} platform {args} {force}".format(fae="fae" if fae_command else '', args=args, force="force" if force else '')
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        if expect_reboot:
            return DutUtilsTool.reload(engine=engine, device=device, command=cmd, confirm=True).verify_result()
        else:
            return engine.run_cmd(cmd)

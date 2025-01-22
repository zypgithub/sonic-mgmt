import logging
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli, check_output

logger = logging.getLogger()


class NvueIbInterfaceCli(NvueBaseCli):

    def __init__(self):
        self.cli_name = "interface"

    @staticmethod
    @check_output
    def clear_stats(engine, port_name, fae_param=""):
        """
        Clears the interface counters
        :param engine: ssh engine object
        :param port_name: the name of the port/ports
        :param fae_param: optional - run the command with fae
        """
        cmd = 'nv action clear {fae_param} interface {port_name} link counters'.\
            format(fae_param=fae_param, port_name=port_name)
        cmd = " ".join(cmd.split())
        logging.info('Running ' + cmd)
        return engine.run_cmd(cmd)

    @staticmethod
    @check_output
    def action_clear_counters(engine, resource_path, fae_param=""):
        """
        Clear counters for all interfaces
        """
        cmd = 'nv action clear {fae_param} {resource_path} counters'.format(fae_param=fae_param,
                                                                            resource_path=resource_path)
        cmd = " ".join(cmd.split())
        logging.info('Running ' + cmd)
        return engine.run_cmd(cmd)

    @staticmethod
    @check_output
    def show_interface(engine, port_name, interface_hierarchy="", fae_param="", output_format=OutputFormat.json):
        """
        Displays the configuration and the status of the interface
        :param engine: ssh engine object
        :param port_name: the name of the port/ports
        :param output_format: format of the output: auto(table), json or yaml. OutputFormat object is expected
        :param interface_hierarchy: the show level
        :param fae_param: optional - to command with fae
        :return: output str
        """
        cmd = "nv show {fae_param} interface {port_name} {interface_hierarchy} --output {output_format}"\
            .format(fae_param=fae_param, port_name=port_name,
                    interface_hierarchy=interface_hierarchy, output_format=output_format)
        cmd = " ".join(cmd.split())
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        return engine.run_cmd(cmd)

    @staticmethod
    @check_output
    def filter(engine, filter_name, value, output_format=OutputFormat.json):
        param = f"{filter_name}={value}" if filter_name else "\"\""
        cmd = f"nv show interface --filter {param} --output {output_format}"
        cmd = " ".join(cmd.split())
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        return engine.run_cmd(cmd)

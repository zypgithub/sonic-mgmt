import logging
from ngts.nvos_constants.constants_nvos import OutputFormat
from ngts.cli_wrappers.nvue.nvue_base_clis import NvueBaseCli, check_output

logger = logging.getLogger()


class NvuePeerPortCli(NvueBaseCli):

    def __init__(self):
        self.cli_name = "peer-port"

    @staticmethod
    @check_output
    def show_peer_port(engine, peer_port_name, fae_param="", output_format=OutputFormat.json):
        """
        Displays the configuration and the status of the interface
        :param engine: ssh engine object
        :param peer_port_name: the name of the port/ports
        :param output_format: format of the output: auto(table), json or yaml. OutputFormat object is expected
        :param fae_param: optional - to command with fae
        :return: output str
        """
        cmd = "nv show {fae_param} peer-port {port_name} --output {output_format}"\
            .format(fae_param=fae_param, port_name=peer_port_name, output_format=output_format)
        cmd = " ".join(cmd.split())
        logging.info("Running '{cmd}' on dut using NVUE".format(cmd=cmd))
        return engine.run_cmd(cmd)

import json
import logging
import os
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts
from ngts.cli_wrappers.common.performance_clis_common import PerformanceCommon


class NvuePerformanceCli(PerformanceCommon):

    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        super().__init__(topology_obj, engine, dut_alias, cli_obj)

    def apply_configuration_file(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR, dst_dir=PerfConsts.CL_HOME_DIR):
        src_file = self.get_configuration_file_path(scenario, template_suite)
        logging.info(f"Applying configuration file on {self.dut_alias}")
        self.engine.copy_file(source_file=src_file, file_system=dst_dir,
                              dest_file="tmp.yaml", overwrite_file=True, verify_file=False)
        logging.info(f"Configuration file was copied to {self.dut_alias}")
        full_path = os.path.join(dst_dir, "tmp.yaml")
        self.cli_obj.general.replace_config(self.engine, full_path, output_type="json", verify_execution=True)
        self.cli_obj.general.apply_config(self.engine, option="-y", verify_execution=True)
        logging.info(f"The configuration file on {self.dut_alias} was applied successfully")

    def save_basic_configuration(self, players, dst_dir=PerfConsts.CL_HOME_DIR):
        logging.info(f"Saving the basic configuration on {self.dut_alias}")
        self.cli_obj.general.save_config(self.engine)
        self.engine.run_cmd(f"sudo cat /etc/nvue.d/startup.yaml >> {dst_dir}/startup.yaml")

    def restore_basic_configuration(self, file_name="startup.yaml", config_directory=PerfConsts.CL_HOME_DIR):
        logging.info("Replacing the basic configuration on the device")
        full_path = config_directory + "/" + file_name
        self.cli_obj.general.replace_config(self.engine, full_path, output_type="json", verify_execution=True)
        self.cli_obj.general.apply_config(self.engine, option="-y", verify_execution=True)

    def get_configuration_file_path(self, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                 template_suite, scenario, "cumulus", f"{self.dut_alias}.yaml")
        logging.info("Full Path returned is {}".format(full_path))
        return full_path

    def set_ibm(self, players, scenario="", ibm_mode=True, reload_conf=True):
        '''
        Implementation Pending
        '''
        return True

    def get_player_ports(self, dst_dut_dir="/tmp"):
        """
        Args:
            dst_dut_dir: by default /tmp, where the file tg_ports.json is saved

        Returns:
        {'connected_ports': [65537, 65539, ...], 'unconnected_ports': [65659, 65661, ...]}
        """
        logging.info("Getting player connected and unconnected ports")
        get_player_ports_cmd = f"sudo {PerfConsts.CL_PYTHON_PATH} {PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_GET_PORTS}"
        self.execute_cmd(get_player_ports_cmd)
        get_ports_output = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", f"{self.dut_alias}_ports.json")
        self.engine.copy_file(source_file="tg_ports.json", file_system=dst_dut_dir, dest_file=get_ports_output,
                              overwrite_file=True, verify_file=False, direction='get')
        with open(get_ports_output) as f:
            player_ports = json.load(f)
        return player_ports

    def get_tg_unconnected_ports(self):
        player_ports = self.get_player_ports()
        return player_ports["unconnected_ports"]

    def get_dut_ports(self):
        player_ports = self.get_player_ports()
        return player_ports["connected_ports"]

    def get_cmd_for_sdk(self, cmd, env_variables=[]):
        variables = "sudo env "
        for env in env_variables:
            variables += f'\"{env}\"=${env} '
        return variables + PerfConsts.CL_PYTHON_PATH + ' ' + cmd

    def logrotate(self, daemon):
        logging.info(f"Rotating log for {daemon}")
        self.execute_cmd(f"sudo logrotate --force /etc/logrotate.d/{daemon}")

    def get_traffic_parameters(self, scenario, conf_args={}):
        is_ipv6 = conf_args.get("is_ipv6", False)
        ip_key = "IPV6" if is_ipv6 else "IP"
        ip_dict = {
            "IP": {
                "left_tg": {"src": "4.4.4.4", "dst": "130.130.130.1"},
                "right_tg": {"src": "4.4.4.4", "dst": "110.110.110.1"}
            },
            "IPV6": {
                "left_tg": {"src": "4::4", "dst": "130::1"},
                "right_tg": {"src": "4::4", "dst": "110::1"}
            }
        }
        self.logrotate("rsyslog")
        traffic_parameters = {}
        if conf_args["split_left"] == 1:
            dst = self.topology_obj[0]['dut']['cli'].interface.get_interface_mac_address("swp1", verify_execution=True)
        else:
            dst = self.topology_obj[0]['dut']['cli'].interface.get_interface_mac_address("swp1s0", verify_execution=True)
        traffic_parameters["MAC"] = conf_args.get("MAC", {"src": "00:11:22:33:44:55", "dst": dst})
        traffic_parameters["IP"] = conf_args.get("IP", ip_dict[ip_key][self.dut_alias])
        traffic_parameters["UDP"] = conf_args.get("UDP", {"src": PerfConsts.UDP_SOURCE_PORT, "dst": PerfConsts.ROCE_PORT})
        traffic_parameters["AR"] = conf_args.get("AR", PerfConsts.ADAPTIVE_ROUTING_ENABLED)
        traffic_parameters["ports"] = self.get_tg_unconnected_ports()
        return traffic_parameters

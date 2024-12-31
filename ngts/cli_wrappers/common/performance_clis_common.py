import logging
import os
import json
import allure
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts
from infra.tools.exceptions.test_issue import TestIssue
from ngts.helpers.performance.traffic_helpers import create_json_traffic_file


class PerformanceCommon:
    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        self.topology_obj = topology_obj
        self.engine = engine
        self.dut_alias = dut_alias
        self.cli_obj = cli_obj

    def configure_mloops(self):
        logging.info(f"Configure Mloop on {self.dut_alias}")
        cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_MLOOP_CONFIGURATION}"
        self.execute_cmd(cmd)

    def execute_cmd(self, cmd):
        """
        All functions on the inheritance classes (DVS, SONiC, Cumulus) will be executed
        by a thread running on 'left_tg', 'dut' and 'right_tg' switch.
        to have each thread write it's log into individualise file we are setting the logging
        class prior and post the thread run using redirect_thread_stdout.
        since run_cmd use logger and not logging we use this wrapper to get the output
        :param cmd: Command to be executed on the switch
        :return: None or raise error
        """
        try:
            output = self.engine.run_cmd(cmd, validate=True)
            logging.info(f"command output: {output}")
            return output
        except TestIssue as e:
            error_msg = f"Command: {cmd} failed on {self.dut_alias} with error:\n{e}\n"
            logging.error(error_msg)
            raise TestIssue(msg=error_msg)

    def run_traffic(self, scenario, pkt_size, num_packets, is_ipv6, tg_ports=None):
        self.generate_traffic_json(scenario, pkt_size, num_packets, is_ipv6, tg_ports=tg_ports)
        logging.info("Running traffic onto the device")
        run_traffic_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_NAME}"
        self.execute_cmd(run_traffic_cmd)

    def validate_traffic(self, json_path, samples_params_dict, dst_dut_dir="/tmp"):
        logging.info("Running traffic validator on the dut")
        for env_var_name, param_val in samples_params_dict.items():
            set_interval_cmd = f"export {env_var_name}={param_val}"
            self.execute_cmd(set_interval_cmd)
        cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_VALIDATOR_NAME}"
        self.execute_cmd(cmd)
        self.engine.copy_file(source_file="TrafficValidator.json", file_system=dst_dut_dir, dest_file=json_path,
                              overwrite_file=True, verify_file=False, direction='get')

    def stop_traffic(self):
        logging.info(f"Remove Mloop configuration from {self.dut_alias}")
        cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_REMOVE_MLOOP_CONFIGURATION}"
        self.execute_cmd(cmd)

    def generate_traffic_json(self, scenario, pkt_size, num_packets, is_ipv6, tg_ports=None,
                              template_suite="traffic_packets_json_files"):
        tg_ports = self.get_tg_unconnected_ports(scenario) if not tg_ports else tg_ports
        json_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                 scenario, f"{self.dut_alias}_{scenario.replace('/', '_')}_{pkt_size}.json")
        create_json_traffic_file(player_alias=self.dut_alias, tg_ports=tg_ports,
                                 packet_size=pkt_size, num_packets=num_packets,
                                 is_ipv6=is_ipv6, json_path=json_path)
        traffic_json_path = self.copy_traffic_json_to_player(scenario, pkt_size, json_path)
        self.set_tg_json_env_var(traffic_json_path)

    def copy_traffic_json_to_player(self, scenario, pkt_size, json_path, dst_dut_dir="/tmp"):
        file_name = f"{scenario.replace('/', '_')}_{pkt_size}_traffic.json"
        traffic_json_path = os.path.join(dst_dut_dir, file_name)
        logging.info(f"Copy Traffic JSON to : {traffic_json_path} on {self.dut_alias}")
        self.engine.copy_file(source_file=json_path, file_system=dst_dut_dir, dest_file=file_name,
                              overwrite_file=True, verify_file=False)
        return traffic_json_path

    def set_tg_json_env_var(self, traffic_json_path):
        logging.info(f"set TG_JSON ={traffic_json_path} on {self.dut_alias}")
        set_traffic_json_cmd = f"export TG_JSON=\"{traffic_json_path}\""
        self.execute_cmd(set_traffic_json_cmd)

    def get_player_ports(self, scenario, template_suite="traffic_packets_json_files", dst_dut_dir="/tmp"):
        """
        This method should be implemented in child class
        """
        pass

    def get_tg_unconnected_ports(self, scenario):
        """
        This method should be implemented in child class
        """
        pass

    def get_dut_ports(self, scenario):
        """
        This method should be implemented in child class
        """
        pass

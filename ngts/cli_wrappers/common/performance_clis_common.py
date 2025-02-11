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

    def logrotate(self, daemon=''):
        '''
        This method is optional for dvs and sonic but mandatory for cumulus
        Returns:
        This method should return a cmd that rotates the log before running sdk tests.
        '''
        pass

    def get_cmd_for_sdk(self, cmd, env_variables=None):
        """
        This method should be implemented in child class
        Returns:
        This method should return a cmd that is running on the sdk per OS
        """
        raise NotImplementedError

    def apply_configuration_file(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def get_configuration_file(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def save_configuration_file(self, conf_path, conf_json, dst_dut_dir="/tmp"):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def save_basic_configuration(self, players):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def get_player_ports(self, dst_dut_dir="/tmp"):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def get_player_unconnected_connected_ports_aliases(self):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def get_player_left_right_ports_aliases(self):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def restore_basic_configuration(self):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def get_tg_unconnected_ports(self):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def get_dut_ports(self):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def get_sdk_ports(self):
        """
        This method should be implemented in child class
        """
        raise NotImplementedError

    def get_traffic_parameters(self, scenario, conf_args):
        """

        Args:
            scenario: name of the scenario, i.e, spcx_ra
            conf_args: a dict with the configuration arguments per test

        Returns:
        player traffic params based on the scenario configuration file, i.e,
        {
                "MAC" : {"src" : "aa:bb:cc:dd:ee:ff", "dst" : "aa:bb:cc:dd:ee:ff"},
                "IP   : {"src" : "11.11.11.11", "dst" : "22:22:22:22"},
                -------------    OR   -------------
                "IP"  :  {"src" : "1::1", "dst" : "2::2"}
                "UDP" : {"src": int, "dst": int},
                "AR"  : 0/1
            }
        """
        raise NotImplementedError

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

    def configure_mloops(self):
        logging.info(f"Configure Mloop on {self.dut_alias}")
        self.logrotate("rsyslog")
        configure_mloops_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_MLOOP_CONFIGURATION}"
        self.execute_cmd(self.get_cmd_for_sdk(configure_mloops_cmd))

    def run_traffic(self, scenario, traffic_jsons):
        json_path = traffic_jsons[self.dut_alias]
        traffic_json_path = self.copy_traffic_json_to_player(scenario, json_path)
        self.set_tg_json_env_var(traffic_json_path)
        logging.info("Running traffic onto the device")
        run_traffic_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_NAME}"
        self.logrotate("rsyslog")
        self.execute_cmd(self.get_cmd_for_sdk(run_traffic_cmd, env_variables=['TG_JSON']))

    def validate_traffic(self, json_path, samples_params_dict, dst_dut_dir="/tmp"):
        logging.info("Running traffic validator on the dut")
        for env_var_name, param_val in samples_params_dict.items():
            set_interval_cmd = f"export {env_var_name}={param_val}"
            self.execute_cmd(set_interval_cmd)
        run_validator_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_VALIDATOR_NAME}"
        self.logrotate("rsyslog")
        self.execute_cmd(self.get_cmd_for_sdk(run_validator_cmd))
        self.engine.copy_file(source_file="TrafficValidator.json", file_system=dst_dut_dir, dest_file=json_path,
                              overwrite_file=True, verify_file=False, direction='get')

    def stop_traffic(self):
        logging.info(f"Remove Mloop configuration from {self.dut_alias}")
        remove_mloops_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_REMOVE_MLOOP_CONFIGURATION}"
        self.logrotate("rsyslog")
        self.execute_cmd(self.get_cmd_for_sdk(remove_mloops_cmd))

    def copy_traffic_json_to_player(self, scenario, json_path, dst_dut_dir="/tmp"):
        file_name = f"{scenario.replace('/', '_')}_traffic.json"
        traffic_json_path = os.path.join(dst_dut_dir, file_name)
        logging.info(f"Copy Traffic JSON to : {traffic_json_path} on {self.dut_alias}")
        self.engine.copy_file(source_file=json_path, file_system=dst_dut_dir, dest_file=file_name,
                              overwrite_file=True, verify_file=False)
        return traffic_json_path

    def set_tg_json_env_var(self, traffic_json_path):
        logging.info(f"set TG_JSON ={traffic_json_path} on {self.dut_alias}")
        set_traffic_json_cmd = f"export TG_JSON=\"{traffic_json_path}\""
        self.execute_cmd(set_traffic_json_cmd)

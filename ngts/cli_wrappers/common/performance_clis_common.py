import logging
import os
import json
from ngts.constants.performance_constants import PerfConsts
from infra.tools.exceptions.test_issue import TestIssue


class PerformanceCommon:
    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        self.topology_obj = topology_obj
        self.engine = engine
        self.dut_alias = dut_alias
        self.cli_obj = cli_obj

    # Mandatory functions to be implemented by child class
    def get_cmd_for_sdk(self, cmd, env_variables=None):
        """
        This method should be implemented in child class
        Returns:
        This method should return a cmd that is running on the sdk per OS
        """
        raise NotImplementedError

    @staticmethod
    def get_controllers_info_dicts_list(sensors_output):
        """
        returns voltage/current per controller
        Args:
            sensors_output: a string with the output of sensors command

        Returns:
        A list of dicts, each dict contains the values of a controller on the device i.e,
        [{'vout1': 1.20, 'vout2': 1.20, 'iout1': 13.00, 'iout2': 94.00},...]
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

    def get_sdk_ports(self, ports_list):
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

    def get_os_ports_name_mapping(self):
        """
        This method should be implemented in child class
        Returns:
        a list of dicts with os port name for each port
        i.e,
        [{'osPortName': 'Ethernet0', 'port': '0x100f1'},...]
        """
        raise NotImplementedError

    # Optional Functions to be implemented by child class for topology object support
    def get_player_unconnected_connected_ports_aliases(self):
        """
        This method should be implemented in child class
        """
        pass

    def get_player_left_right_ports_aliases(self):
        """
        This method should be implemented in child class
        """
        pass

    # Optional Functions

    def wait_for_nexthop_resolution(self, conf_args=None, number_of_nexthops=None, timeout=120):
        """
        Wait for the number of nexthops to be resolved on the dut
        Implemented for Cumulus only
        """
        pass

    def logrotate(self, daemon=''):
        '''
        This method is optional for dvs and sonic but mandatory for cumulus
        Returns:
        This method should return a cmd that rotates the log before running sdk tests.
        '''
        pass

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
        self.execute_cmd(self.get_cmd_for_sdk(run_traffic_cmd, env_variables=[f'TG_JSON={traffic_json_path}']))

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

    def get_test_specific_values(self, testname):
        """

        Args:
            testname: returns all the test values stored during the test run,
            and adds any OS specific info

        Returns:
            a json obj with the test info, i.e,
            {
                "testName": "test_ar_perf_max_bandwidth[4096-IPv6]",
                "timeStamp": "23-02-2025 14:09:25",
                "configurationName": "x2_400G", ...
            }
        """
        with open(os.path.join(PerfConsts.REQUIRMENTS_DIR, f"{testname}_info_dump.json")) as f:
            test_specific_values = json.load(f)
        return test_specific_values

    def get_sensors_data(self):
        sensors_cmd = r"sensors *-i2c-5-*"
        output = self.execute_cmd(sensors_cmd)
        return output

    def retrieve_default_route(self):
        """
        Retrieve the default route on the the setup
        """
        try:
            retrieve_default_route_cmd = 'ip route | grep default'
            output = self.execute_cmd(retrieve_default_route_cmd)
            return output
        except Exception as e:
            logging.warning(f"Error retrieving default route: {e}")
            return "No route found"

    def restart_daemon(self, daemon):
        """
        This method is optional for dvs and sonic but mandatory for cumulus
        it restarts the daemon on the dut
        """
        pass

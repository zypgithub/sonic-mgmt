import logging
import os
import re
import json
import fcntl
import pandas as pd
from retry import retry
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, ValidationConsts, MultiNosSharedData
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

    def unsplit_all_ports(self):
        """
        Unsplit all ports before test configuration.
        Default implementation does nothing (for SONiC/Cumulus).
        Overridden in DvsPerformance for DVS-specific behavior.
        """
        pass

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

    def validate_no_drops_on_tg_ports(self):
        """
        This Method is checking if any packets were dropped on the traffic genrators
        Mloop ports, indicating that the test full traffic pattern did not reach the dut
        TODO: Should be implemented in DVS and Cumulus
        """
        return []

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

    def check_mloops_up(self):
        """
        This method is used to check if the mloops are up on the traffic generator
        and if not, it will wait for them to be up
        """
        pass

    def execute_cmd(self, cmd, print_output=False):
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
            output = self.engine.run_cmd(cmd, print_output=print_output, validate=True)
            logging.debug(f"command output: {output}")
            return output
        except TestIssue as e:
            error_msg = f"Command: {cmd} failed on {self.dut_alias} with error:\n{e}\n"
            logging.error(error_msg)
            raise TestIssue(msg=error_msg) from e

    def get_port_mapping_df(self):
        sdk_port_to_local_port_mapping = {}
        sdk_port_speed_mapping = {}
        ports_dump_cmd = "sx_api_ports_dump.py"
        output = self.execute_cmd(self.get_cmd_for_sdk(ports_dump_cmd))
        ports_info = re.findall(r"(0x[\d|\w]{5})\|\s+\d+\|\s+\d+\|\s+(\d+)\|.*\|\s+(\d+)G", output)
        for sdk_port, local_port, speed in ports_info:
            sdk_port_to_local_port_mapping[sdk_port] = str(hex(int(local_port) - 1))
            sdk_port_speed_mapping[sdk_port] = int(speed)
        return sdk_port_to_local_port_mapping, sdk_port_speed_mapping

    @retry(exceptions=TestIssue, tries=2, delay=2)
    def configure_mloops(self, validate_mloops=True, is_simx=False):
        try:
            logging.info(f"Configure Mloop on {self.dut_alias}")
            self.logrotate("rsyslog")
            env_variables = [f"{PerfConsts.SEND_FWS_ENV}={'false' if is_simx else 'true'}"]
            configure_mloops_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_MLOOP_CONFIGURATION}"
            self.execute_cmd(self.get_cmd_for_sdk(configure_mloops_cmd, env_variables=env_variables))
            if validate_mloops:
                self.check_mloops_up()
        except Exception as e:
            logging.warning(f"Failed to configure Mloop on {self.dut_alias}: {e}")
            raise TestIssue(msg=f"Failed to configure Mloop on {self.dut_alias}: {type(e).__name__}: {e}") from e

    @retry(exceptions=TestIssue, tries=2, delay=10)
    def run_traffic(self, scenario, traffic_jsons):
        self.cli_obj.interface.clear_counters()
        json_path = traffic_jsons[self.dut_alias]
        traffic_json_path = self.copy_traffic_json_to_player(scenario, json_path)
        self.set_tg_json_env_var(traffic_json_path)
        logging.info("Running traffic onto the device")
        run_traffic_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_NAME}"
        self.logrotate("rsyslog")
        try:
            self.execute_cmd(self.get_cmd_for_sdk(run_traffic_cmd, env_variables=[f'TG_JSON={traffic_json_path}']))
        except Exception as e:
            logging.error(f"Error running traffic: {e}")
            raise TestIssue(msg=f"Error running traffic: {type(e).__name__}: {e}") from e

    def _create_sdk_dump_dirs(self):
        """Create dump directories required by the SDK TrafficValidator.

        The SDK daemon (sx_sdk) may run with systemd PrivateTmp, giving it an
        isolated /tmp.  The daemon writes dump files into its private /tmp,
        but the SDK test process (TrafficValidator) runs outside that namespace
        and needs to read those files.

        The solution is by finding the daemon's actual private tmp path and
        creating symlinks from /tmp/dump_* to the physical location.  This
        lets both the daemon and the test process access the same files.
        If PrivateTmp is not detected, we use nsenter into the daemon's mount
        namespace as a safe default (handles PrivateTmp regardless of whether
        we can discover the path).
        """
        dump_dir_names = ["dump_with_perf_counters", "dump_without_perf_counters"]
        try:
            priv_tmp = self._find_private_tmp()
            if priv_tmp:
                for d in dump_dir_names:
                    self.execute_cmd(f"sudo mkdir -p {priv_tmp}/{d}")
                    self.execute_cmd(f"sudo ln -sfnT {priv_tmp}/{d} /tmp/{d}")
                return
        except Exception:
            logging.warning("Symlink approach failed, falling back to nsenter + plain mkdir")

        self._create_sdk_dump_dirs_via_nsenter(dump_dir_names)

    def _find_private_tmp(self):
        """Find the systemd PrivateTmp path for the SDK service.

        The systemd-private-* directories under /tmp are owned by root with
        mode 0700, so both the glob expansion and the listing must run as
        root.  We use ``sudo bash -c '...'`` so the shell that expands the
        glob is already privileged.
        """
        for service in ("sx_sdk", "switchd"):
            try:
                path = self.execute_cmd(
                    f"sudo bash -c 'ls -d /tmp/systemd-private-*-{service}.service-*/tmp 2>/dev/null | head -1'"
                ).strip()
                if path:
                    return path
            except Exception:
                continue
        return None

    def _create_sdk_dump_dirs_via_nsenter(self, dump_dir_names):
        """Enter the SDK daemon mount namespace and create dump directories."""
        dump_dirs = " ".join(f"/tmp/{d}" for d in dump_dir_names)
        try:
            self.execute_cmd(
                f"sudo bash -c 'PID=$(pgrep -ox sx_sdk || pgrep -ox switchd) && "
                f"nsenter -m -t $PID -- mkdir -p {dump_dirs} || "
                f"mkdir -p {dump_dirs}'"
            )
        except Exception as e:
            raise TestIssue(msg=f"Failed to create SDK dump directories: {e}") from e

    @retry(exceptions=TestIssue, tries=2, delay=2)
    def validate_traffic(self, json_path, samples_params_dict, dst_dut_dir="/tmp"):
        logging.info("Running traffic validator on the dut")
        self._create_sdk_dump_dirs()
        env_variables = []
        for env_var_name, param_val in samples_params_dict.items():
            set_interval_cmd = f"export {env_var_name}={param_val}"
            env_variables.append(f"{env_var_name}={param_val}")
            self.execute_cmd(set_interval_cmd)
        run_validator_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_VALIDATOR_NAME}"
        self.logrotate("rsyslog")
        try:
            self.execute_cmd(self.get_cmd_for_sdk(run_validator_cmd, env_variables=env_variables))
        except Exception as e:
            logging.error(f"Error running traffic validator: {e}")
            raise TestIssue(msg=f"Error running traffic validator: {type(e).__name__}: {e}") from e

        source_path = os.path.join(dst_dut_dir, "TrafficValidator.json")
        try:
            self.engine.copy_file(source_file="TrafficValidator.json", file_system=dst_dut_dir, dest_file=json_path,
                                  overwrite_file=True, verify_file=False, direction='get')
        except Exception as e:
            logging.error(f"Error copying validation file from {source_path} on DUT to {json_path}: {e}")
            raise TestIssue(msg=f"Error copying validation file from DUT: {type(e).__name__}: {e}") from e

        if not os.path.exists(json_path):
            raise TestIssue(f"Traffic validation file was not created at {json_path} after copy from DUT. "
                            f"The file may not exist on the DUT at {source_path}.")

    @retry(exceptions=TestIssue, tries=2, delay=2)
    def stop_traffic(self):
        logging.info(f"Remove Mloop configuration from {self.dut_alias}")
        remove_mloops_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_REMOVE_MLOOP_CONFIGURATION}"
        self.logrotate("rsyslog")
        try:
            self.execute_cmd(self.get_cmd_for_sdk(remove_mloops_cmd))
        except Exception as e:
            logging.error(f"Error stopping traffic: {e}")
            raise TestIssue(msg=f"Error stopping traffic: {type(e).__name__}: {e}") from e

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

    def convert_port_group_df_to_dict(self, port_group_df):
        """
        Convert list of dicts format [{"port":"0x101f1", "portGroupName": "uplink"},..]
        to dict format {"uplink": [all ports], ...} using pandas
        """
        df = pd.DataFrame(port_group_df)
        port_group_df_dict = df.groupby(MongoDbConsts.PORT_GROUP_NAME)[ValidationConsts.PORT].apply(list).to_dict()
        for port_group_name, ports in port_group_df_dict.items():
            port_group_df_dict[port_group_name] = [int(port, PerfConsts.HEX_BASE) for port in ports]
        return {ValidationConsts.PORT_GROUPS: port_group_df_dict}

    def update_port_group_df_on_dut(self, port_group_df):
        """
        Convert list of dicts format [{"port":"0x101f1", "portGroupName": "uplink"},..]
        to dict format {"uplink": [65777, 65778, ...], ...}
        """
        port_group_df_dict = self.convert_port_group_df_to_dict(port_group_df)
        port_group_df_file = "conf.json"
        full_path = os.path.join(PerfConsts.CONFIG_FILES_DIR, port_group_df_file)
        with open(full_path, 'w') as f:
            json.dump(port_group_df_dict, f)
        self.engine.copy_file(source_file=full_path,
                              dest_file=port_group_df_file,
                              file_system='/tmp',
                              direction='put'
                              )

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

    def run_customer_examples_on_sdk(self, example_name):
        """
        Execute a customer example script on the SDK.

        Args:
            example_name (str): The name of the example script to run (e.g., "sx_api_flex_acl_dump.py").

        Returns:
            The result of executing the command via execute_cmd().
        """
        return self.execute_cmd(self.get_cmd_for_sdk(example_name))

    def create_acl_dump(self):
        """
        Generate an ACL dump using the SDK API examples.

        This method runs the sx_api_flex_acl_dump.py script to create a dump of
        all the ACL configurations.

        Returns:
            The output from running the ACL dump command.
        """
        create_acl_dump_cmd = "sx_api_flex_acl_dump.py"
        return self.run_customer_examples_on_sdk(create_acl_dump_cmd)

    def modify_pg_buffer_for_connected_ports(self):
        """
        Modify PG buffer configuration for connected ports only.

        This method runs a sys_sdk test that modifies the buffer configuration for
        specified Priority Groups on all connected ports. It preserves all existing buffer
        parameters and only modifies the pipeline_latency_size and max_borrowed_delta values.

        The modification sets:
        - override_default_max_borrowed_delta: True
        - pipeline_latency_size: User-defined value
        - max_borrowed_delta: User-defined value

        Note: This method assumes pg_buffer_config is already in /tmp/conf.json from apply_test_configuration.
        The configuration is read from the existing conf.json file by the sys_sdk test.

        Returns:
            str: The output from running the buffer modification test.

        Raises:
            TestIssue: If pg_buffer_config is missing, required fields are missing,
                      or the buffer modification fails.
        """
        logging.info(f"[{self.dut_alias}] Running PG buffer modification from existing conf.json")

        modify_pg_buffer_cmd = (f"{PerfConsts.DVS_RUN_TEST_PATH} --names "
                                f"{PerfConsts.DVS_MODIFY_PG_BUFFER_CONNECTED_PORTS}")

        try:
            result = self.execute_cmd(self.get_cmd_for_sdk(modify_pg_buffer_cmd))
        except TestIssue as e:
            raise TestIssue(msg=f"[{self.dut_alias}] Failed to modify PG buffer for connected ports: {e}") from e

        return result

    def get_occ_watermark_per_port_dump(self, sonic_mgmt_path, tar_file_name="occ_headroom_per_port.tar.gz",
                                        tar_file_system='/tmp'):
        """
        Copy occupancy and watermark data tar archive from DUT to local machine.

        This method copies the tar archive file that was created during validation
        from the DUT to the local management system.

        Args:
            sonic_mgmt_path (str): The local path where the tar file will be copied.
            tar_file_name (str, optional): The name of the tar file on the DUT.
                                           Defaults to "occ_headroom_per_port.tar.gz".
            tar_file_system (str, optional): The remote filesystem path where the tar file is located.
                                             Defaults to '/tmp'.

        Returns:
            str: The local path to the copied tar file.
        """
        logging.info(f"Copying occupancy and watermark dump from DUT: {tar_file_system}/{tar_file_name} "
                     f"to {sonic_mgmt_path}")

        self.engine.copy_file(source_file=tar_file_name, file_system=tar_file_system,
                              dest_file=sonic_mgmt_path, overwrite_file=True, verify_file=False, direction='get')

        return sonic_mgmt_path

    def create_sdk_dump(self, sonic_mgmt_path, sdk_dump_file_name="sdkdump", sdk_dump_file_system='/var/log/sdk_dbg'):
        """
        Generate an SDK debug dump and retrieve its contents.

        This method executes the SDK dump generation script, copies the resulting dump
        file from the device to the local management system, and returns the dump contents
        as a string.

        Args:
            sonic_mgmt_path (str): The local path where the SDK dump file will be copied.
            sdk_dump_file_name (str, optional): The name of the SDK dump file. Defaults to "sdkdump".
            sdk_dump_file_system (str, optional): The remote filesystem path where the dump is generated.
                Defaults to '/var/log/sdk_dbg'.

        Returns:
            str: The contents of the SDK dump file as a string.
        """
        create_sdk_dump_cmd = "sx_api_dbg_generate_dump.py"
        self.run_customer_examples_on_sdk(create_sdk_dump_cmd)

        os.environ[PerfConsts.SDK_DUMP_FILE_SYSTEM] = sonic_mgmt_path
        self.engine.copy_file(source_file=sdk_dump_file_name, file_system=sdk_dump_file_system, dest_file=sonic_mgmt_path, overwrite_file=True, verify_file=False, direction='get')

        with open(sonic_mgmt_path) as f:
            sdk_dump_str = f.read()
        return sdk_dump_str

    def write_shared_json(self, key=None, json_path='/tmp', data=None, raise_on_existing=True):
        """
        Write a value for a specific key to the shared JSON file.
        Args:
            key (str): Key to write/update
            json_path (str): Path to the shared JSON file
            data (any): Data to store under the key
            raise_on_existing (bool): If True, raise KeyError if key already exists.
                                      If False, override the existing value. Default is True.
        Raises:
            KeyError: If the key already exists and raise_on_existing is True
        """
        file_name = MultiNosSharedData.DEFAULT_SHARED_JSON
        full_path = os.path.join(json_path, file_name)

        mode = 'r' if os.path.exists(full_path) else 'w'
        with open(full_path, mode, encoding='utf-8') as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                if os.path.exists(full_path) and os.stat(full_path).st_size > 0:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = json.load(f)
                else:
                    content = {}

                if key in content and raise_on_existing:
                    raise KeyError(f"Key '{key}' already exists in the shared JSON file.")
                content[key] = data

                with open(full_path, 'w', encoding='utf-8') as f:
                    json.dump(content, f, indent=2)
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

        self.engine.copy_file(source_file=full_path, dest_file=file_name, file_system=json_path,
                              overwrite_file=True, verify_file=True, direction='put')

    def read_shared_json(self, key, json_path='/tmp'):
        """
        Read the value for a specific key from the shared JSON file.
        Args:
            key (str): Key to read
            json_path (str): Path to the shared JSON file
        Returns:
            The value stored under the key, or None if not found
        Raises:
            FileNotFoundError: If the JSON file does not exist
        """

        file_name = MultiNosSharedData.DEFAULT_SHARED_JSON
        full_path = os.path.join(json_path, file_name)
        self.engine.copy_file(source_file=file_name, dest_file=json_path, file_system=json_path,
                              overwrite_file=True, verify_file=True, direction='get')

        with open(full_path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                content = json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return content.get(key, None)

    def cleanup_shared_json_file(self, json_path='/tmp'):
        """
        Create an empty (zero-byte) shared JSON file at the given path.
        If no path is provided, use the default from PerfConsts.
        Args:
            json_path (str): Path to the shared JSON file. If None, use default.
        """
        file_name = MultiNosSharedData.DEFAULT_SHARED_JSON
        full_path = os.path.join(json_path, file_name)

        open(full_path, 'w').close()

        self.engine.copy_file(source_file=full_path, dest_file=file_name, file_system=json_path, direction='put')

    def dynamic_configuration_helper(self, scenario, performance_parameters):
        """
        This method is used to apply the dynamic configuration on the dut
        """
        pass

    def update_dst_mac_address(self, src_port, dut_mac_addresses, traffic_parameters):
        """
        This method is used to update the dst mac address on the traffic parameters
        Implemented for Nvue only
        """
        pass

    def configure_interfaces_mac_neighbor(self, vlan_interface_configuration_dict):
        """
        This method is used to configure the mac neighbor on the dut
        Implemented for SONiC only
        """
        pass

    def set_shaper(self, speed, shaper_value, shaper_profile="default-global"):
        """
        This method is used to set the shaper on the traffic gen
        """
        pass

    def validate_ets(self, interface_list, queues_list, violations_list):
        """
        This method is used to validate the ETS on the dut
        """
        pass

    def configure_incremental_dips_on_tg(self):
        """
        This method is used to create the incremental dips on the traffic generator
        """
        raise NotImplementedError

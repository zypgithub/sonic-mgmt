import json
import logging
import os
import pprint
import tempfile
import yaml
import re
from retry import retry

from infra.tools.exceptions.test_issue import TestIssue
from ngts.constants.constants import BugHandlerConst, ResultUploaderConst
from ngts.constants.performance_constants import PerfConsts, Cl_Consts, ValidationConsts
from dataclasses import dataclass
from ngts.cli_wrappers.common.performance_clis_common import PerformanceCommon
from jinja2 import Environment, FileSystemLoader
from ngts.helpers.performance.traffic_helpers import generate_ip_address_list, is_ipv6, address_calculator
from time import sleep
import re


@dataclass
class VoltageCurrentInfo:
    vout_number: str
    vout_value: str
    vout_unit: str
    iout_number: str
    iout_value: str
    iout_unit: str


class NvuePerformanceCli(PerformanceCommon):

    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        super().__init__(topology_obj, engine, dut_alias, cli_obj)
        self.port_groups = self.get_right_left_ports_dict()
        self.mac = self.cli_obj.general.get_dut_mac_address()
        self.dut_neighbor_dict = {}
        self.ports = []
        self.connected_ports = []
        self.unconnected_ports = []
        self.ports_mapping = {}
        self.mloops = []
        # self.set_class_vars()    # only for debug where we don't want to apply the config again

    def set_class_vars(self):
        self.ports = self.get_player_ports()
        self.connected_ports = self.ports["connected_ports"]
        self.unconnected_ports = self.ports["unconnected_ports"]
        self.get_os_ports_name_mapping()

    def apply_configuration_file(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR, dst_dir=Cl_Consts.CL_HOME_DIR):
        src_file = self.get_configuration_file(scenario, conf_args, template_suite)
        logging.info(f"Applying configuration file on {self.dut_alias}")
        self.engine.copy_file(source_file=src_file, file_system=dst_dir,
                              dest_file="tmp.yaml", overwrite_file=True, verify_file=False)
        full_path = os.path.join(dst_dir, "tmp.yaml")
        self.cli_obj.general.replace_config(self.engine, full_path, output_type="json", verify_execution=True)
        self.cli_obj.general.apply_config(self.engine, option="-y", verify_execution=True)
        logging.info(f"The configuration file on {self.dut_alias} was applied successfully")
        self.ports = self.get_player_ports()
        self.connected_ports = self.ports["connected_ports"]
        self.unconnected_ports = self.ports["unconnected_ports"]
        self.get_os_ports_name_mapping()

    def save_basic_configuration(self, players, dst_dir=Cl_Consts.CL_HOME_DIR):
        logging.info(f"Saving the basic configuration on {self.dut_alias}")
        self.cli_obj.general.save_config(self.engine)
        self.engine.run_cmd(f"sudo rm {dst_dir}/startup.yaml")
        self.engine.run_cmd(f"sudo cat /etc/nvue.d/startup.yaml >> {dst_dir}/startup.yaml")

    def restore_basic_configuration(self, file_name="startup.yaml", config_directory=Cl_Consts.CL_HOME_DIR):
        logging.info("Replacing the basic configuration on the device")
        full_path = config_directory + "/" + file_name
        self.cli_obj.general.replace_config(self.engine, full_path, output_type="json", verify_execution=True)
        self.cli_obj.general.apply_config(self.engine, option="-y", verify_execution=True)

    def get_configuration_file_path(self, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                 template_suite, scenario, "cumulus", f"{self.dut_alias}.yaml")
        logging.info("Full Path returned is {}".format(full_path))
        return full_path

    def set_ibm(self, scenario, conf_args):
        ibm_mode = True if conf_args["auto_buffer_mode"] == "False" else False
        if conf_args['params']:
            ctl = conf_args.get('params', {}).get("low_ar_thresh", PerfConsts.LOW_AR_THRESHOLD)
            ctm = conf_args.get('params', {}).get("med_ar_thresh", PerfConsts.MED_AR_THRESHOLD)
            cth = conf_args.get('params', {}).get("high_ar_thresh", PerfConsts.HIGH_AR_THRESHOLD)
        else:
            ctl = PerfConsts.LOW_AR_THRESHOLD
            ctm = PerfConsts.MED_AR_THRESHOLD
            cth = PerfConsts.HIGH_AR_THRESHOLD

        logging.info(f"Set IBM mode to {ibm_mode}")
        if ibm_mode:
            txt = "\n".join([
                "ar.p.m = 0",
                f"ar.ctl = {ctl}",
                f"ar.ctm = {ctm}",
                f"ar.cth = {cth}",
                "ar.srt = 10",
                "ar.srf = 10",
                "ar.p.bit = 0",
                "ar.p.frt = 4",
                "ar.p.but = 0",
                "ar.p.sfe = FALSE",
                "ar.p.ste = FALSE",
                "ar.p.ef = FALSE",
                "ar.ecs = 512",
                "ar.ibm = ingress"
            ])
            cmd = "echo \"echo -e \'{}\' > /etc/cumulus/switchd.d/ar_profile_custom.conf\" | sudo su".format(txt)
            self.execute_cmd(cmd)
            logging.info("Enabling the custom ar profile for IBM mode ingress.")
            logging.info(cmd)
            self.execute_cmd("nv set router adaptive-routing profile profile-custom")
            self.cli_obj.general.apply_config(self.engine, option="-y", verify_execution=True)
        else:
            logging.info("Enabling the default ar profile")
            self.execute_cmd("nv set router adaptive-routing profile profile-2")
            self.cli_obj.general.apply_config(self.engine, option="-y", verify_execution=True)
        return True

    def get_player_ports(self, dst_dut_dir="/tmp"):
        """
        Args:
            dst_dut_dir: by default /tmp, where the file tg_ports.json is saved

        Returns:
        {'connected_ports': [65537, 65539, ...], 'unconnected_ports': [65659, 65661, ...]}
        """
        self.logrotate("rsyslog")
        logging.info("Getting player connected and unconnected ports")
        if self.ports:
            return self.ports
        get_player_ports_cmd = f"sudo {Cl_Consts.CL_PYTHON_PATH} {PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_GET_PORTS}"
        self.retry_get_ports(get_player_ports_cmd)
        get_ports_output = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", f"{self.dut_alias}_ports.json")
        self.engine.copy_file(source_file="tg_ports.json", file_system=dst_dut_dir, dest_file=get_ports_output,
                              overwrite_file=True, verify_file=False, direction='get')
        with open(get_ports_output) as f:
            player_ports = json.load(f)
        return player_ports

    @retry(exceptions=Exception, tries=3, delay=1)
    def retry_get_ports(self, get_player_ports_cmd):
        self.execute_cmd(get_player_ports_cmd)
        logging.info("Successfully got player ports")

    def get_tg_unconnected_ports(self):
        player_ports = self.get_player_ports()
        return player_ports["unconnected_ports"]

    def get_mloops_tuples_list(self):
        if self.mloops:
            return self.mloops
        else:
            self.check_mloops_up()
            return self.mloops

    def get_dut_ports(self, sdk_ports=False):
        mgmt_port = "eth0"
        bonus_ports = self.cli_obj.interface.get_bonus_ports(self.engine)
        if sdk_ports:
            player_ports = self.get_player_ports()
            return player_ports["connected_ports"]
        else:
            output = self.execute_cmd("nv sh interface physical -o json")
            try:
                output = json.loads(output)
            except json.JSONDecodeError as j:
                logging.error("Interface output is not a valid JSON object")
                logging.error(f"Output is : {output}")
                raise j
            list_of_ports = list(output.keys())
            list_of_ports.pop(list_of_ports.index(mgmt_port))
            for ports in bonus_ports:
                list_of_ports.pop(list_of_ports.index(ports))
            return list_of_ports

    def get_os_ports_name_mapping(self):
        """
        This method should be implemented in child class
        Returns:
        a list of dicts with os port name for each port
        i.e,
        [{'osPortName': 'Ethernet0', 'port': '0x100f1'},...]
        """
        os_ports_name_mapping = []
        dut_ports = self.get_dut_ports()
        sdk_ports = self.get_sdk_ports(dut_ports)
        for port, sdk_port in zip(dut_ports, sdk_ports):
            self.ports_mapping[port] = sdk_port
            os_ports_name_mapping.append({ValidationConsts.PORT: sdk_port,
                                          ValidationConsts.OS_PORT_NAME: port})
        return os_ports_name_mapping

    def get_cmd_for_sdk(self, cmd, env_variables=[]):
        variables = "sudo env "
        variables += " ".join(env_variables)
        return variables + ' ' + Cl_Consts.CL_PYTHON_PATH + ' ' + cmd

    def logrotate(self, daemon):
        logging.info(f"Rotating log for {daemon}")
        self.execute_cmd(f"sudo logrotate --force /etc/logrotate.d/{daemon}")

    def get_traffic_parameters(self, scenario, conf_args={}):
        if scenario == "srv6":
            traffic_parameters = {
                "ports": self.get_tg_unconnected_ports(),
                "MAC": {"src": self.mac,
                        "dst": conf_args["dut_mac"]},
                "IP": {},
                "IPV6": {},
                PerfConsts.IP_PROTOCOL_UDP: {"src": PerfConsts.UDP_SOURCE_PORT, "dst": PerfConsts.ROCE_PORT},
                PerfConsts.IP_PROTOCOL_TCP: {"sport": PerfConsts.TCP_SOURCE_PORT, "dport": PerfConsts.TCP_DOURCE_PORT},
                "packet_size": conf_args["packet_size"],
                "is_ipv6": conf_args["is_ipv6"],
            }
        else:
            tg_regex = r"(left|right)_tg"
            tg_alias = re.search(tg_regex, self.dut_alias).group(1)
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
            traffic_parameters["packet_size"] = conf_args["packet_size"]
            traffic_parameters["num_packets"] = conf_args[f"{tg_alias}_num_packets"]
            traffic_parameters["is_ipv6"] = is_ipv6
        return traffic_parameters

    def set_ports(self, port_list: list, port_state):
        self.cli_obj.interface.set_ports_admin_state(port_list, port_state)

    def get_sdk_ports(self, ports_list: list):
        ports_string = " ".join(ports_list)
        if self.ports_mapping:
            return [self.ports_mapping[port] for port in ports_list]
        self.engine.copy_file(source_file=f'{Cl_Consts.CL_LOG_PORT_FILE_PATH}/{Cl_Consts.CL_LOG_PORT_FILE}',
                              dest_file=f'{Cl_Consts.CL_LOG_PORT_FILE}',
                              file_system=Cl_Consts.CL_HOME_DIR, overwrite_file=True, verify_file=False)
        sdk_ports = self.execute_cmd(f'sudo python {Cl_Consts.CL_HOME_DIR}/{Cl_Consts.CL_LOG_PORT_FILE} --ports {ports_string}  | egrep \"^[0-9]\"')
        sdk_ports = sdk_ports.split()
        sdk_ports = [hex(int(port)) for port in sdk_ports]
        return sdk_ports

    def get_hex_int_sdk_ports(self, ports_list: list):
        list_of_sdk_ports = []
        if not self.ports_mapping:
            self.get_os_ports_name_mapping()
        for port in ports_list:
            list_of_sdk_ports.append((int(self.ports_mapping[port], PerfConsts.HEX_BASE)))
        return list_of_sdk_ports

    def get_sdk_port(self, port: str):
        try:
            return self.ports_mapping[port]
        except KeyError:
            self.engine.copy_file(source_file=f'{Cl_Consts.CL_LOG_PORT_FILE_PATH}/{Cl_Consts.CL_LOG_PORT_FILE}',
                                  dest_file=f'{Cl_Consts.CL_LOG_PORT_FILE}',
                                  file_system=Cl_Consts.CL_HOME_DIR, overwrite_file=True, verify_file=False)
            sdk_port = self.execute_cmd(f'sudo python {Cl_Consts.CL_HOME_DIR}/{Cl_Consts.CL_LOG_PORT_FILE} --port {port}  | egrep \"^[0-9]\"')
            return hex(int(sdk_port))

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
        sensor_pattern = r'\s*Rail \((out\d+)\):\s+(\d+.\d+ )(m|V)|\s*Curr \((out\d+)\):\s+(\d+.\d+ )(m|A)'
        i2c_group = re.split(r'\n\s*\n', sensors_output)
        controller_dict_list = []
        for group in i2c_group:

            controller_dict = {}
            sensor_info_list = re.findall(sensor_pattern, group)

            for info in sensor_info_list:
                values = VoltageCurrentInfo(*info)
                # convert 'mV' and 'mA' values to corresponding float
                if values.iout_value:
                    converted_value = float(values.iout_value)
                elif values.vout_value:
                    converted_value = float(values.vout_value)
                if values.vout_unit.lower() == 'm' or values.iout_unit.lower() == 'm':
                    converted_value /= 1000
                if values.vout_number:
                    if 'out1' in values.vout_number:
                        controller_dict['vout1'] = converted_value
                    elif 'out2' in values.vout_number:
                        controller_dict['vout2'] = converted_value
                elif values.iout_number:
                    if 'out1' in values.iout_number:
                        controller_dict['iout1'] = converted_value
                    elif 'out2' in values.iout_number:
                        controller_dict['iout2'] = converted_value
            controller_dict_list.append(controller_dict)
        return controller_dict_list

    def get_right_left_ports_dict(self, bring_up_ports=False):
        """
        Returns:
        A dict of ports in the dut connect to the right TG and left TG, i.e,
        {'left_ports': ['swp1s0', 'swp1s1', ...,], 'right_ports': ['swp33s0', 'swp33s1',...]}
        """
        right_left_port_dict = {
            'right_ports': [],
            'left_ports': []
        }
        if bring_up_ports:
            for dut in PerfConsts.PERF_SETUP_PLAYERS_ALIASES:
                self.topology_obj[0][dut]['cli'].interface.initialize_physical_ports()
            logging.info("Waiting 10 seconds for LLDP neighbor to get populated.")
            sleep(10)
        lldp_json = self.cli_obj.interface.get_lldp_neighbors(output_type="json")
        for port, properties in lldp_json.items():
            if [*properties['lldp']['neighbor'].keys()][0] == 'right-tg':
                right_left_port_dict["right_ports"].append(port)
            if [*properties['lldp']['neighbor'].keys()][0] == 'left-tg':
                right_left_port_dict["left_ports"].append(port)
        return right_left_port_dict

    def get_configuration_file(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        func_dict = {"get_right_left_ports_dict": self.get_right_left_ports_dict,
                     "generate_ip_address_list": generate_ip_address_list,
                     "filter_ports": self.cli_obj.interface.filter_lldp_neighbors,
                     "down_ports": self.cli_obj.interface.get_down_ports,
                     "address_calculator": address_calculator
                     }
        asic = self.cli_obj.general.get_asic_model(self.engine)
        number_of_bonus_ports = len(Cl_Consts.BONUS_PORTS[asic])
        total_ports = self.cli_obj.interface.get_physical_ports()
        total_dut_ports = total_ports - number_of_bonus_ports
        templates_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                      template_suite, scenario, "cumulus_jinja")
        templateLoader = FileSystemLoader(searchpath=templates_path)
        templateEnv = Environment(loader=templateLoader)
        TEMPLATE_FILE = "{}.yaml.jinja".format(self.dut_alias)
        jinja_template = templateEnv.get_template(TEMPLATE_FILE)
        jinja_template.globals.update(func_dict)
        parameter_dict = {
            "split_left": conf_args['split_left'],
            "split_right": conf_args['split_right'],
            "total_ports": total_dut_ports,
            "speed": conf_args.get('speed', "400000000"),
            "two_sided_ar": conf_args.get('two_sided_ar', False)
        }
        outputText = jinja_template.render(parameter_dict=parameter_dict)
        # TODO: Add port groups to SDK level, so validator will be able to overview them (SONiC as well)
        self.port_groups = self.get_right_left_ports_dict()
        try:
            yaml.safe_load(outputText)  # just for checking the YAML sanity
        except yaml.YAMLError as yex:
            logging.error(yex)
            logging.error(f"{self.dut_alias}'s Jinja file has resulted in incorrect YAML configuration :- \r\n{pprint.pformat(outputText, depth=12, width=128)}\r\n")
            raise
        fd, path = tempfile.mkstemp()
        with open(path, 'w') as f:
            f.write(outputText)
        return path

    def get_device_configuration(self, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        """
        Returns:
        A dict of the device configuration for the given scenario
        """
        self.engine.copy_file(source_file=f"{Cl_Consts.CL_LOG_PORT_FILE_PATH}/{Cl_Consts.CL_LOG_PORT_FILE}",
                              dest_file=f"{Cl_Consts.CL_LOG_PORT_FILE}",
                              file_system=Cl_Consts.CL_HOME_DIR, overwrite_file=True, verify_file=False)
        right_left_port_dict = self.get_right_left_ports_dict()
        ports_string = " ".join(right_left_port_dict["right_ports"])
        right_side_ports_to_ip_dict = self.get_ports_to_ip_dict(ports_string, conf_args["is_ipv6"], Cl_Consts.COMMON_IP_PREFIX_RIGHT)
        ports_string = " ".join(right_left_port_dict["left_ports"])
        left_side_ports_to_ip_dict = self.get_ports_to_ip_dict(ports_string, conf_args["is_ipv6"], Cl_Consts.COMMON_IP_PREFIX_LEFT)
        return {"right_side_ports_to_ip_dict": right_side_ports_to_ip_dict, "left_side_ports_to_ip_dict": left_side_ports_to_ip_dict}

    def get_ports_to_ip_dict(self, ports_string, is_ipv6, ip_prefix):
        output = self.execute_cmd(f"sudo python {Cl_Consts.CL_HOME_DIR}/{Cl_Consts.CL_LOG_PORT_FILE} --ports {ports_string}  | egrep \"^[0-9]\"")
        port_list = output.split()
        ports_to_ip_dict = {}
        for index, port in enumerate(port_list):
            if is_ipv6:
                ports_to_ip_dict[port] = f"{ip_prefix}::{index + 1}"
            else:
                ports_to_ip_dict[port] = f"{ip_prefix}.{ip_prefix}.{ip_prefix}.{index + 1}"
        return ports_to_ip_dict

    def get_dut_system_information(self, session_id, setup_name):
        """
        Args:
            session_id: Mars session id, i.e, 9443960
            setup_name: i.e, nv_performance_mtvr-moose-17

        Returns: a dictionary with the full dut system information, .i.e,
         "dutSystemInformation": {
                "marsSessionId": "9438676",
                "setupName": "nv_performance_mtvr-moose-17",
                "osType": "NVUE",
                "chip": "SPECTRUM4",
                "board": "sn5600",
                "sdkVersion": "4.7.3094-003",
                "hwChassisRev": "AJ",
                "modelNumber": "MSN-9N402-00RI-7N0_Ax",
                "hostDetails": "mtvr-moose-17, IP N/A",
                "serialNumber": "MT2443J011Q7",
                "onieVersion": "2023.11-5.3.0012-115200",
                "psid": "MT_0000000955",
                "osVersion": "Cumulus Linux 5.12.0"
            }
        """
        dut_system_information = {"marsSessionId": session_id,
                                  "setupName": setup_name,
                                  "osType": "NVUE"}

        cmd = f"sudo {Cl_Consts.CL_PYTHON_PATH} {PerfConsts.DVS_RUN_TEST_PATH} -si"
        output = self.execute_cmd(cmd)

        regex_dict = {
            "chip": r"ASIC:\s*(SPECTRUM\d+)",
            "board": r"Platform:\s*([a-zA-Z0-9]+)",
            "sdkVersion": r"SDK Version:\s*([\d|.|-]*)",
            "hwChassisRev": r"HW Revision:\s*([A-Z]+)",
            "modelNumber": r"Model:\s*(.*)",
            "serialNumber": r"Serial Number:\s*([A-Za-z0-9]+)",
            "onieVersion": r"ONIE Version:\s*(.*)",
            "psid": r"PSID:\s*([A-Za-z0-9_]+)",
        }

        for key, regex in regex_dict.items():
            match = re.search(regex, output)
            if match:
                dut_system_information[key] = match.group(1)

        os_regex = r"IMAGE_DESCRIPTION=\"(Cumulus Linux [\d|.]+)\""
        os_output = self.execute_cmd("cat /etc/image-release")
        match = re.search(os_regex, os_output)
        if match:
            dut_system_information["osVersion"] = match.group(1)

        self.modify_board_host_internal_name(output, regex_dict, dut_system_information)
        return dut_system_information

    @staticmethod
    def modify_board_host_internal_name(output, regex_dict, dut_system_information):
        match = re.search(regex_dict["board"], output)
        if match:
            dut_system_information["board"] = ResultUploaderConst.HOST_INTERNAL_NAMES_MAP[match.group(1).lower()]

    def wait_for_nexthop_resolution(self, conf_args, number_of_nexthops=None, timeout=120):
        """
        Wait for the number of nexthops to be resolved on the dut
        Implemented for Cumulus only
        """
        asic_model = self.cli_obj.general.get_asic_model(self.engine)
        if number_of_nexthops is None:
            total_dut_ports = (self.cli_obj.interface.get_physical_ports() - len(Cl_Consts.BONUS_PORTS[asic_model]))
            number_of_nexthops = total_dut_ports * (conf_args["split_left"] + conf_args["split_right"])
            logging.info(f"Number of nexthops to resolve: {number_of_nexthops}")
        nexthop_number = 0
        start_time = timeout
        while nexthop_number < number_of_nexthops:
            nexthop_number = int(self.execute_cmd("ip neighbor show | grep swp | wc -l"))
            logging.info("Number of nexthops resolved on the dut at time {} is {}".format(start_time - timeout, nexthop_number))
            sleep(10)
            timeout -= 10
            if timeout < 0 and nexthop_number < number_of_nexthops:
                raise RealIssue("After {} seconds, the number of nexthops resolved on the dut is {}".format(start_time, nexthop_number))
        return True

    def retrieve_default_route(self):
        """
        Retrieve the default route on the the setup
        """
        retrieve_default_route_cmd = "nv sh vrf mgmt router rib ipv4 | grep connected | awk '{print $1}'"
        try:
            output = self.execute_cmd(retrieve_default_route_cmd)
            return output
        except Exception as e:
            logging.warning(f"Error retrieving default route: {e}")
            return "No route found"

    def restart_daemon(self, daemon):
        self.execute_cmd(f"sudo systemctl restart {daemon}")

    def get_dut_interfaces_ipv6_configuration(self):
        output = self.execute_cmd("nv sh interface -o json")
        interface_output = json.loads(output)
        dut_interfaces_ipv6_configuration_dict = {}
        for interface in interface_output:
            if "swp" not in interface:  # skip non-switch ports
                continue
            else:
                ip_addresses = interface_output[interface]["ip"]['address'].keys()
                for ip in ip_addresses:
                    if is_ipv6(ip) and ("fe80" not in ip):
                        ipv6_address = ip.split("/")[0]
                        dut_interfaces_ipv6_configuration_dict[interface] = ipv6_address
        return dut_interfaces_ipv6_configuration_dict

    def get_tg_interfaces_vlan_configuration(self):
        output = self.execute_cmd("nv sh bridge domain br_default port vlan -o json")
        port_vlan_info = json.loads(output)
        vlan_interface_configuration_dict = {}
        for port, vlan_info_dict in port_vlan_info.items():
            vlan_interface_configuration_dict[port] = [* vlan_info_dict["vlan"].keys()][0]
        return vlan_interface_configuration_dict

    def configure_mac_neighbor(self, port, port_ipv6_address, port_neighbor_mac, vlan):
        """
        Configure the mac neighbor on the dut

        cmd_list = []
        fdb_discard_conf = []
        cmd_list.append(f"nv set vrf default router static {port_ipv6_address}/120 via {port}")
        cmd_list.append(f"nv set interface {port} neighbor ipv6 {port_ipv6_address} lladdr {port_neighbor_mac}")
        self.engine.run_cmd_set(cmd_list)
        """
        pass

    def add_ports_connectivity_to_dut(self, conf_args, selected_connected_ports=None):
        ports_file = "ports.json"
        full_path = os.path.join(PerfConsts.CONFIG_FILES_DIR, ports_file)
        connected_ports = selected_connected_ports if selected_connected_ports else self.connected_ports
        ports_connectivity_dict = {
            "unconnected_ports": self.get_hex_int_sdk_ports(self.unconnected_ports),
            "connected_ports": self.get_hex_int_sdk_ports(connected_ports),
            "speed": conf_args["speed"]}
        with open(full_path, 'w') as f:
            json.dump(ports_connectivity_dict, f)
        self.engine.copy_file(source_file=full_path, file_system="/tmp",
                              dest_file=ports_file, overwrite_file=True, verify_file=False)

    @retry(exceptions=TestIssue, tries=10, delay=1)
    def check_mloops_up(self):
        """
        This method is used to check if the mloops are up on the traffic generator
        and if not, it will wait for them to be up.
        """
        if not self.dut_neighbor_dict:
            self.dut_neighbor_dict = self.cli_obj.interface.filter_lldp_neighbors(neighbor_list=[PerfConsts.DUT_ALIAS],
                                                                                  include_neighbor_ports=True)[PerfConsts.DUT_ALIAS]
        mloops_tuples_list = []
        if len(self.connected_ports) == len(self.unconnected_ports):
            dut_lldp_name = self.dut_alias.replace("_", "-")
            ports_dict = self.cli_obj.interface.filter_lldp_neighbors(neighbor_list=[dut_lldp_name, PerfConsts.DUT_ALIAS])
            down_ports_list = ports_dict[dut_lldp_name]
            up_ports_list = ports_dict[PerfConsts.DUT_ALIAS]
        if len(down_ports_list) != len(self.unconnected_ports):
            raise TestIssue(f"Not all Mloops are up yet on {self.dut_alias}")
        for up_port, down_port in zip(up_ports_list, down_ports_list):
            mloops_tuples_list.append((up_port, down_port))
        self.mloops = mloops_tuples_list
        logging.info(f"Mloops for {self.dut_alias} are up")

    def update_dst_mac_address(self, src_port, dut_mac_addresses, traffic_parameters):
        dut_port = self.dut_neighbor_dict[src_port]
        traffic_parameters["MAC"]["dst"] = dut_mac_addresses[dut_port]

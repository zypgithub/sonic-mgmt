import json
import logging
import os
import pprint
import tempfile
import yaml
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts, Cl_Consts
from dataclasses import dataclass
from ngts.cli_wrappers.common.performance_clis_common import PerformanceCommon
from jinja2 import Environment, FileSystemLoader
from ngts.helpers.performance.traffic_helpers import generate_ip_address_list
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

    def apply_configuration_file(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR, dst_dir=Cl_Consts.CL_HOME_DIR):
        src_file = self.get_configuration_file(scenario, conf_args, template_suite)
        logging.info(f"Applying configuration file on {self.dut_alias}")
        self.engine.copy_file(source_file=src_file, file_system=dst_dir,
                              dest_file="tmp.yaml", overwrite_file=True, verify_file=False)
        logging.info(f"Configuration file was copied to {self.dut_alias}")
        full_path = os.path.join(dst_dir, "tmp.yaml")
        self.cli_obj.general.replace_config(self.engine, full_path, output_type="json", verify_execution=True)
        self.cli_obj.general.apply_config(self.engine, option="-y", verify_execution=True)
        logging.info(f"The configuration file on {self.dut_alias} was applied successfully")

    def save_basic_configuration(self, players, dst_dir=Cl_Consts.CL_HOME_DIR):
        logging.info(f"Saving the basic configuration on {self.dut_alias}")
        self.cli_obj.general.save_config(self.engine)
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
        logging.info(f"Set IBM mode to {ibm_mode}")
        if ibm_mode:
            txt = "\n".join([
                "ar.p.m = 0",
                "ar.ctl = 400",
                "ar.ctm = 800",
                "ar.cth = 2000",
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
        logging.info("Getting player connected and unconnected ports")
        get_player_ports_cmd = f"sudo {Cl_Consts.CL_PYTHON_PATH} {PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_GET_PORTS}"
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

    def get_cmd_for_sdk(self, cmd, env_variables=[]):
        variables = "sudo env "
        for env in env_variables:
            variables += f'\"{env}\"=${env} '
        return variables + Cl_Consts.CL_PYTHON_PATH + ' ' + cmd

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
        traffic_parameters["packet_size"] = conf_args["packet_size"]
        traffic_parameters["num_packets"] = conf_args["num_packets"]
        traffic_parameters["is_ipv6"] = is_ipv6
        return traffic_parameters

    def set_ports(self, port_list: list, port_state):
        self.cli_obj.interface.set_ports_admin_state(port_list, port_state)

    def get_sdk_ports(self, ports_list: list):
        ports_string = " ".join(ports_list)
        self.engine.copy_file(source_file=f'{Cl_Consts.CL_LOG_PORT_FILE_PATH}/{Cl_Consts.CL_LOG_PORT_FILE}',
                              dest_file=f'{Cl_Consts.CL_LOG_PORT_FILE}',
                              file_system=Cl_Consts.CL_HOME_DIR, overwrite_file=True, verify_file=False)
        sdk_ports = self.execute_cmd(f'sudo python {Cl_Consts.CL_HOME_DIR}/{Cl_Consts.CL_LOG_PORT_FILE} --ports {ports_string}  | egrep \"^[0-9]\"')
        sdk_ports = sdk_ports.split()
        logging.info(sdk_ports)
        return sdk_ports

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
                     "down_ports": self.cli_obj.interface.get_down_ports
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
            "total_ports": total_dut_ports
        }
        outputText = jinja_template.render(parameter_dict=parameter_dict)
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

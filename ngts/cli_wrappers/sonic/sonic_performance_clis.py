import logging
import os
import json
import re
from collections import defaultdict
from jsonmerge import merge
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from infra.tools.exceptions.test_issue import TestIssue
from ngts.helpers.system_helpers import copy_files_to_syncd
from ngts.constants.constants import BugHandlerConst, InfraConst, CliType, SonicConst, ConfigDbJsonConst
from ngts.constants.performance_constants import PerfConsts, PowerConsts
from ngts.cli_wrappers.common.performance_clis_common import PerformanceCommon
from ngts.helpers.interface_helpers import get_alias_letter, get_alias_number, convert_letter_to_idx
from ngts.helpers.performance.traffic_helpers import generate_ip_address_dict
from ngts.helpers.config_db_utils import save_config_db_json
from jinja2 import Environment, FileSystemLoader
from ngts.helpers.performance.traffic_helpers import is_ipv6


class SonicPerformanceCli(PerformanceCommon):
    """
    This class is for Performance cli commands for sonic only
    """

    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        self.topology_obj = topology_obj
        self.engine = engine
        self.dut_alias = dut_alias
        self.cli_obj = cli_obj
        self.service_port_idx = -1
        self.service_port = None
        self.sonic_to_sdk_ports_dict = {}
        self.connected_ports, self.unconnected_ports = [], []
        self.mloops = []

    def get_cmd_for_sdk(self, cmd, env_variables=[]):
        docker_exec_syncd_cmd = InfraConst.DOCKER_EXEC_BASH_CMD.format(DOCKER=InfraConst.SYNCD_DOCKER)
        variables = " ".join(env_variables)
        new_cmd = f"{docker_exec_syncd_cmd} '{PerfConsts.EXPORT_PYTHONPATH} {variables} && {cmd}'"
        return new_cmd

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
        controllers_info_dicts_list = []
        controllers_info_str_list = re.split(PowerConsts.CONTROLLER_REGEX, sensors_output)
        for controller_info_str in controllers_info_str_list:
            controller_info_list = controller_info_str.splitlines()
            if controller_info_list:
                controllers_info_dict = {}
                for controller_info in controller_info_list:
                    regex_pattern = r"(Rail|Curr)\s*\((out\d+)\):\s+(\d*\.*\d*)\s+([mV|A|V]*)"
                    controller_info_parsed = re.search(regex_pattern, controller_info)
                    if controller_info_parsed:
                        key = controller_info_parsed.group(2)
                        value = controller_info_parsed.group(3)
                        measure_unit = controller_info_parsed.group(4)
                        key = f"v{key}" if "V" in measure_unit else f"i{key}"
                        controllers_info_dict[key] = float(value) / 1000 if 'm' in measure_unit else float(value)
                controllers_info_dicts_list.append(controllers_info_dict)
        return controllers_info_dicts_list

    def get_dut_system_information(self, session_id, setup_name):
        """
        Args:
            session_id: Mars session id, i.e, 9443960
            setup_name: i.e, nv_performance_mtvr-moose-17

        Returns: a dictionary with the full dut system information, .i.e,
         "dutSystemInformation": {
                "marsSessionId": "9438676",
                "setupName": "nv_performance_mtvr-moose-17",
                "osType": "DVS",
                "chip": "SPECTRUM4",
                "board": "sn5600",
                "sdkVersion": "4.7.3094-003",
                "hwChassisRev": "AJ",
                "modelNumber": "MSN-9N402-00RI-7N0_Ax",
                "hostDetails": "mtvr-moose-17, IP N/A",
                "serialNumber": "MT2443J011Q7",
                "onieVersion": "2023.11-5.3.0012-115200",
                "psid": "MT_0000000955",
                "osVersion": "dvs-os-sonic_4.7.1920_DEV_LK6.1.38_x86_64---2024-09-09 10:43:49"
            }
        """
        chip_type = self.topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific'][
            'chip_type'].replace("SPC", "SPECTRUM")
        dut_hostname = self.topology_obj.players[self.dut_alias]['attributes'].noga_query_data['attributes']['Common'][
            'Name']
        fw_info = self.cli_obj.chassis.get_fw_info()
        platform_summary_info = self.cli_obj.chassis.show_platform_summary()
        platform_syseeprom_info = self.cli_obj.chassis.show_platform_syseeprom()
        dut_system_information = {"marsSessionId": session_id,
                                  "setupName": setup_name,
                                  "osType": CliType.SONIC,
                                  "chip": chip_type,
                                  "osVersion": self.cli_obj.general.get_image_sonic_version(),
                                  "sdkVersion": self.cli_obj.general.get_sdk_version(),
                                  "hostDetails": f"{dut_hostname}, {self.engine.ip}"}
        full_info = "\n".join([fw_info, platform_summary_info, platform_syseeprom_info])
        regex_dict = {
            "board": r"Product\s+Name.*(SN\d+)",
            "fwVersion": r"FW\s+Version:\s+([\d|\.]*)",
            "hwChassisRev": r"Hardware\s+Revision:\s+(.*)",
            "modelNumber": r"Part\s+Number\s+[\d|x]*\s+\d+\s+(.*)",
            "serialNumber": r"Serial\s+Number\s+[\d|x]*\s+\d+\s+(.*)",
            "onieVersion": r"ONIE Version\s+[\d|x]*\s+\d+\s+(.*)",
            "psid": r"PSID:\s+(.*)",
        }
        for key, regex in regex_dict.items():
            match = re.search(regex, full_info)
            if match:
                dut_system_information[key] = match.group(1)
        return dut_system_information

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
            platform_summary_info = self.cli_obj.chassis.show_platform_summary()
            hwsku = re.search(r"HwSKU: (.*)", platform_summary_info).group(1)
            test_specific_values["hwsku"] = hwsku
        return test_specific_values

    def apply_configuration_file(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        with allure.step(f'Apply SKU {conf_args["hwsku"]} on {self.dut_alias}'):
            self.apply_sku(conf_args["hwsku"])

        with allure.step(f'Apply Test Configuration on {self.dut_alias}'):
            self.get_configuration_file(scenario, conf_args, template_suite)

        self.disable_im_on_tg()
        self.load_qos_config_on_dut()

        with allure.step(f'Reload SKU and Test configuration on {self.dut_alias}'):
            self.cli_obj.general.reload_configuration(force=True)
            self.cli_obj.general.verify_dockers_are_up()

        with allure.step(f'Install Traffic generator on {self.dut_alias}'):
            self.cli_obj.general.install_traffic_generator()
        self.sonic_to_sdk_ports_dict = self.get_sonic_to_sdk_port_mapping()
        self.connected_ports, self.unconnected_ports = self.get_connected_unconnected_ports()

    def disable_im_on_tg(self):
        """
        Disables Independent module on traffic generators otherwise unconnected ports
        won't be up after mloop configuration
        """
        if self.dut_alias in PerfConsts.TG_ALIAS_LIST:
            with allure.step(f'Disable IM on {self.dut_alias}'):
                self.disable_im()

    def load_qos_config_on_dut(self):
        """
        Without loading the QOS configuration the dut won't have
        the dscp to tc port mapping determined by the SKU.
        """
        if self.dut_alias in PerfConsts.PERF_SETUP_DUT_ALIASES:
            with allure.step(f'Load QoS configuration on {self.dut_alias}'):
                self.cli_obj.general.reload_configuration(force=True)
                self.cli_obj.general.verify_dockers_are_up()
                self.cli_obj.qos.reload_qos()
                self.cli_obj.general.save_configuration()

    def get_configuration_file(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        templates_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                      template_suite, scenario, "sonic")
        env = Environment(loader=FileSystemLoader(templates_path))
        template_name = f"{self.dut_alias}.jinja" if self.dut_alias in PerfConsts.PERF_SETUP_DUT_ALIASES else "tg.jinja"
        jinja_template = env.get_template(template_name)
        func_dict = {"generate_ip_address_dict": generate_ip_address_dict,
                     "get_right_left_ports_dict": self.get_right_left_ports_dict
                     }
        jinja_template.globals.update(func_dict)
        self.mloops = self.get_mloops_tuples_list()
        vlan_conf = {}
        for idx, mloop in enumerate(self.mloops):
            vlan_conf[100 + idx * 10] = mloop
        template_string = jinja_template.render(connected_ports=self.connected_ports,
                                                unconnected_ports=self.unconnected_ports, vlan_conf=vlan_conf,
                                                dut_alias=self.dut_alias)
        json_dict = json.loads(template_string)
        hwsku_json = self.cli_obj.general.get_config_db()
        updated_config_db = merge(json_dict, hwsku_json)
        conf_path = os.path.join(templates_path, f"{self.dut_alias}_config_db.json")
        self.save_configuration_file(conf_path, updated_config_db, dst_dut_dir="/tmp")
        return conf_path

    def get_device_configuration(self, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        conf_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                 template_suite, scenario, "sonic", f"{self.dut_alias}_config_db.json")
        with open(conf_path, "r") as f:
            conf_json = json.load(f)
        return conf_json

    def apply_sku(self, sku):
        hwsku_json = self.cli_obj.general.load_sku_init_conf(sku)
        self.update_sku(hwsku_json)
        self.update_connected_unconnected_ports(hwsku_json)

    def update_connected_unconnected_ports(self, hwsku_json):
        ports_list = list(hwsku_json["PORT"].keys())
        self.service_port = ports_list.pop(self.service_port_idx)
        if len(ports_list) % 2 == 1:
            raise TestIssue(f"Expected port number should be even, actual port number {len(ports_list)}")
        middle = len(ports_list) // 2
        if self.dut_alias == "left_tg":
            self.connected_ports, self.unconnected_ports = ports_list[:middle], ports_list[middle:]
        elif self.dut_alias == "right_tg":
            self.unconnected_ports, self.connected_ports = ports_list[:middle], ports_list[middle:]
        else:
            self.connected_ports, self.unconnected_ports = ports_list, []

    def update_sku(self, hwsku_json):
        self.update_sku_port_admin_status(hwsku_json)
        save_config_db_json(self.engine, hwsku_json, remove_json_path=False)

    def update_sku_port_admin_status(self, hwsku_json):
        for port, port_dict in hwsku_json["PORT"].items():
            port_dict.update({"admin_status": "up"})

    def save_configuration_file(self, conf_path, conf_json, dst_dut_dir="/tmp"):
        save_config_db_json(self.engine, conf_json, conf_path, remove_json_path=False)

    def save_basic_configuration(self, players):
        config_db_json = self.cli_obj.general.get_config_db()
        full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", PerfConsts.DEFAULT_PERF_TEMPLATES_DIR,
                                 "sonic", f"{self.dut_alias}_basic_config_db.json")
        with open(full_path, 'w') as f:
            json.dump(config_db_json, f)

    def get_player_ports(self, dst_dut_dir="/tmp"):
        return {'connected_ports': self.connected_ports,
                'unconnected_ports': self.unconnected_ports}

    def configure_mloops(self):
        logging.info(f"Configure Mloop on {self.dut_alias}")
        files_list = PerfConsts.CONFIG_FILES_DICT[self.dut_alias]
        copy_files_to_syncd(self.engine, files_list, PerfConsts.CONFIG_FILES_DIR)
        self.execute_cmd(self.get_cmd_for_sdk(f"python3 {PerfConsts.DISABLE_MAC_SCRIPT}"))
        self.cli_obj.mac.clear_fdb()
        configure_mloops_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_MLOOP_CONFIGURATION}"
        self.execute_cmd(self.get_cmd_for_sdk(configure_mloops_cmd))
        self.cli_obj.interface.check_link_state(ifaces=self.unconnected_ports + self.unconnected_ports)

    def copy_traffic_json_to_player(self, scenario, json_path, dst_dut_dir="/tmp"):
        dir_path, file_name = os.path.split(json_path)
        copy_files_to_syncd(self.engine, [file_name], dir_path)
        return f"/{file_name}"

    def restore_basic_configuration(self, dst_dut_dir="/tmp"):
        full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", PerfConsts.DEFAULT_PERF_TEMPLATES_DIR,
                                 "sonic", f"{self.dut_alias}_basic_config_db.json")
        self.engine.copy_file(source_file=full_path, file_system=dst_dut_dir, dest_file=SonicConst.CONFIG_DB_JSON,
                              overwrite_file=True, verify_file=False)
        full_path = os.path.join(dst_dut_dir, SonicConst.CONFIG_DB_JSON)
        self.cli_obj.general.load_configuration(full_path)

    def get_tg_unconnected_ports(self):
        return self.unconnected_ports

    def get_dut_ports(self):
        return self.connected_ports

    def get_sdk_ports(self, ports_list):
        return list(map(self.get_sdk_port, ports_list))

    def get_hex_int_sdk_ports(self, ports_list):
        return list(map(self.get_hex_int_sdk_port, ports_list))

    def get_hex_int_sdk_port(self, port):
        """
        Args:
            port: sonic port, i.e, Ethernet0

        Returns: sdk port mapped to sonic port , i.e, 65777
        """
        return int(self.sonic_to_sdk_ports_dict[port], PerfConsts.HEX_BASE)

    def get_sdk_port(self, port):
        """
        Args:
            port: sonic port, i.e, Ethernet0

        Returns: sdk port mapped to sonic port , i.e, 0x100f1
        """
        return self.sonic_to_sdk_ports_dict[port]

    def get_sdk_port_mapping(self):
        """
        Returns: a dict of port number and a list of sdk hex ports sorted by lane mapping.
        i.e,
        { 1: ['0x100f1', '0x100f2', '0x100f3',...], 2: [...], ... }
        """
        sdk_port_mapping_cmd = f"sx_api_ports_mapping_dump.py"
        sdk_port_mapping_info = self.execute_cmd(self.get_cmd_for_sdk(sdk_port_mapping_cmd))
        regex = r"\|\s+(0x[\d|\w]*)\|\s+\d+\|\s+\d+\|\s+(\d+)\|\s+ENABLED\|\s+\d+\|\s+(.*)\|\s+\d+\|"
        sdk_port_mapping = re.findall(regex, sdk_port_mapping_info)
        sdk_port_mapping_dict = defaultdict(list)

        for hex_port, port_number, lane_map in sdk_port_mapping:
            port_number = int(port_number)
            lane_map_hex_port_tuple = (int(lane_map, PerfConsts.HEX_BASE), hex_port)
            sdk_port_mapping_dict[port_number].append(lane_map_hex_port_tuple)
        for port_number, hex_ports in sdk_port_mapping_dict.items():
            sorted_hex_ports_by_lane_map = sorted(hex_ports, key=lambda lane_map_hex_port_tuple: lane_map_hex_port_tuple[0])
            sorted_hex_ports = [lane_map_hex_port_tuple[1] for lane_map_hex_port_tuple in sorted_hex_ports_by_lane_map]
            sdk_port_mapping_dict[port_number] = sorted_hex_ports
        return sdk_port_mapping_dict

    def get_sonic_port_mapping(self):
        """
        Returns: a list of sonic port number, port name and the lane index in sdk, i.e,
        [(1, Ethernet0, 0),(1, Ethernet1, 1), (1, Ethernet2, 2), ..]
        """
        sonic_port_mapping = []
        ports_aliases_dict = self.cli_obj.interface.parse_ports_aliases_on_sonic()
        for port, port_alias in ports_aliases_dict.items():
            port_number = int(get_alias_number(port_alias))
            port_letter = get_alias_letter(port_alias)
            port_idx = convert_letter_to_idx(port_letter)
            sonic_port_mapping.append((port_number, port, port_idx))
        return sonic_port_mapping

    def get_sonic_to_sdk_port_mapping(self):
        """
        Returns: a dict of sonic port mapped to sdk port, i.e,
        { 'Ethernet0': '0x100f1',...}
        """
        sonic_to_sdk_ports_dict = {}
        sdk_port_mapping_dict = self.get_sdk_port_mapping()
        sonic_port_mapping = self.get_sonic_port_mapping()
        for (port_number, port, idx) in sonic_port_mapping:
            sonic_to_sdk_ports_dict[port] = sdk_port_mapping_dict[port_number][idx]
        return sonic_to_sdk_ports_dict

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
        traffic_parameters = {
            "ports": self.get_sdk_ports(self.get_tg_unconnected_ports()),
            "MAC": {"src": self.get_mac(),
                    "dst": conf_args["dut_mac"]},
            "IP": {},
            "IPV6": {},
            "UDP": {"src": PerfConsts.UDP_SOURCE_PORT, "dst": PerfConsts.ROCE_PORT},
            "packet_size": conf_args["packet_size"],
            "is_ipv6": conf_args["is_ipv6"]
        }
        return traffic_parameters

    def get_mac(self):
        output = self.execute_cmd("sonic-cfggen -j /etc/sonic/config_db.json --var-json DEVICE_METADATA | grep mac")
        return re.search(r'"mac":\s"(.*)"', output).group(1)

    def get_right_left_ports_dict(self):
        """
        Returns:
        A dict of ports in the dut connect to the right TG and left TG, i.e,
        {'right_ports': ['Ethernet256', ...,], 'left_ports': ['Ethernet0',...]}
        """
        dut_ports = self.get_dut_ports()
        middle = len(dut_ports) // 2
        right_left_ports_dict = {"left_ports": dut_ports[:middle], "right_ports": dut_ports[middle:]}
        return right_left_ports_dict

    def get_mloops_tuples_list(self):
        mloops_tuples_list = []
        if len(self.connected_ports) == len(self.unconnected_ports):
            mloops_tuples_list = list(zip(self.connected_ports, self.unconnected_ports))
        return mloops_tuples_list

    def get_connected_unconnected_ports(self):
        transceiver_presence_table_info = self.cli_obj.interface.parse_interfaces_transceiver_presence()
        connected_ports = []
        unconnected_ports = []
        for port, status in transceiver_presence_table_info.items():
            if status['Presence'] == 'Present':
                connected_ports.append(port)
            else:
                unconnected_ports.append(port)
        self.remove_service_port(connected_ports)
        self.remove_service_port(unconnected_ports)
        return connected_ports, unconnected_ports

    def remove_service_port(self, ports_list):
        if self.service_port in ports_list:
            ports_list.remove(self.service_port)

    def disable_im(self):
        self.execute_cmd("sudo cmis_host_mgmt.py --disable")

    def fdb_discard_creation(self):
        configure_fdb_drop_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names TempFdbDiscardCreation"
        self.execute_cmd(self.get_cmd_for_sdk(configure_fdb_drop_cmd))

    def get_tg_interfaces_vlan_configuration(self):
        vlan_brief_info = self.cli_obj.vlan.get_show_vlan_brief_parsed_output(data_line_index=3)
        vlan_interface_configuration_dict = {}
        for vlan, vlan_info_dict in vlan_brief_info.items():
            vlan_ports = list(vlan_info_dict["ports"].keys())
            for port in vlan_ports:
                vlan_interface_configuration_dict[port] = int(vlan)
        return vlan_interface_configuration_dict

    def get_dut_interfaces_ipv6_configuration(self):
        dut_configuration = self.cli_obj.general.get_config_db()
        interface_configuration = dut_configuration[ConfigDbJsonConst.INTERFACE]
        dut_interfaces_ipv6_configuration_dict = {}
        for key in interface_configuration:
            if "|" in key:
                interface, ip = key.split("|")
                if is_ipv6(ip):
                    ipv6_address = ip.split("/")[0]
                    dut_interfaces_ipv6_configuration_dict[interface] = ipv6_address
        return dut_interfaces_ipv6_configuration_dict

    def validate_traffic(self, json_path, samples_params_dict, dst_dut_dir="/tmp"):
        logging.info("Running traffic validator on the dut")
        samples_params = []
        for env_var_name, param_val in samples_params_dict.items():
            samples_params.append(f"{env_var_name}={param_val}")
        run_validator_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_TG_VALIDATOR_NAME}"
        ports_file = "ports.json"
        full_path = os.path.join(PerfConsts.CONFIG_FILES_DIR, ports_file)
        with open(full_path, 'w') as f:
            json.dump({"unconnected_ports": self.get_hex_int_sdk_ports(self.unconnected_ports),
                       "connected_ports": self.get_hex_int_sdk_ports(self.connected_ports)}, f)
        copy_files_to_syncd(self.engine, [ports_file], PerfConsts.CONFIG_FILES_DIR)
        self.execute_cmd(self.get_cmd_for_sdk(run_validator_cmd, env_variables=samples_params))
        self.execute_cmd(f"docker cp {InfraConst.SYNCD_DOCKER}:/tmp/TrafficValidator.json /tmp/TrafficValidator.json")
        self.engine.copy_file(source_file="TrafficValidator.json", file_system=dst_dut_dir, dest_file=json_path,
                              overwrite_file=True, verify_file=False, direction='get')

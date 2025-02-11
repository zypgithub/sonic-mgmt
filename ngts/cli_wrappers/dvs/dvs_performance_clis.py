import logging
import os
import re
import json
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts
from ngts.helpers.performance.traffic_helpers import generate_ip_address_dict
from ngts.cli_wrappers.common.performance_clis_common import PerformanceCommon
from jinja2 import Environment, FileSystemLoader


class DvsPerformance(PerformanceCommon):
    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        super().__init__(topology_obj, engine, dut_alias, cli_obj)
        self.base_ports, self.ports_lanes = self.get_base_ports()

    def get_cmd_for_sdk(self, cmd, env_variables=None):
        """
        Returns:
        a cmd that is running on the sdk, in DVS it's simply the command it's self
        """
        return cmd

    def apply_configuration_file(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        test_name = self.get_configuration_file(scenario, conf_args, template_suite)
        logging.info(f"Configuration to be run {test_name}")
        logging.info(f"Applying the configuration on {self.dut_alias}")
        cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {test_name}"
        self.execute_cmd(cmd)

    def get_configuration_file(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        templates_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                      template_suite, scenario, "dvs")
        env = Environment(loader=FileSystemLoader(templates_path))
        jinja_template = env.get_template(f"{self.dut_alias}.txt")
        func_dict = {"get_right_left_ports_dict": self.get_right_left_ports_dict,
                     "get_split_ports": self.get_split_ports,
                     "generate_ip_list": generate_ip_address_dict}
        jinja_template.globals.update(func_dict)
        template_string = jinja_template.render(conf_args=conf_args, dut_alias=self.dut_alias)
        json_dict = json.loads(template_string)
        conf_path = os.path.join(templates_path, f"{self.dut_alias}_conf.json")
        self.save_configuration_file(conf_path, json_dict, dst_dut_dir="/tmp")
        return json_dict["sdk_test_info"]["sdk_test_name"]

    def get_device_configuration(self, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        conf_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                 template_suite, scenario, "dvs", f"{self.dut_alias}_conf.json")
        with open(conf_path, "r") as f:
            conf_json = json.load(f)
        return conf_json

    def save_configuration_file(self, conf_path, conf_json, dst_dut_dir="/tmp"):
        with open(conf_path, "w") as f:
            json.dump(conf_json["sdk_test_conf"], f)
        file_name = "conf.json"
        conf_json_path = os.path.join(dst_dut_dir, file_name)
        logging.info(f"Copy Configuration JSON to : {conf_json_path} on {self.dut_alias}")
        self.engine.copy_file(source_file=conf_path, file_system=dst_dut_dir, dest_file=file_name,
                              overwrite_file=True, verify_file=False)

    def save_basic_configuration(self, players):
        pass

    def restore_basic_configuration(self):
        restart_cmd = "dvs_stop.sh && dvs_start.sh --sdk_bridge_mode=HYBRID"
        self.execute_cmd(restart_cmd)

    def set_ports(self, ports_list, port_state):
        for port in ports_list:
            set_port_cmd = f"echo y |  sx_api_port_state_set.py --log_port {hex(port)} --state {port_state}"
            self.execute_cmd(set_port_cmd)

    def get_player_ports(self, dst_dut_dir="/tmp"):
        """
        Args:
            dst_dut_dir: by default /tmp, where the file tg_ports.json is saved

        Returns:
        {'connected_ports': [65537, 65539, ...], 'unconnected_ports': [65659, 65661, ...]}
        """
        logging.info("Getting player connected and unconnected ports")
        get_player_ports_cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {PerfConsts.DVS_GET_PORTS}"
        self.execute_cmd(get_player_ports_cmd)
        get_ports_output = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", f"{self.dut_alias}_ports.json")
        self.engine.copy_file(source_file="tg_ports.json", file_system=dst_dut_dir, dest_file=get_ports_output,
                              overwrite_file=True, verify_file=False, direction='get')
        with open(get_ports_output) as f:
            player_ports = json.load(f)
        return player_ports

    def get_player_unconnected_connected_ports_aliases(self):
        """
        Returns:
        A dict of connected and unconnected ports aliases, i.e,
        {"unconnected_ports": [('left_tg_unconnected_port_p1', '0x10001'), ...,],
        "connected_ports": [('left_tg_connected_port_p1', '0x10041'),...,]
        }
        """
        player_ports = self.get_player_ports()
        player_ports_aliases_dict = {"unconnected_ports": [], "connected_ports": []}
        port_alias_regex = r"(u*n*connected_port)"
        for ports_aliases, port_list in player_ports.items():
            ports_alias = re.search(port_alias_regex, ports_aliases).group(1)
            sorted_port_list = sorted(port_list)
            for port_index, port in enumerate(sorted_port_list, start=1):
                player_ports_aliases_dict[ports_aliases].append((f"{self.dut_alias}_{ports_alias}_p{port_index}",
                                                                 hex(port)))
        return player_ports_aliases_dict

    def get_tg_unconnected_ports(self):
        player_ports = self.get_player_ports()
        return player_ports["unconnected_ports"]

    def get_dut_ports(self):
        player_ports = self.get_player_ports()
        return player_ports["connected_ports"]

    def get_base_ports(self):
        """
        Returns:
        A list of tuples of sdk port and label without last port which is mgmt port, i.e,
        [('0x10001',1), ('0x10003',2),...]
        """
        port_dump = self.execute_cmd('sx_api_ports_dump.py')
        port_label_tuple_list = re.findall(r"\|\s+(0x\d*\w*\d*)\|\s+\d+\|\s+\d+\|\s+(\d+)\|", port_dump)
        ports_lanes = self.get_ports_lanes(port_label_tuple_list)
        return port_label_tuple_list[:-1], ports_lanes

    @staticmethod
    def get_ports_lanes(port_label_tuple_list):
        """
        Returns:
        A dict with which port number of lanes:
        {'0x10001': 4, '0x10003': 4, ...}
        """
        ports_lanes = {}
        for idx, (port, label) in enumerate(port_label_tuple_list[:-1]):
            nxt_port, nxt_label = port_label_tuple_list[idx + 1]
            ports_lanes[port] = abs(int(port, 16) - int(nxt_port, 16))
        return ports_lanes

    def get_right_left_ports_dict(self):
        """
        Returns:
        A dict of ports in the dut connect to the right TG and left TG, i.e,
        {'right_ports': ['0x10001', '0x10003', ...,], 'left_ports': ['0x10041', '0x10043',...]}
        """
        ports = {}
        base_ports, _ = self.get_base_ports()
        half_ports_num = len(base_ports) // 2
        sorted_base_ports_by_label = sorted(base_ports, key=lambda port_label_tuple: int(port_label_tuple[1]))
        sorted_base_ports = list(map(lambda port_label_tuple: port_label_tuple[0], sorted_base_ports_by_label))
        ports["left_ports"] = sorted_base_ports[:half_ports_num]
        ports["right_ports"] = sorted_base_ports[half_ports_num:]
        return ports

    def get_player_left_right_ports_aliases(self):
        """
        Returns:
        A dict of left and right ports aliases, i.e,
        {'right_ports': [('right_port_p1', '0x10001'), ...,],
        'left_ports': [('left_port_p1', '0x10041'),...,]
        }
        """
        port_alias_regex = r"((left|right)_port)"
        player_ports = self.get_right_left_ports_dict()
        player_ports_aliases_dict = {"left_ports": [], "right_ports": []}
        for ports_aliases, port_list in player_ports.items():
            port_alias = re.search(port_alias_regex, ports_aliases).group(1)
            for port_index, port in enumerate(port_list, start=1):
                player_ports_aliases_dict[ports_aliases].append((f"{self.dut_alias}_{port_alias}_p{port_index}",
                                                                 port))
        return player_ports_aliases_dict

    def get_split_ports(self, right_split_num, left_split_num):
        """
        TODO: separate the split and test configuration, and build the topology object after the split was made
        Args:
            right_split_num: i.e, 2
            left_split_num: i.e, 4

        Returns:
        A dict with the left / right ports after the split,
            {"right_split_ports": ["65537", "65539",...],
             "left_split_ports": ["65665", "65667",...]
             }
        """
        split_ports = {}
        ports_dict = self.get_right_left_ports_dict()
        split_ports["left_split_ports"] = self.get_all_breakout_ports(left_split_num, ports_dict["left_ports"])
        split_ports["right_split_ports"] = self.get_all_breakout_ports(right_split_num, ports_dict["right_ports"])

        return split_ports

    def get_all_breakout_ports(self, split_num, ports_list):
        breakout_ports = []
        for port in ports_list:
            lane = self.ports_lanes[port]
            num_lanes_after_breakout = lane // int(split_num)
            lanes_after_breakout = list(range(0, lane, num_lanes_after_breakout))
            breakout_ports += [str(int(port, 16) + lane) for lane in lanes_after_breakout]
        return breakout_ports

    def get_traffic_parameters(self, scenario, conf_args, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        """

        Args:
            scenario: name of scenario, i.e, spcx_ra
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
        conf_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                 template_suite, scenario, "dvs", f"{self.dut_alias}_conf.json")
        with open(conf_path) as f:
            conf_json = json.load(f)

        tg_regex = r"(left|right)_tg"
        tg_alias = re.search(tg_regex, self.dut_alias).group(1)
        traffic_parameters = {
            "ports": self.get_tg_unconnected_ports(),
            "MAC": {"src": conf_json["smac"], "dst": conf_json[f"{tg_alias}_mac"]},
            "IP": {"src": conf_json["source_ip"], "dst": conf_json[f"{tg_alias}_dst_ip"]},
            "UDP": {"src": PerfConsts.UDP_SOURCE_PORT, "dst": PerfConsts.ROCE_PORT},
            "AR": PerfConsts.ADAPTIVE_ROUTING_ENABLED,
            "packet_size": conf_args["packet_size"],
            "num_packets": conf_args["num_packets"],
            "is_ipv6": conf_args["is_ipv6"]
        }
        return traffic_parameters

    def set_ibm(self, scenario, conf_args):
        self.restore_basic_configuration()
        self.apply_configuration_file(scenario, conf_args)

    def get_sdk_ports(self, ports_list):
        return ports_list

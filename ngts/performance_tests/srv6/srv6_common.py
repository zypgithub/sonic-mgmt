import os
import json
import allure
import logging
import pytest
import random
import numpy as np
from ngts.helpers.system_helpers import copy_files_to_syncd
from ngts.helpers.performance.traffic_helpers import (generate_mac_range,
                                                      pick_random_non_consecutive_ports, validate_bw_per_ports)
from ngts.helpers.performance.performance_setup_helpers import (Validation, ValidationConfig, run_traffic,
                                                                stop_traffic, run_validation, configure_mloops,
                                                                skip_test_on_unsupported_os, add_test_mongo_metadata)
from ngts.constants.constants import CliType, InfraConst
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, MRCConsts, ValidationConsts
from ngts.performance_tests.srv6.srv6_workloads import get_workload_method
from ngts.performance_tests.srv6.conftest import (get_many_to_few_traffic, get_round_robin_traffic)
from infra.tools.exceptions.test_issue import TestIssue

logger = logging.getLogger()


class TestSRv6Base:

    @pytest.fixture(autouse=True)
    def setup(self, players, engines, cli_objects, is_ipv6, chip_type, conf_args, power_thresholds_by_chip_type):
        self.players = players
        self.engines = engines
        self.cli_objects = cli_objects
        self.engine = engines['dut']
        self.cli_object = self.cli_objects['dut']
        self.tg_cli_object = self.cli_objects[PerfConsts.LEFT_TG_ALIAS]
        self.ip = InfraConst.IPV6 if is_ipv6 else InfraConst.IPV4
        self.chip_type = chip_type
        self.scenario = "srv6"
        self.opt_ts = os.getenv(MRCConsts.OPT_TS, default=MRCConsts.OPT_TS_DEFAULT)
        self.conf_args = conf_args
        self.hwsku = conf_args["hwsku"]
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.dut_interfaces_ipv6_configuration_dict = {}
        self.vlan_interface_configuration_dict = {}

    def round_robin_traffic_test_runner(self, test_name, traffic_type, workload,
                                        upstream, downstream, bisection_traffic=True, packet_size=4096):
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.NVUE)
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.DVS)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            traffic_jsons = get_round_robin_traffic(self.players, self.conf_args, traffic_type,
                                                    upstream, downstream, bisection_traffic,
                                                    self.dut_interfaces_ipv6_configuration_dict,
                                                    create_workload_stream=get_workload_method(workload))
            run_traffic(self.players, self.scenario, traffic_jsons, attach_traffic_json=False)
        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            half_ports_num = (len(upstream) + len(downstream)) // 2
            round_robin_occ_th_dict = {ValidationConsts.TC_OCC_AVG: 11 * half_ports_num,
                                       ValidationConsts.TC_OCC_99: 22 * half_ports_num}
            self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=set(upstream + downstream))
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                      tc_occ_threshold=round_robin_occ_th_dict,
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      counters_list=MRCConsts.COUNTERS_WITH_ECN,
                                      run_validate_counters=False)
            run_validation(config)

    def many_to_one_traffic_test_runner(self, test_name, traffic_type, workload, packet_size=4096):
        """
        For each M in [(4K/OPT_TS)-1, (4K/OPT_TS)]:

        Define M ingress ports that send traffic to a certain single egress port
        Apply SRV6 configuration
        Generate many-to-one traffic
        Validate line rate BW in the egress port.
        Validate no discards (due to trimming) when M =(4K/OPT_TS)-1.
        Validate MRC retransmits and MRC control packets are not dropped
        because of the congestion caused by MRC data flow.
        Validate TC SB max (among ports) watermark < 22*260 buffer cells.
        """
        egress_port, port_group_df = self.get_egress_port_group_df(port_number=1)
        with allure.step(f"Set test info"):
            add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: f"many_to_one_traffic",
                                                MongoDbConsts.PORT_GROUP_DF: port_group_df})

        total_violations_list = []
        ingress_ratio = int(np.ceil(packet_size / self.opt_ts))
        for ingress_ports_num in [ingress_ratio - 1, ingress_ratio]:
            with allure.step(f"Many to one traffic with ingress ports num={ingress_ports_num}, packet_size({packet_size})/opt_ts({self.opt_ts})={ingress_ratio}"):
                ingress_ports = self.get_ingress_ports(egress_port, ingress_ports_num)
                traffic_jsons = get_many_to_few_traffic(self.players, self.conf_args, traffic_type,
                                                        self.dut_interfaces_ipv6_configuration_dict,
                                                        egress_port, ingress_ports,
                                                        create_workload_stream=get_workload_method(workload),
                                                        congestion=True)
                configure_mloops(self.players)
                run_traffic(self.players, self.scenario, traffic_jsons)
                with allure.step(f"Verifying the traffic on egress port: {egress_port}"):
                    self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=egress_port)
                    run_validate_counters = self.is_run_validate_counters_enabled(ingress_ports_num, ingress_ratio)

                    config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                              chip_type=self.chip_type,
                                              run_validate_counters=run_validate_counters,
                                              bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                              tc_occ_threshold=MRCConsts.MANY_TO_ONE_TRAFFIC_TC_OCC_TH,
                                              power_threshold=self.power_thresholds_by_chip_type,
                                              counters_list=MRCConsts.COUNTERS_WITH_ECN)
                    traffic_validation_jsons_list, violations_list = run_validation(config, ignore_violations=True)
                    total_violations_list.append(f"ingress ports num: {ingress_ports_num} violations:")
                    total_violations_list.extend(violations_list)
                stop_traffic(self.players)
        if total_violations_list:
            raise TestIssue("\n".join(total_violations_list))

    def is_run_validate_counters_enabled(self, ingress_ports_num, ingress_ratio):
        return True if ingress_ports_num == ingress_ratio - 1 else False

    def many_to_few_traffic_test_runner(self, test_name, traffic_type, workload,
                                        egress_ports_candidates, ingress_ports, tc_threshold, packet_size=4096):
        total_violations_list = []
        ingress_ratio = int(np.ceil(packet_size / self.opt_ts))
        for M in [ingress_ratio - 1, ingress_ratio]:
            with allure.step(f"Many to few traffic with M: {M}, packet_size({packet_size})/opt_ts({self.opt_ts})={ingress_ratio}"):
                egress_ports_num = len(egress_ports_candidates) // M
                egress_ports = self.get_egress_ports(egress_ports_candidates, egress_ports_num)
                with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
                    configure_mloops(self.players)
                    traffic_jsons = get_many_to_few_traffic(self.players, self.conf_args, traffic_type,
                                                            self.dut_interfaces_ipv6_configuration_dict,
                                                            egress_ports, ingress_ports,
                                                            create_workload_stream=get_workload_method(workload),
                                                            congestion=True)

                    run_traffic(self.players, self.scenario, traffic_jsons)
                with allure.step(f"Verifying the traffic on selected {egress_ports_num} egress ports"):
                    self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=egress_ports)
                    run_validate_counters = self.is_run_validate_counters_enabled(M, ingress_ratio)

                    config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                              chip_type=self.chip_type,
                                              run_validate_counters=run_validate_counters,
                                              bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                              tc_occ_threshold=tc_threshold,
                                              power_threshold=self.power_thresholds_by_chip_type,
                                              counters_list=MRCConsts.COUNTERS_WITH_ECN)
                    traffic_validation_jsons_list, violations_list = run_validation(config, ignore_violations=True)
                    total_violations_list.append(f"M={M} violations:")
                    total_violations_list.extend(violations_list)
                stop_traffic(self.players)
        if total_violations_list:
            raise TestIssue("\n".join(total_violations_list))

    def configure_interfaces_mac_neighbor(self):
        """
        TODO: Should be done via BGP - this is temporary
        Configure static route on dut, however this configuration eventually will be done via BGP
        """
        dut_ports = self.cli_object.performance.get_dut_ports()
        mac_range = generate_mac_range("00:11:22:33:44:55", count=len(dut_ports))
        fdb_discard_conf = []
        cmd_list = []
        for idx, port in enumerate(dut_ports):
            port_ipv6_address = self.dut_interfaces_ipv6_configuration_dict[port].replace("aaaa", "bbbb")
            port_neighbor_mac = mac_range[idx]
            vlan = self.vlan_interface_configuration_dict[port]
            cmd_list.append(f"sudo ip -6 route add {port_ipv6_address}/48 dev {port}")
            cmd_list.append(f"sudo ip -6 neigh add {port_ipv6_address} lladdr {port_neighbor_mac} dev {port}")
            fdb_discard_conf.append([self.cli_object.performance.get_hex_int_sdk_port(port), port_neighbor_mac, vlan])
        self.engine.run_cmd_set(cmd_list)
        self.configure_fdb_discard(fdb_discard_conf)

    def configure_fdb_discard(self, fdb_discard_conf):
        """
        TODO: should be removed with correct ACL - this is temporary

        All egress traffic going into the tg should be dropped, this should be done by ACL
        However currently this is being done by adding correct FDB discard entries via sdk.
        """
        conf_file = "fdb_discard_conf.json"
        full_path = os.path.join(PerfConsts.CONFIG_FILES_DIR, conf_file)
        with open(full_path, 'w') as f:
            json.dump(fdb_discard_conf, f)
        for alias in PerfConsts.PERF_SETUP_TG_ALIASES:
            copy_files_to_syncd(self.engines[alias], [conf_file], PerfConsts.CONFIG_FILES_DIR)
        for alias in PerfConsts.PERF_SETUP_TG_ALIASES:
            tg_cli = self.cli_objects[alias]
            tg_cli.performance.fdb_discard_creation()

    def get_egress_port_group_df(self, port_number):
        port_group_df = []
        ports = self.cli_object.performance.get_dut_ports()
        egress_ports = pick_random_non_consecutive_ports(ports_list=ports, port_number=port_number)
        for port in egress_ports:
            port_group_df.append({"port": self.players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "egress_ports"})
        return egress_ports, port_group_df

    def get_ingress_ports(self, egress_ports, ingress_ports_num):
        dut_ports = self.cli_object.performance.get_dut_ports()
        ingress_ports_candidates = set(dut_ports).difference(egress_ports)
        ingress_ports = random.sample(ingress_ports_candidates, ingress_ports_num)
        return ingress_ports

    def get_egress_ports(self, egress_ports_candidates, egress_ports_num):
        egress_ports = random.sample(egress_ports_candidates, egress_ports_num)
        return egress_ports

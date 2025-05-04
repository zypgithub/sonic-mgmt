import os
import json
import allure
import logging
from ngts.performance_tests.srv6.utils.srv6_traffic_patterns import get_many_to_few_traffic, get_many_to_one_traffic
import pytest
import random
import re
import numpy as np
import time
import pandas as pd
from ngts.helpers.system_helpers import copy_files_to_syncd
from ngts.helpers.performance.traffic_helpers import (generate_mac_range,
                                                      pick_random_non_consecutive_ports,
                                                      pick_random_consecutive_ports,
                                                      validate_trimmed_untrimmed_percentages,
                                                      validate_trimmed_untrimmed_dropped_percentages)
from ngts.helpers.performance.performance_setup_helpers import (Validation, ValidationConfig, run_traffic,
                                                                stop_traffic, run_validation, configure_mloops,
                                                                skip_test_on_unsupported_os, add_test_mongo_metadata)
from ngts.constants.constants import CliType, InfraConst
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, MRCConsts, ValidationConsts
from ngts.performance_tests.srv6.utils.srv6_workloads import get_workload_method
from ngts.performance_tests.srv6.utils.srv6_traffic_patterns import (get_round_robin_traffic)
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

    def round_robin_traffic_test_runner(self, test_name, traffic_type,
                                        upstream_group, downstream_group, bisection_traffic=True):
        upstream_downstream_group = list(zip(upstream_group, downstream_group))
        all_ports_in_test = []
        for upstream, downstream in upstream_downstream_group:
            with allure.step(f"Run round-robin traffic pattern on {len(upstream)} upstream ports and {len(downstream)} downstream ports"):
                traffic_jsons = get_round_robin_traffic(self.players, self.conf_args, traffic_type,
                                                        upstream, downstream, bisection_traffic,
                                                        self.dut_interfaces_ipv6_configuration_dict)
                run_traffic(self.players, self.scenario, traffic_jsons, attach_traffic_json=False)
                all_ports_in_test.extend(upstream + downstream)
        with allure.step(f"Verifying round-robin traffic pattern on all upstream ports and all downstream ports"):
            half_ports_num = len(all_ports_in_test) // 2
            round_robin_occ_th_dict = {ValidationConsts.TC_OCC_AVG: 11 * half_ports_num,
                                       ValidationConsts.TC_OCC_99: 22 * half_ports_num}
            self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=all_ports_in_test)
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                      tc_occ_threshold=round_robin_occ_th_dict,
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      counters_list=MRCConsts.COUNTERS_WITH_ECN)
            run_validation(config)

    def many_to_one_traffic_test_runner(self, test_name, traffic_type, workload, egress_port, ingress_ports):
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
        with allure.step(f"Many to one traffic with ingress ports num={len(ingress_ports)}"):
            traffic_jsons = get_many_to_one_traffic(self.players, self.conf_args, traffic_type,
                                                    self.dut_interfaces_ipv6_configuration_dict,
                                                    egress_port, ingress_ports,
                                                    create_workload_stream=get_workload_method(workload),
                                                    congestion=True)
            with allure.step(f"Clear counters"):
                self.cli_object.interface.clear_counters()
                self.cli_object.interface.clear_queue_counters()
            with allure.step(f"Run traffic"):
                run_traffic(self.players, self.scenario, traffic_jsons, attach_traffic_json=False)
            with allure.step(f"Verifying the traffic on egress port: {egress_port}"):
                self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=egress_port)
                run_validate_counters = self.is_run_validate_counters_enabled(M=len(ingress_ports)) or workload == MRCConsts.WORKLOAD1_NAME
                config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                          chip_type=self.chip_type,
                                          run_validate_counters=run_validate_counters,
                                          bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                          tc_occ_threshold=MRCConsts.MANY_TO_ONE_TRAFFIC_TC_OCC_TH,
                                          power_threshold=self.power_thresholds_by_chip_type,
                                          counters_list=MRCConsts.COUNTERS_WITH_ECN)
                run_validation(config)

    def is_run_validate_counters_enabled(self, M):
        return True if M != MRCConsts.MAX_INGRESS_PORTS_NUM else False

    def many_to_few_traffic_test_runner(self, test_name, traffic_type, workload,
                                        egress_ports, ingress_ports, tc_threshold, M, get_ports_from_start=False):
        with allure.step(f"Run many to few traffic on {len(ingress_ports)} ingress ports and {len(egress_ports)} egress ports, M={M}"):
            traffic_jsons = get_many_to_few_traffic(self.players, self.conf_args, traffic_type,
                                                    self.dut_interfaces_ipv6_configuration_dict,
                                                    egress_ports, ingress_ports,
                                                    create_workload_stream=get_workload_method(workload),
                                                    congestion=True)

            run_traffic(self.players, self.scenario, traffic_jsons)
        with allure.step(f"Verifying the traffic on selected {len(egress_ports)} egress ports"):
            self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=egress_ports)
            run_validate_counters = self.is_run_validate_counters_enabled(M)

            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      run_validate_counters=run_validate_counters,
                                      bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                      tc_occ_threshold=tc_threshold,
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      counters_list=MRCConsts.COUNTERS_WITH_ECN)
            run_validation(config)

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

    def get_egress_port_group_df(self, port_number, get_ports_from_start=False):
        port_group_df = []
        ports = self.cli_object.performance.get_dut_ports()
        egress_ports = pick_random_non_consecutive_ports(ports_list=ports, port_number=port_number)
        if get_ports_from_start:
            egress_ports = ports[:port_number]
        for port in egress_ports:
            port_group_df.append({"port": self.players['dut']['cli'].performance.get_sdk_port(port), MongoDbConsts.PORT_GROUP_NAME: "egress_ports"})
        return egress_ports, port_group_df

    def get_ingress_ports(self, egress_ports, ingress_ports_num, ingress_port_sequence=MRCConsts.INGRESS_PORT_SEQUENCE_CONSECUTIVE, get_ports_from_start=False):
        dut_ports = self.cli_object.performance.get_dut_ports()
        port_list = list(set(dut_ports).difference(egress_ports))
        ingress_ports_candidates = sorted(port_list, key=lambda port: int(re.search(r'Ethernet(\d+)', port).group(1)))
        if ingress_port_sequence == MRCConsts.INGRESS_PORT_SEQUENCE_NON_CONSECUTIVE:
            ingress_ports = pick_random_non_consecutive_ports(ports_list=ingress_ports_candidates, port_number=ingress_ports_num, non_consecutive_gap=8)
        elif ingress_port_sequence == MRCConsts.INGRESS_PORT_SEQUENCE_CONSECUTIVE:
            ingress_ports = pick_random_consecutive_ports(ports_list=ingress_ports_candidates, port_number=ingress_ports_num)
        if get_ports_from_start:
            ingress_ports = ingress_ports_candidates[:ingress_ports_num]
        return ingress_ports

    def get_egress_ports(self, egress_ports_candidates, egress_ports_num, get_ports_from_start=False):
        egress_ports = random.sample(egress_ports_candidates, egress_ports_num)
        if get_ports_from_start:
            egress_ports = egress_ports_candidates[:egress_ports_num]
        return egress_ports

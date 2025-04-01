import os

import allure
import logging
import pytest
import random
import pandas as pd
import numpy as np
from ngts.helpers.performance.performance_setup_helpers import (ValidationConfig,
                                                                Validation,
                                                                configure_mloops, stop_traffic,
                                                                run_traffic, run_validation,
                                                                add_test_mongo_metadata)
from ngts.constants.constants import InfraConst
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, MRCConsts
from ngts.performance_tests.srv6.conftest import (get_many_to_few_traffic, get_many_to_one_traffic)
from ngts.performance_tests.srv6.srv6_common import TestSRv6Base
from ngts.performance_tests.srv6.srv6_workloads import get_workload_method
from ngts.performance_tests.srv6.leaf.conftest import (get_bisection_traffic)
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name
from ngts.helpers.performance.traffic_helpers import (get_avg_ports_tx,
                                                      validate_no_dropped_packets_on_queue,
                                                      validate_no_untrimmed_packets)
from infra.tools.exceptions.test_issue import TestIssue

logger = logging.getLogger()


class TestSRv6Leaf(TestSRv6Base):

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
        self.conf_args = conf_args
        self.hwsku = conf_args["hwsku"]
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.dut_interfaces_ipv6_configuration_dict = self.cli_object.performance.get_dut_interfaces_ipv6_configuration()
        self.vlan_interface_configuration_dict = self.tg_cli_object.performance.get_tg_interfaces_vlan_configuration()
        self.configure_interfaces_mac_neighbor()
        self.opt_ts = os.getenv(MRCConsts.OPT_TS, default=MRCConsts.OPT_TS_DEFAULT)

    @pytest.mark.parametrize("workload", ["workload_1"])
    @pytest.mark.parametrize("traffic_type", MRCConsts.TRAFFIC_TYPE_LIST)
    def test_bisection_srv6(self, request, traffic_type, workload, upstream_downstream_port_group_df, packet_size=4096):
        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = get_perf_test_name(request, self.ip)
            upstream, downstream, port_group_df = upstream_downstream_port_group_df
            egress_ports = upstream + downstream
            add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: f"bisection-{workload}-{traffic_type}",
                                                MongoDbConsts.PORT_GROUP_DF: port_group_df})
        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            create_workload_stream = get_workload_method(workload)
            traffic_jsons = get_bisection_traffic(self.players, self.conf_args, traffic_type,
                                                  self.dut_interfaces_ipv6_configuration_dict,
                                                  create_workload_stream, left_ports=upstream, right_ports=downstream)
            run_traffic(self.players, self.scenario, traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=egress_ports)
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                      tc_occ_threshold=MRCConsts.OCC_TH_DICT,
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      counters_list=MRCConsts.COUNTERS_WITH_ECN)
            run_validation(config)

    @pytest.mark.parametrize("workload", ["workload_1"])
    @pytest.mark.parametrize("traffic_type", MRCConsts.TRAFFIC_TYPE_LIST)
    def test_leaf_srv6(self, request, upstream_downstream_port_group_df, traffic_type, workload, packet_size=4096):
        test_name = get_perf_test_name(request, self.ip)
        with allure.step(f"Set test configuration description"):
            add_test_mongo_metadata(test_name,
                                    {MongoDbConsts.CONF_NAME:
                                     f"leaf-round-robin-{workload}-{traffic_type}"})
        with allure.step(f"Set test correct port group dataframe"):
            upstream, downstream, port_group_df = upstream_downstream_port_group_df
            add_test_mongo_metadata(test_name, {MongoDbConsts.PORT_GROUP_DF: port_group_df})

        self.round_robin_traffic_test_runner(test_name, traffic_type, workload, upstream,
                                             downstream, packet_size=packet_size)

    @pytest.mark.parametrize("workload", ["opt_ts_workload"])
    @pytest.mark.parametrize("traffic_type", [MRCConsts.TRAFFIC_TYPE_SRV6])
    def test_optimal_trimming_value_with_srv6(self, request, cleanup_trimming_threshold, traffic_type, workload,
                                              packet_size=4096):
        egress_ports, port_group_df = self.get_egress_port_group_df(port_number=8)

        self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=egress_ports)
        self.cli_object.trimming.configure_trim_of_all_packets(ports=egress_ports, queue=1, scenario=self.scenario)
        self.cli_object.trimming.enable_trimming_on_lossy_queue()
        self.cli_object.trimming.disable_packets_aging()
        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = get_perf_test_name(request, self.ip)
            add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: f"Calibrate-OPT_TS",
                                                MongoDbConsts.PORT_GROUP_DF: port_group_df})
        comparison_value_dict = {}
        total_violations_list = []
        with allure.step(f"Start to find optimal trimming size in range {MRCConsts.MINIMAL_TRIM_SIZE} - {MRCConsts.MAX_TRIM_SIZE_CHECKING_RANGE} with step 16"):
            for trimming_size in range(MRCConsts.MINIMAL_TRIM_SIZE, MRCConsts.MAX_TRIM_SIZE_CHECKING_RANGE + 1, 16):
                with allure.step(f"Set trimming size to {trimming_size}"):
                    self.cli_object.trimming.configure_trimming_size(trimming_size)
                    ingress_to_one_egress_ports_num = int(np.ceil(packet_size / trimming_size))
                    total_ingress_ports_num = ingress_to_one_egress_ports_num * len(egress_ports)
                    with allure.step(f"Get {total_ingress_ports_num} ingress ports, {ingress_to_one_egress_ports_num} to 1 ratio"):
                        ingress_ports = self.get_ingress_ports(egress_ports, total_ingress_ports_num)
                    traffic_jsons = get_many_to_one_traffic(self.players, self.conf_args, traffic_type,
                                                            self.dut_interfaces_ipv6_configuration_dict,
                                                            egress_ports, ingress_ports,
                                                            create_workload_stream=get_workload_method(workload))
                    self.cli_object.interface.clear_queue_counters()
                    configure_mloops(self.players)
                    with allure.step(f"Run traffic from {total_ingress_ports_num} ingress ports"
                                     f" to {len(egress_ports)} egress ports"):
                        run_traffic(self.players, self.scenario, traffic_jsons)
                    with allure.step(f"Verifying the traffic for trimming size: {trimming_size}, "
                                     f"packet size: {packet_size}"):
                        additional_validations = {
                            "validate_no_untrimmed_packets":
                            Validation(validate_no_untrimmed_packets,
                                       {'cli_obj': self.cli_object,
                                        'interface_list': egress_ports,
                                        'trimming_queue': MRCConsts.TRIMMING_TC,
                                        'drop_queue': MRCConsts.MRC1_DATA_TC})
                        }
                        config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                                  chip_type=self.chip_type,
                                                  run_validate_counters=False,
                                                  bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                                  tc_occ_threshold=None,
                                                  power_threshold=self.power_thresholds_by_chip_type,
                                                  counters_list=MRCConsts.COUNTERS_WITH_ECN,
                                                  additional_validations=additional_validations)
                        traffic_validation_jsons_list, violations_list = run_validation(config, ignore_violations=True)
                        traffic_validation_json = traffic_validation_jsons_list.pop()
                        comparison_value = self.get_comparison_value(traffic_validation_json, trimming_size)
                        with allure.step(f"comparison value for trimming size: {trimming_size}, is {comparison_value}"):
                            comparison_value_dict[trimming_size] = comparison_value
                        total_violations_list.append(f"Violations for trimming size: {trimming_size}, "
                                                     f"ingress ports number: {total_ingress_ports_num}")
                        total_violations_list.extend(violations_list)
                stop_traffic(self.players)
        self.set_opt_ts(comparison_value_dict)
        if total_violations_list:
            raise TestIssue("\n".join(total_violations_list))

    @pytest.mark.parametrize("workload", ["workload_2"])
    @pytest.mark.parametrize("traffic_type", MRCConsts.TRAFFIC_TYPE_LIST)
    def test_leaf_srv6_trimming_many_to_one(self, request, config_optimal_trimming_size,
                                            traffic_type, workload, packet_size=4096):
        test_name = get_perf_test_name(request, self.ip)
        self.many_to_one_traffic_test_runner(test_name, traffic_type, workload, packet_size=packet_size)

    @pytest.mark.parametrize("workload", ["workload_2"])
    @pytest.mark.parametrize("traffic_type", MRCConsts.TRAFFIC_TYPE_LIST)
    def test_leaf_srv6_trimming_many_to_few(self, request, config_optimal_trimming_size,
                                            upstream_downstream_port_group_df, traffic_type, workload):
        test_name = get_perf_test_name(request, self.ip)
        with allure.step(f"Set test configuration description"):
            add_test_mongo_metadata(test_name,
                                    {MongoDbConsts.CONF_NAME:
                                     f"leaf-many-to-few-{workload}-{traffic_type}"})
        with allure.step(f"Set test correct port group dataframe"):
            upstream, downstream, port_group_df = upstream_downstream_port_group_df
            add_test_mongo_metadata(test_name, {MongoDbConsts.PORT_GROUP_DF: port_group_df})
        self.many_to_few_traffic_test_runner(test_name, traffic_type, workload,
                                             egress_ports_candidates=upstream, ingress_ports=downstream,
                                             tc_threshold=MRCConsts.SPINE_MANY_TO_FEW_TRAFFIC_TC_OCC_TH)

    @pytest.mark.parametrize("workload", ["workload_3"])
    @pytest.mark.parametrize("traffic_type", ["SRv6"])
    def test_victim_flow_srv6(self, request, victim_flow_port_group_df, config_optimal_trimming_size, traffic_type, workload, packet_size=4096):
        test_name = get_perf_test_name(request, self.ip)
        with allure.step(f"Set test configuration description"):
            add_test_mongo_metadata(test_name,
                                    {MongoDbConsts.CONF_NAME:
                                     f"leaf-victim-flow-{workload}-{traffic_type}"})
        with allure.step(f"Set test correct port group dataframe"):
            bisection_left, bisection_right, many_to_one_ingress_ports, many_to_one_egress_ports, port_group_df = victim_flow_port_group_df
            egress_ports = bisection_left + bisection_right + many_to_one_egress_ports
            add_test_mongo_metadata(test_name, {MongoDbConsts.PORT_GROUP_DF: port_group_df})
            allure.attach(pd.DataFrame(port_group_df).to_html(), MongoDbConsts.PORT_GROUP_DF, allure.attachment_type.HTML)
        with allure.step(f"get bisection traffic json for traffic generators"):
            bisection_traffic_jsons = get_bisection_traffic(self.players, self.conf_args, traffic_type,
                                                            self.dut_interfaces_ipv6_configuration_dict,
                                                            create_workload_stream=get_workload_method(workload),
                                                            left_ports=bisection_left,
                                                            right_ports=bisection_right)
        with allure.step(f"get many to one traffic json for traffic generators"):
            many_to_one_traffic_jsons = get_many_to_few_traffic(self.players, self.conf_args, traffic_type,
                                                                self.dut_interfaces_ipv6_configuration_dict,
                                                                egress_ports=many_to_one_egress_ports,
                                                                ingress_ports=many_to_one_ingress_ports,
                                                                create_workload_stream=get_workload_method(workload),
                                                                congestion=True)
        with allure.step(f"run bisection traffic"):
            run_traffic(self.players, self.scenario, bisection_traffic_jsons)
        with allure.step(f"run many to one traffic"):
            run_traffic(self.players, self.scenario, many_to_one_traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=egress_ports)
            additional_validations = {"validate_no_dropped_packets_on_queue":
                                      Validation(validate_no_dropped_packets_on_queue,
                                                 {'cli_obj': self.cli_object,
                                                  'interface_list': egress_ports,
                                                  'queue_list': MRCConsts.VICTIM_PORTS_QUEUE_LIST})}
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                      tc_occ_threshold=MRCConsts.OCC_TH_DICT,
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      counters_list=MRCConsts.COUNTERS_WITH_ECN,
                                      additional_validations=additional_validations)
            run_validation(config, ignore_violations=True)

    def get_comparison_value(self, traffic_validation_json, trimming_size):
        avg_ports_tx = get_avg_ports_tx(traffic_validation_json)
        with allure.step(f"Get comparison value for trimming size: {trimming_size}, avg ports tx: {avg_ports_tx}"):
            comparison_value = avg_ports_tx * 158 / trimming_size
        return comparison_value

    def set_opt_ts(self, comparison_value_dict):
        opt_ts, max_value = max(comparison_value_dict.items(), key=lambda x: x[1])
        self.opt_ts = opt_ts
        logger.info(f"Optimal trimming size is: {opt_ts}, max value is: {max_value}")
        with allure.step(f"Set optimal trimming size to {opt_ts}"):
            os.environ[MRCConsts.OPT_TS] = str(opt_ts)

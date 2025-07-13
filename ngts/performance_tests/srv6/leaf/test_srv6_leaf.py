import os

import allure
import logging
from ngts.performance_tests.srv6.utils.srv6_traffic_patterns import get_many_to_few_traffic
import pytest
import pandas as pd
from ngts.helpers.performance.performance_setup_helpers import (ValidationConfig, stop_traffic,
                                                                run_traffic, run_validation,
                                                                add_test_mongo_metadata,
                                                                skip_performance_test_conditionally, skip_test_on_unsupported_chip_type)
from ngts.constants.constants import InfraConst
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, MRCConsts
from ngts.performance_tests.srv6.conftest import (get_upstream_downstream_port_group_df,
                                                  get_upstream_downstream_groups_port_group_df,
                                                  get_leaf_many_to_few_port_group_df,
                                                  config_optimal_trimming_size,
                                                  get_trimming_tests_skip_condition)
from ngts.performance_tests.srv6.utils.srv6_common import TestSRv6Base
from ngts.performance_tests.srv6.utils.srv6_workloads import get_workload_method
from ngts.performance_tests.srv6.leaf.conftest import (get_bisection_traffic)
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name
from ngts.helpers.performance.traffic_helpers import (validate_no_dropped_packets_on_queue)
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
        config_optimal_trimming_size(self.chip_type, self.cli_objects)
        self.opt_ts = os.getenv(MRCConsts.OPT_TS, default=MRCConsts.OPT_TS_DEFAULT)

    @pytest.mark.parametrize("workload", MRCConsts.MRC_REGRESSION_WORKLOADS_LIST)
    @pytest.mark.parametrize("traffic_type", MRCConsts.REGRESSION_TRAFFIC_TYPE_LIST)
    def test_bisection_srv6(self, request, traffic_type, workload, packet_size=4096):
        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = get_perf_test_name(request, self.ip)
            num_of_ports = MRCConsts.UPSTREAM_DOWNSTREAM_NUM_OF_PORTS_BY_CHIP_TYPE[self.chip_type]
            upstream, downstream, port_group_df = get_upstream_downstream_port_group_df(self.players, upstream_ports_num=num_of_ports,
                                                                                        downstream_ports_num=num_of_ports)
            egress_ports = upstream + downstream
            add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: f"bisection",
                                                MongoDbConsts.TEST_WORKLOAD: workload,
                                                MongoDbConsts.TEST_TRAFFIC_TYPE: traffic_type,
                                                MongoDbConsts.PORT_GROUP_DF: port_group_df})
        with allure.step(f"Run bisection traffic pattern on {len(upstream)} upstream ports <-> {len(downstream)} downstream ports"):
            create_workload_stream = get_workload_method(workload)
            traffic_jsons = get_bisection_traffic(self.players, self.conf_args, traffic_type,
                                                  self.dut_interfaces_ipv6_configuration_dict,
                                                  create_workload_stream, left_ports=upstream, right_ports=downstream)
            run_traffic(self.players, self.scenario, traffic_jsons, attach_traffic_json=False)

        with allure.step(f"Verifying the traffic for all egress ports"):
            self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=egress_ports)
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                      tc_occ_threshold=MRCConsts.OCC_TH_DICT,
                                      power_threshold=self.power_thresholds_by_chip_type)
            run_validation(config)

    @pytest.mark.parametrize("traffic_type", MRCConsts.REGRESSION_TRAFFIC_TYPE_LIST)
    def test_leaf_round_robin_srv6(self, request, traffic_type):
        test_name = get_perf_test_name(request, self.ip)
        round_robin_dict = MRCConsts.LEAF_ROUND_ROBIN_PORTS_NUM_BY_CHIP_TYPE[self.chip_type]
        round_robin_ports_num, round_robin_groups_num = round_robin_dict['group_size'], round_robin_dict['group_num']
        upstream_groups, downstream_groups, port_group_df = get_upstream_downstream_groups_port_group_df(self.players,
                                                                                                         upstream_ports_num=round_robin_ports_num,
                                                                                                         downstream_ports_num=round_robin_ports_num,
                                                                                                         num_of_groups=round_robin_groups_num)
        with allure.step(f"Set test configuration description"):
            add_test_mongo_metadata(test_name,
                                    {MongoDbConsts.CONF_NAME:
                                     f"leaf-round-robin",
                                     MongoDbConsts.TEST_TRAFFIC_TYPE: traffic_type,
                                     MongoDbConsts.PORT_GROUP_DF: port_group_df})
        self.round_robin_traffic_test_runner(test_name, traffic_type, upstream_groups, downstream_groups)

    @pytest.mark.parametrize("workload", MRCConsts.MRC_REGRESSION_WORKLOADS_LIST)
    @pytest.mark.parametrize("traffic_type", MRCConsts.REGRESSION_TRAFFIC_TYPE_LIST)
    @pytest.mark.parametrize("ingress_port_sequence", MRCConsts.INGRESS_PORT_SEQUENCE)
    @pytest.mark.parametrize("ingress_ports_num", MRCConsts.INGRESS_PORT_NUMBER_LIST)
    def test_leaf_srv6_trimming_many_to_one(self, request,
                                            traffic_type, workload, ingress_port_sequence, ingress_ports_num, get_ports_from_start=False):
        condition, skip_message = get_trimming_tests_skip_condition(self.cli_object, self.chip_type, "SPC4")
        skip_performance_test_conditionally(condition, skip_message)
        test_name = get_perf_test_name(request, self.ip)
        egress_port, port_group_df = self.get_egress_port_group_df(port_number=1, get_ports_from_start=get_ports_from_start)
        with allure.step(f"Many to one traffic with ingress ports num={ingress_ports_num}"):
            ingress_ports = self.get_ingress_ports(egress_port, ingress_ports_num, ingress_port_sequence, get_ports_from_start=get_ports_from_start)
        with allure.step(f"Set test configuration description"):
            add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: f"{ingress_ports_num}_to_one_traffic",
                                                MongoDbConsts.TEST_WORKLOAD: workload,
                                                MongoDbConsts.TEST_TRAFFIC_TYPE: traffic_type,
                                                MongoDbConsts.INGRESS_PORT_SEQUENCE: ingress_port_sequence,
                                                MongoDbConsts.PORT_GROUP_DF: port_group_df})
        self.many_to_one_traffic_test_runner(test_name, traffic_type, workload, egress_port, ingress_ports)

    @pytest.mark.parametrize("workload", MRCConsts.MRC_REGRESSION_WORKLOADS_LIST)
    @pytest.mark.parametrize("traffic_type", MRCConsts.REGRESSION_TRAFFIC_TYPE_LIST)
    @pytest.mark.parametrize("M", MRCConsts.INGRESS_PORT_NUMBER_LIST)
    def test_leaf_srv6_trimming_many_to_few(self, request, traffic_type, workload, M):
        condition, skip_message = get_trimming_tests_skip_condition(self.cli_object, self.chip_type, "SPC4")
        skip_performance_test_conditionally(condition, skip_message)
        test_name = get_perf_test_name(request, self.ip)
        num_of_ports = MRCConsts.UPSTREAM_DOWNSTREAM_NUM_OF_PORTS_BY_CHIP_TYPE[self.chip_type]
        egress_ports, ingress_ports, port_group_df = get_leaf_many_to_few_port_group_df(self.players, M, num_of_ports)
        with allure.step(f"Set test configuration description"):
            add_test_mongo_metadata(test_name,
                                    {MongoDbConsts.CONF_NAME: f"leaf-many-to-few",
                                     MongoDbConsts.PORT_GROUP_DF: port_group_df,
                                     MongoDbConsts.TEST_TRAFFIC_TYPE: traffic_type,
                                     MongoDbConsts.TEST_WORKLOAD: workload})
        self.many_to_few_traffic_test_runner(test_name, traffic_type, workload,
                                             egress_ports=egress_ports, ingress_ports=ingress_ports, M=M,
                                             tc_threshold=MRCConsts.SPINE_MANY_TO_FEW_TRAFFIC_TC_OCC_TH)

    @pytest.mark.parametrize("traffic_type", [MRCConsts.TRAFFIC_TYPE_SRV6])
    def test_victim_flow_srv6(self, request, victim_flow_port_group_df, traffic_type, packet_size=4096):
        skip_test_on_unsupported_chip_type(self.chip_type, "SPC4")
        test_name = get_perf_test_name(request, self.ip)
        with allure.step(f"Set test configuration description"):
            add_test_mongo_metadata(test_name,
                                    {MongoDbConsts.CONF_NAME:
                                     f"leaf-victim-flow-{traffic_type}"})
        with allure.step(f"Set test correct port group dataframe"):
            bisection_left, bisection_right, many_to_one_ingress_ports, many_to_one_egress_ports, port_group_df = victim_flow_port_group_df
            egress_ports = bisection_left + bisection_right + many_to_one_egress_ports
            add_test_mongo_metadata(test_name, {MongoDbConsts.PORT_GROUP_DF: port_group_df,
                                                MongoDbConsts.TEST_TRAFFIC_TYPE: traffic_type})
            allure.attach(pd.DataFrame(port_group_df).to_html(), MongoDbConsts.PORT_GROUP_DF, allure.attachment_type.HTML)
        with allure.step(f"get bisection traffic json for traffic generators"):
            bisection_traffic_jsons = get_bisection_traffic(self.players, self.conf_args, traffic_type,
                                                            self.dut_interfaces_ipv6_configuration_dict,
                                                            create_workload_stream=get_workload_method(MRCConsts.MRC2_DATA_ONLY_WORKLOAD_NAME),
                                                            left_ports=bisection_left,
                                                            right_ports=bisection_right)
        with allure.step(f"get many to one traffic json for traffic generators"):
            many_to_one_traffic_jsons = get_many_to_few_traffic(self.players, self.conf_args, traffic_type,
                                                                self.dut_interfaces_ipv6_configuration_dict,
                                                                egress_ports=many_to_one_egress_ports,
                                                                ingress_ports=many_to_one_ingress_ports,
                                                                create_workload_stream=get_workload_method(MRCConsts.MRC1_DATA_ONLY_WORKLOAD_NAME),
                                                                congestion=True)
        with allure.step(f"Clear counters"):
            self.cli_object.interface.clear_counters()
            self.cli_object.interface.clear_queue_counters()
        with allure.step(f"run bisection traffic"):
            run_traffic(self.players, self.scenario, bisection_traffic_jsons)
        with allure.step(f"run many to one traffic"):
            run_traffic(self.players, self.scenario, many_to_one_traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            self.cli_object.performance.add_ports_connectivity_to_dut(self.conf_args, selected_connected_ports=egress_ports)
            samples_params_dict = PerfConsts.SAMPLES_PARAMS.copy()
            samples_params_dict[PerfConsts.CLEAR_COUNTERS_ENV_VAR] = "False"
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      run_validate_counters=False,
                                      bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                      tc_occ_threshold=MRCConsts.OCC_TH_DICT,
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      samples_params_dict=samples_params_dict)
            traffic_validation_jsons_list, violations_list = run_validation(config, ignore_violations=True)
        with allure.step(f"stop traffic"):
            stop_traffic(self.players)
        with allure.step(f"validate no dropped packets on queues"):
            validate_no_dropped_packets_on_queue(self.cli_object, egress_ports, MRCConsts.MRC_DATA_ONLY_WORKLOAD_TC_LIST, violations_list)
        if violations_list:
            raise TestIssue("\n".join(violations_list))

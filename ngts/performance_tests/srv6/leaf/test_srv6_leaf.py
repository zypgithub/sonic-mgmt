import allure
import logging
import pytest
from ngts.helpers.performance.traffic_helpers import is_ipv6
from ngts.helpers.performance.performance_setup_helpers import (ValidationConfig, run_traffic, run_validation,
                                                                skip_test_on_unsupported_os, add_test_mongo_metadata)
from ngts.constants.constants import CliType, InfraConst
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, MRCConsts
from ngts.performance_tests.srv6.conftest import get_workload_method, get_upstream_downstream_port_group_df
from ngts.performance_tests.srv6.srv6_common import TestSRv6Base
from ngts.performance_tests.srv6.leaf.conftest import (get_bisection_traffic)
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name
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

    @pytest.mark.parametrize("workload", ["workload_1"])
    @pytest.mark.parametrize("traffic_type", ["IPv6", "SRv6"])
    def test_bisection_srv6(self, request, traffic_type, workload, port_group_df, packet_size=4096):
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.NVUE)
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.DVS)

        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = get_perf_test_name(request.node.name, self.ip)
            add_test_mongo_metadata(test_name, {MongoDbConsts.CONF_NAME: f"bisection-{workload}-{traffic_type}",
                                                MongoDbConsts.PORT_GROUP_DF: port_group_df})
        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            traffic_jsons = get_bisection_traffic(self.players, self.conf_args, traffic_type,
                                                  self.dut_interfaces_ipv6_configuration_dict,
                                                  create_workload_stream=get_workload_method(workload))
            run_traffic(self.players, self.scenario, traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                      tc_occ_threshold=MRCConsts.OCC_TH_DICT,
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      counters_list=MRCConsts.COUNTERS_WITH_ECN)
            run_validation(config)

    @pytest.mark.parametrize("workload", ["workload_1"])
    @pytest.mark.parametrize("traffic_type", ["IPv6", "SRv6"])
    def test_leaf_srv6(self, request, traffic_type, workload, packet_size=4096):

        test_name = get_perf_test_name(request.node.name, self.ip)
        with allure.step(f"Set test configuration description"):
            add_test_mongo_metadata(test_name,
                                    {MongoDbConsts.CONF_NAME:
                                     f"leaf-round-robin-{workload}-{traffic_type}"})
        with allure.step(f"Set test correct port group dataframe"):
            upstream, downstream, port_group_df = get_upstream_downstream_port_group_df(self.players)
            add_test_mongo_metadata(test_name, {MongoDbConsts.PORT_GROUP_DF: port_group_df})

        self.round_robin_traffic_test_runner(test_name, traffic_type, workload, upstream,
                                             downstream, packet_size=packet_size)

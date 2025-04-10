import allure
import logging
import pytest
from ngts.helpers.performance.traffic_helpers import is_ipv6
from ngts.helpers.performance.performance_setup_helpers import (add_test_mongo_metadata)
from ngts.constants.constants import InfraConst
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts
from ngts.performance_tests.srv6.srv6_common import TestSRv6Base
from ngts.performance_tests.srv6.conftest import get_spine_downstream_port_group_df
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name

logger = logging.getLogger()


class TestSRv6Spine(TestSRv6Base):

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
    def test_spine_srv6(self, request, traffic_type, workload, packet_size=4096):
        """
        All to all Full mesh (spine)-

        Each ingress port sends traffic to all egress ports in round-robin.
        In each round, each ingress port sends workload x to egress ports in increasing order,
        different then the increasing order of the other ingress ports. For example:
        First round (1 packet sent):
            port 0 → port 1.
            port 1 → port 2.
            ...
            port 447 → port 0.
        Second round (1 packet sent):
            port 0 → port 2.
            port 1 → port 3.
            ...
            port 447 → port 1.

        In order to recreate this full mesh we just define all the spine downstream ports as both
        downstream and upstream this way get the traffic pattern as seen above.
        """
        test_name = get_perf_test_name(request.node.name, self.ip)
        with allure.step(f"Set test configuration description"):
            add_test_mongo_metadata(test_name,
                                    {MongoDbConsts.CONF_NAME:
                                     f"leaf-round-robin-{workload}-{traffic_type}"})
        with allure.step(f"Set test correct port group dataframe"):
            downstream, port_group_df = get_spine_downstream_port_group_df(self.players)
            add_test_mongo_metadata(test_name, {MongoDbConsts.PORT_GROUP_DF: port_group_df})

        self.round_robin_traffic_test_runner(test_name, traffic_type, workload, upstream=downstream,
                                             downstream=downstream, bisection_traffic=False, packet_size=packet_size)

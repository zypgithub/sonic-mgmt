import allure
import logging
import pandas as pd
import os
import copy

from ngts.performance_tests.lossy_lossless.lossy_lossless_many_to_1.conftest import get_many_to_1_traffic, TestConfig, TRAFFIC_PORTS_GROUP_NAME_TEMPLATE
import pytest
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name
from ngts.helpers.performance.performance_setup_helpers import (ValidationConfig, run_traffic, run_validation,
                                                                get_topology_obj, configure_mloops, stop_traffic,
                                                                create_sdk_dump)
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts, ValidationConsts, MRCConsts
from ngts.helpers.performance.traffic_helpers import get_ports_avg_bw

logger = logging.getLogger()

PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST


@pytest.mark.parametrize(
    "test_config",
    [
        TestConfig(num_of_traffic_ports=10, num_of_lossy_packets=8, num_of_lossless_packets=0, packet_size=PerfConsts.PACKET_SIZE_LIST[0], split_left=2, split_right=2, auto_buffer_mode=True, fboss_enabled=True, adjust_buffer_config=False, test_id="10_to_1_lossy_lossless_scenario_4_many_to_1"),
        TestConfig(num_of_traffic_ports=70, num_of_lossy_packets=0, num_of_lossless_packets=8, packet_size=2500, split_left=4, split_right=4, auto_buffer_mode=True, fboss_enabled=True, adjust_buffer_config=True, num_downlink_ports=10, test_id="70_to_1_lossless_scenario_Ali_Bug"),
        TestConfig(num_of_traffic_ports=60, num_of_lossy_packets=0, num_of_lossless_packets=16, packet_size=4096, split_left=1, split_right=1, auto_buffer_mode=True, fboss_enabled=True, adjust_buffer_config=True, test_id="60_to_1_800G_Bytedance"),
        TestConfig(num_of_traffic_ports=10, num_of_lossy_packets=0, num_of_lossless_packets=16, packet_size=4096, split_left=1, split_right=1, auto_buffer_mode=True, fboss_enabled=True, adjust_buffer_config=True, test_id="10_to_1_800G_Bytedance"),
        TestConfig(num_of_traffic_ports=2, num_of_lossy_packets=0, num_of_lossless_packets=16, packet_size=4096, split_left=1, split_right=1, auto_buffer_mode=True, fboss_enabled=True, adjust_buffer_config=True, test_id="2_to_1_800G_Bytedance")
    ],
    indirect=True
)
class TestLossyLosslessManyToOne:
    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, chip_type, is_ipv6, conf_args):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.dut_engine = engines['dut']
        self.cli_object = self.players['dut']['cli']

        self.conf_args = conf_args
        self.scenario = "lossy_lossless"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.chip_type = chip_type
        self.is_ipv6 = is_ipv6

    @pytest.fixture
    def scenario_name(self, test_config, conf_args):
        return conf_args.get("effective_test_id", test_config.test_id)

    @allure.title('Lossy lossless scenario 4. Many to 1')
    @allure.description('Lossy lossless scenario 4. Send many to 1 one sided traffic')
    def test_loosy_lossless_many_to_1(self, request, scenario_name, test_config, packet_size=4096):
        """
        Test lossy lossless scenario with configurable test parameters.

        Args:
            scenario_name: Scenario name
            test_config: TestConfig object with num_of_traffic_ports, num_of_lossy_packets, num_of_lossless_packets
        """
        test_name = get_perf_test_name(request)
        num_lossy_packets = test_config.num_of_lossy_packets
        num_lossless_packets = test_config.num_of_lossless_packets
        num_of_traffic_ports = test_config.num_of_traffic_ports
        test_id = self.conf_args.get("effective_test_id", test_config.test_id)

        with allure.step(f"Change test name and description"):
            description = (
                f"{test_id} test. Test lossy lossless scenario with {num_of_traffic_ports} traffic ports to 1 port, "
                f"{num_lossy_packets} lossy packets, {num_lossless_packets} lossless packets"
            )

            allure.dynamic.title(test_id)
            allure.dynamic.description(description)

        self.traffic_jsons = get_many_to_1_traffic(self.conf_args, num_lossy_packets, num_lossless_packets, num_of_traffic_ports)

        with allure.step(f"Run traffic on all the ports:"):
            run_traffic(self.players, self.scenario, self.traffic_jsons, parallel_run=False)

        with allure.step(f"Generate SDK dump"):
            full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                     "sdk_dumps", self.scenario, "sdk_dump")
            sdk_dump = create_sdk_dump(self.players, full_path)
            allure.attach(sdk_dump, "SDK dump", attachment_type=allure.attachment_type.TEXT)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            bw_threshold = {
                "dont_care_ports": {
                    ValidationConsts.TX: 0,
                    ValidationConsts.RX: 0
                },
                TRAFFIC_PORTS_GROUP_NAME_TEMPLATE.format(num_of_traffic_ports): {
                    ValidationConsts.TX: None,
                    ValidationConsts.RX: (1 / num_of_traffic_ports) * 0.83
                },
                "single_port_group": {
                    ValidationConsts.RX: None,
                    ValidationConsts.TX: 0.97
                }
            }
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type, bw_threshold=bw_threshold,
                                      tc_occ_threshold=None,
                                      run_validate_counters=False,
                                      power_threshold=self.power_thresholds_by_chip_type)
            run_validation(config)

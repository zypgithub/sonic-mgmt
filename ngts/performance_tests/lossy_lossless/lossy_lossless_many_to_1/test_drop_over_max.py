import allure
import logging
import pandas as pd
import os
import copy

from ngts.performance_tests.lossy_lossless.lossy_lossless_many_to_1.conftest import get_many_to_1_traffic, TestConfig, TRAFFIC_PORTS_GROUP_NAME_TEMPLATE
import pytest
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name
from ngts.helpers.performance.performance_setup_helpers import (ValidationConfig, run_traffic, run_validation, get_topology_obj, configure_mloops, stop_traffic)
from ngts.constants.performance_constants import PerfConsts, ValidationConsts, MRCConsts
from ngts.helpers.performance.traffic_helpers import get_ports_avg_bw

logger = logging.getLogger()

PACKET_SIZE_LIST = PerfConsts.PACKET_SIZE_LIST


@pytest.mark.parametrize(
    "test_config",
    [
        TestConfig(num_of_traffic_ports=1, num_of_lossy_packets=8, num_of_lossless_packets=0, packet_size=4096, split_left=2, split_right=2, auto_buffer_mode=True, fboss_enabled=False, adjust_buffer_config=False, test_id="Drop_over_max_scenario_1_to_1")
    ],
    indirect=True
)
class TestDropOverMax:
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
    def scenario_name(self, test_config):
        return test_config.test_id

    @allure.title('drop over max scenario')
    @allure.description('Lossy drop over max test scenario send 1 to 1 one sided traffic')
    @pytest.mark.parametrize("reserved_buffer_size", PerfConsts.RESERVED_BUFFER_SIZE_WITH_NO_DROPS)
    def test_drop_over_max(self, request, scenario_name, reserved_buffer_size, test_config):
        """
        Drop over max test scenario send 1 to 1 one sided lossy traffic,
        checks if the result headroom buffer size is enough to avoid rx no buffer drops
        on the ingress port
        """
        test_name = get_perf_test_name(request)
        num_lossy_packets = test_config.num_of_lossy_packets
        num_lossless_packets = test_config.num_of_lossless_packets
        num_of_traffic_ports = test_config.num_of_traffic_ports
        test_id = test_config.test_id

        with allure.step(f"Change test name and description"):
            description = (
                f"{test_id} test. Drop over max test scenario send {num_of_traffic_ports} to 1 one sided lossy traffic, "
                f"{num_lossy_packets} lossy packets, {num_lossless_packets} lossless packets, "
                f"reserved buffer size {reserved_buffer_size}"
            )
            allure.dynamic.title(test_id)
            allure.dynamic.description(description)

        self.traffic_jsons = get_many_to_1_traffic(self.conf_args, num_lossy_packets,
                                                   num_lossless_packets, num_of_traffic_ports)

        port_group_df = {
            MRCConsts.INGRESS_PORT_GROUP_NAME: self.conf_args[PerfConsts.PORT_GROUPS][PerfConsts.DUT_ALIAS][TRAFFIC_PORTS_GROUP_NAME_TEMPLATE.format(num_of_traffic_ports)][:1]
        }
        bw_threshold = self.get_drop_over_max_bw_threshold()
        with allure.step(f"Testing reserved buffer size {reserved_buffer_size}"):
            self.cli_object.performance.configure_reserved_buffer_size(reserved_buffer_size, port_group_df)
        with allure.step(f"Run traffic on all the ports:"):
            run_traffic(self.players, self.scenario, self.traffic_jsons)
        with allure.step(f"Verifying only counters"):
            counters_to_ignore = copy.deepcopy(PerfConsts.TOTAL_COUNTERS)
            counters_to_ignore.remove("port_rx_no_buffer")
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=bw_threshold,
                                      tc_occ_threshold=None,
                                      temperature_threshold=None,
                                      power_threshold=None,
                                      run_validate_no_drops_on_tg_ports=None,
                                      run_validate_counters=True,
                                      ignore_counter_list=counters_to_ignore)
            run_validation(config, add_validator_results_to_mongo_db=False)

    @allure.title('drop over max scenario')
    @allure.description('Lossy drop over max test scenario send 1 to 1 one sided traffic')
    @pytest.mark.skip("Skipping drop over max scenario, this test is only for manual calibration")
    def test_drop_over_max_scenario_callibration(self, request, scenario_name, test_config):
        """
        Drop over max test scenario send 1 to 1 one sided lossy traffic,
        it runs a binary search between reserved buffer for pg 0 defined range and
        finds the minimal reserved buffer for pg 0 size with no drops
        """
        results_df = []
        test_name = get_perf_test_name(request)
        num_lossy_packets = test_config.num_of_lossy_packets
        num_lossless_packets = test_config.num_of_lossless_packets
        num_of_traffic_ports = test_config.num_of_traffic_ports
        test_id = test_config.test_id

        with allure.step(f"Change test name and description"):
            description = (
                f"{test_id} calibration test. Drop over max test scenario send {num_of_traffic_ports} to 1 one sided lossy traffic, "
                f"{num_lossy_packets} lossy packets, {num_lossless_packets} lossless packets"
            )
            allure.dynamic.title(f"{test_id}_calibration")
            allure.dynamic.description(description)

        self.traffic_jsons = get_many_to_1_traffic(self.conf_args, num_lossy_packets,
                                                   num_lossless_packets, num_of_traffic_ports)

        port_group_df = {
            MRCConsts.INGRESS_PORT_GROUP_NAME: self.conf_args[PerfConsts.PORT_GROUPS][PerfConsts.DUT_ALIAS][TRAFFIC_PORTS_GROUP_NAME_TEMPLATE.format(num_of_traffic_ports)][:1]
        }
        bw_threshold = self.get_drop_over_max_bw_threshold()
        min_buffer_size = 1
        max_buffer_size = PerfConsts.MAX_CELLS_RANGE_FOR_BINARY_SEARCH
        min_no_drop_size = None

        counters_to_ignore = copy.deepcopy(PerfConsts.TOTAL_COUNTERS)
        counters_to_ignore.remove("port_rx_no_buffer")
        with allure.step(f"Starting binary search between {min_buffer_size} and {max_buffer_size}"):
            while min_buffer_size < max_buffer_size:
                mid_size = (min_buffer_size + max_buffer_size) // 2
                with allure.step(f"Testing reserved buffer for pg 0 size {mid_size} (binary search)"):
                    self.cli_object.performance.configure_shared_buffer_size(mid_size, port_group_df)
                    with allure.step(f"Run traffic on all the ports:"):
                        run_traffic(self.players, self.scenario, self.traffic_jsons)
                    with allure.step(f"Verifying only counters"):
                        config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                                  chip_type=self.chip_type,
                                                  bw_threshold=bw_threshold,
                                                  tc_occ_threshold=None,
                                                  temperature_threshold=None,
                                                  power_threshold=None,
                                                  run_validate_no_drops_on_tg_ports=None,
                                                  run_validate_counters=True,
                                                  ignore_counter_list=counters_to_ignore)
                        traffic_validation_jsons_list, violations_list = run_validation(config, ignore_violations=True, add_validator_results_to_mongo_db=False)
                        traffic_validation_json = traffic_validation_jsons_list.pop()
                        avg_ports_tx, avg_ports_rx = get_ports_avg_bw(traffic_validation_json, MRCConsts.INGRESS_PORT_GROUP_NAME)
                        were_there_drops = False
                        logger.info(f"avg ports tx: {avg_ports_tx}, avg ports rx: {avg_ports_rx}")
                        if not violations_list:
                            max_buffer_size = mid_size
                            min_no_drop_size = mid_size
                        else:
                            min_buffer_size = mid_size + 1
                            were_there_drops = True
                        results_df.append({
                            "reserved_buffer_for_pg_0_size": mid_size,
                            "were_there_drops": were_there_drops,
                            "avg_ports_rx": avg_ports_rx
                        })
                    with allure.step(f"Stop traffic"):
                        stop_traffic(self.players)
                    with allure.step(f"Configure mloops"):
                        configure_mloops(self.players)
        reserved_buffer_for_pg_0_size = min_no_drop_size if min_no_drop_size is not None else max_buffer_size

        with allure.step(f"Minimal reserved buffer for pg 0 size found {reserved_buffer_for_pg_0_size}, restore to max buffer size"):
            self.cli_object.performance.configure_reserved_buffer_size(max_buffer_size, port_group_df)
        with allure.step(f"Attach results_df"):
            allure.attach(pd.DataFrame(results_df).to_html(), "Results dataframe", attachment_type=allure.attachment_type.HTML)

    def get_drop_over_max_bw_threshold(self):
        bw_threshold = {
            MRCConsts.EGRESS_PORT_GROUP_NAME: {
                ValidationConsts.RX: None,
                ValidationConsts.TX: PerfConsts.DVS_SHAPER_VALUE
            },
            MRCConsts.INGRESS_PORT_GROUP_NAME: {
                ValidationConsts.TX: None,
                ValidationConsts.RX: PerfConsts.DVS_SHAPER_VALUE
            }
        }
        return bw_threshold

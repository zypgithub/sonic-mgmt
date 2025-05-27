import allure
import logging
import pytest

from ngts.constants.constants import CliType, InfraConst
from ngts.helpers.performance.performance_setup_helpers import (configure_mloops, restore_basic_configuration, apply_test_configuration,
                                                                run_traffic, run_validation, get_topology_obj,
                                                                skip_test_on_unsupported_os,
                                                                ValidationConfig, stop_traffic)
from ngts.helpers.performance.performance_db_helpers import add_test_mongo_metadata, get_perf_test_name
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, SPCXRAConsts
from ngts.performance_tests.alibaba_performance.conftest import get_alibaba_leaf_traffic
from ngts.performance_tests.alibaba_performance.alibaba_leaf_scenarios.conftest import TESTS_SCENARIO, TestParameters
from infra.tools.redmine.redmine_api import is_redmine_issue_active, get_issues_status


logger = logging.getLogger()


@pytest.mark.parametrize(
    "test_params",
    [
        TestParameters(0.975, 1900, True, 4, "shaper_97.5_pkt_size_1900_ar_enabled_split_4_host_ports"),
        TestParameters(0.999, 4096, True, 4, "shaper_99.9_pkt_size_4096_ar_enabled_split_4_host_ports"),
        TestParameters(0.975, 1900, False, 4, "shaper_97.5_pkt_size_1900_ar_disabled_split_4_host_ports"),
        TestParameters(0.975, 2000, False, 2, "shaper_97.5_pkt_size_2000_ar_disabled_split_2_host_ports"),
    ],
    indirect=True
)
class TestAlibabaLeafScenario:
    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, chip_type):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.cli_object = self.players['dut']['cli']
        self.scenario = TESTS_SCENARIO
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.chip_type = chip_type
        self.ip = InfraConst.IPV4
        self.is_ipv6 = False

    @allure.title('alibaba_performance_leaf_scenario. Added dynamically in test body')
    @allure.description('Added dynamically in test body')
    @pytest.mark.parametrize(
        "ip_combinations",
        [
            ("ipv4_enabled", "ipv6_disabled"),
            ("ipv4_disabled", "ipv6_enabled"),
            ("ipv4_enabled", "ipv6_enabled"),
        ]
    )
    def test_alibaba_performance_leaf_scenario(self, request, conf_args, ip_combinations):
        if ip_combinations == ("ipv4_enabled", "ipv6_disabled"):
            conf_args['packet_size'] = conf_args['packet_size'] + 100

        conf_args['is_ipv4'] = ip_combinations[0] == "ipv4_enabled"
        conf_args['is_ipv6'] = ip_combinations[1] == "ipv6_enabled"

        test_name = get_perf_test_name(request)

        with allure.step(f"Testing with IPv4={conf_args['is_ipv4']}, IPv6={conf_args['is_ipv6']}"):
            with allure.step("Adding dynamic description to allure report"):
                scenario_name = (f"Alibaba Performance real life leaf Scenario. "
                                 f"{32 * conf_args['split_left']} X {32 * conf_args['split_right']} ports. "
                                 f"shaper value: {conf_args['shaper_value']}. "
                                 f"packet size: {conf_args['packet_size']}. "
                                 f"{'with' if conf_args['is_ipv6'] else 'without'} IPv6. "
                                 f"{'with' if conf_args['is_ipv4'] else 'without'} IPv4. "
                                 f"{'with' if conf_args['ar_enabled'] else 'without'} AR. "
                                 )

                scenario_description = f"{scenario_name} "
                f"{'with' if conf_args['set_lpm_root'] else 'without'} LPM root. "
                f"{'with' if conf_args['disable_locality'] else 'without'} locality. "

                allure.dynamic.title(scenario_name)
                allure.dynamic.description(scenario_description)

            with allure.step(f"Get Alibaba traffic"):
                leaf_traffic_jsons = get_alibaba_leaf_traffic(self.players, conf_args)

            with allure.step(f"Run Traffic on all the ports"):
                run_traffic(self.players, self.scenario, leaf_traffic_jsons)

            with allure.step(f"Verifying the traffic"):
                expected_bw = {
                    "left_ports": {"tx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096], "rx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096]},
                    "right_ports": {"tx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096] / 2, "rx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096] / 2}
                }
                config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                          chip_type=self.chip_type,
                                          bw_threshold=expected_bw,
                                          power_threshold=self.power_thresholds_by_chip_type,
                                          skip_first_counters_iteration=True)
                run_validation(config)

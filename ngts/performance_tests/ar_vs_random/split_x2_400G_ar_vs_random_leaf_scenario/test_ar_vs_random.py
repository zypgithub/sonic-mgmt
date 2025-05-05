import allure
import logging
import pytest

from ngts.constants.constants import CliType, InfraConst
from ngts.helpers.performance.performance_setup_helpers import (restore_basic_configuration, apply_test_configuration,
                                                                run_traffic, run_validation, get_topology_obj,
                                                                skip_test_on_unsupported_os, set_allure_title,
                                                                ValidationConfig)
from ngts.helpers.performance.performance_db_helpers import add_test_mongo_metadata
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts, MongoDbConsts
from ngts.performance_tests.ar_vs_random.conftest import get_ar_vs_random_traffic
from infra.tools.redmine.redmine_api import is_redmine_issue_active, get_issues_status


logger = logging.getLogger()


class TestARvsRandom:
    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, chip_type):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.cli_object = self.players['dut']['cli']
        self.scenario = "ar_vs_random"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.chip_type = chip_type
        self.ip = InfraConst.IPV4
        self.is_ipv6 = False

    @pytest.mark.parametrize(
        "bisection_traffic, ecmp_type_ar, one_to_one_leaf_scenario",
        [
            (True, True, False),    # Bisection traffic with AR ECMP
            (True, False, False),   # Bisection traffic with Random ECMP
            (False, True, False),   # One sided traffic with AR ECMP
            (False, False, False),  # One sided traffic with Random ECMP
            (True, False, True),    # One-to-one leaf scenario with bisection
            (False, False, True),   # One-to-one leaf scenario without bisection
        ]
    )
    @allure.title('test_ar_vs_random_leaf. Added dynamically in test body')
    @allure.description('Added dynamically in test body')
    def test_ar_vs_random_leaf(self, request, bisection_traffic, ecmp_type_ar, one_to_one_leaf_scenario, conf_args):
        test_name = (
            f'test_ar_vs_random_leaf_'
            f'{"with" if bisection_traffic else "without"}_bisection_traffic_and_'
            f'{"AR" if ecmp_type_ar else "Random"}_ecmp_type'
        ) if not one_to_one_leaf_scenario else (
            f'SpcX_400G_to_400G_leaf_scenario_'
            f'{"with" if bisection_traffic else "without"}_bisection_traffic'
        )
        packet_size = PerfConsts.PACKET_SIZE_LIST[0]
        skip_first_counters_iteration = True

        with allure.step("Adding dynamic description to allure report"):
            allure.dynamic.title(test_name)
            allure.dynamic.description(
                f"Test AR vs Random leaf scenario with "
                f"{'with' if bisection_traffic else 'without'} bisection traffic and "
                f"{'AR' if ecmp_type_ar else 'Random'} ecmp type"
            ) if not one_to_one_leaf_scenario else (
                f"Test SpcX 400G to 400G leaf scenario with "
                f"{'with' if bisection_traffic else 'without'} bisection traffic"
            )

        with allure.step(f"Get AR vs Random traffic"):
            leaf_traffic_jsons = get_ar_vs_random_traffic(self.players, conf_args, bisection_traffic)

        with allure.step(
            f"Run Traffic on all the ports "
            f"{'with' if bisection_traffic else 'without'} bisection traffic"
        ):
            run_traffic(self.players, self.scenario, leaf_traffic_jsons)

        with allure.step(
            f"Verifying the traffic "
            f"{'with' if bisection_traffic else 'without'} bisection traffic, "
            f"and {'AR' if ecmp_type_ar else 'Random'} ecmp type"
        ):
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[packet_size],
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      skip_first_counters_iteration=skip_first_counters_iteration)

            run_validation(config)

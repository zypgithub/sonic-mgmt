import copy
from struct import pack
import allure
import logging
import pytest
import random
from ngts.helpers.performance.performance_setup_helpers import (ValidationConfig, apply_test_configuration, configure_mloops, create_acl_dump, restore_basic_configuration, run_traffic, run_validation,
                                                                get_topology_obj, set_allure_title)
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name
from ngts.constants.performance_constants import PerfConsts, SPCXRAConsts
from ngts.constants.constants import InfraConst
from ngts.performance_tests.spcx_ra.Alibaba_400G_AR_tests.conftest import AlibabaScenarioToconfiguration, get_alibaba_traffic, extract_acl_counters
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.performance_tests.spcx_ra.conftest import get_spcx_ra_spine_traffic
import re

logger = logging.getLogger()


SCENARIO_TO_PACKET_SIZE_DICT = {
    "p2_dut_no_acl": AlibabaScenarioToconfiguration(scenario_name="p2_dut_no_acl", packet_size=3200,
                                                    num_left_packets=12, num_right_packets=12, ecmp_type_stateless=True,
                                                    ecmp_size=4096, create_acls=False, create_goto_acl=False, two_sided_ar=True),

    "p3_leaf_no_acl": AlibabaScenarioToconfiguration(scenario_name="p3_leaf_no_acl_hash_crc", packet_size=1600,
                                                     num_left_packets=3, num_right_packets=20, ecmp_type_stateless=True,
                                                     ecmp_size=4096, create_acls=False, create_goto_acl=False, two_sided_ar=False),

    "p4_leaf_six_acl": AlibabaScenarioToconfiguration(scenario_name="p4_1_leaf_six_acl_hash_crc", packet_size=1600,
                                                      num_left_packets=3, num_right_packets=20, ecmp_type_stateless=False,
                                                      ecmp_size=512, create_acls=True, create_goto_acl=False, two_sided_ar=False),

    "p4_1_leaf_seven_acl": AlibabaScenarioToconfiguration(scenario_name="p4_2_leaf_seven_acl_hash_crc", packet_size=1500,
                                                          num_left_packets=3, num_right_packets=19, ecmp_type_stateless=False,
                                                          ecmp_size=512, create_acls=True, create_goto_acl=True, two_sided_ar=False),
}


SCENARIO_CONFIGURATIONS_NO_SHAPER = {
    "split_2_no_shaper": {
        "split_right": 2,
        "split_left": 2,
        "shaper_value": 1,
        "speed": 400000000,
        "left_num_packets": SPCXRAConsts.PACKET_NUM_400G_x2,
        "right_num_packets": SPCXRAConsts.PACKET_NUM_400G_x2
    },
    "split_4_no_shaper": {
        "split_right": 4,
        "split_left": 4,
        "shaper_value": 1,
        "speed": 200000000,
        "left_num_packets": int(SPCXRAConsts.PACKET_NUM_400G_x2 / 2),
        "right_num_packets": int(SPCXRAConsts.PACKET_NUM_400G_x2 / 2)
    }
}


class Test_Alibaba_scenarios_with_reset:
    @pytest.fixture(autouse=True)
    def setup(self, players, engines, power_thresholds_by_chip_type, conf_args, chip_type, is_ipv6):
        self.topology_obj = get_topology_obj(players)
        self.players = players
        self.engines = engines
        self.dut_engine = engines['dut']
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra"
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.ip = InfraConst.IPV6 if is_ipv6 else InfraConst.IPV4
        self.is_ipv6 = is_ipv6
        self.chip_type = chip_type
        self.conf_args = conf_args

    @pytest.mark.parametrize("scenario_name,scenario_configuration,rebalancer_enabled",
                             [(scenario_name, scenario_configuration, rebalancer_enabled)
                              for scenario_name, scenario_configuration in SCENARIO_CONFIGURATIONS_NO_SHAPER.items()
                              for rebalancer_enabled in [True, False]])
    @allure.title('test_Alibaba_100%_line_rate - {scenario_name} with rebalancer {rebalancer_enabled}')
    @allure.description('Added dynamically in test body')
    def test_alibaba_100_percent_line_rate(self, request, scenario_name, scenario_configuration, rebalancer_enabled):
        with allure.step(f"Set test correct allure title with {self.ip} parameter"):
            test_name = set_allure_title(request, self.is_ipv6)
            allure.dynamic.title(f"test_Alibaba_100%_line_rate - {scenario_name} with rebalancer {rebalancer_enabled}")
            allure.dynamic.description(f"Test Alibaba 100% line rate scenario {scenario_name} with rebalancer {rebalancer_enabled}")

        config_to_apply = None
        with allure.step("Apply custom configuration: Enable rebalancer - auto buffer mode is true"):
            restore_basic_configuration(players=self.players)
            config_to_apply = copy.deepcopy(self.conf_args)
            config_to_apply.update(scenario_configuration)
            config_to_apply.update({"auto_buffer_mode": rebalancer_enabled})

            apply_test_configuration(players=self.players, scenario=self.scenario, conf_args=config_to_apply)
            configure_mloops(players=self.players)

        with allure.step(f"Run Traffic on all the ports"):
            self.traffic_jsons = get_spcx_ra_spine_traffic(players=self.players, conf_args=config_to_apply)
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        with allure.step(f"Verifying the traffic"):
            bw_threshold = SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096] if rebalancer_enabled else SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[4096]
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=bw_threshold,
                                      tc_occ_threshold=PerfConsts.OCC_TH_DICT,
                                      power_threshold=self.power_thresholds_by_chip_type)
            run_validation(config)

    @pytest.mark.parametrize("scenario_name,scenario_configuration,packet_size,hash_type",
                             [(scenario_name, scenario_configuration, scenario_configuration.packet_size, hash_type)
                              for scenario_name, scenario_configuration in SCENARIO_TO_PACKET_SIZE_DICT.items()
                              for hash_type in ["crc", "random"]])
    @allure.title('test_Alibaba_scenario - {scenario_name} with {packet_size}B packets and {hash_type} hash')
    @allure.description('Added dynamically in test body')
    def test_alibaba_scenario(self, request, scenario_name, scenario_configuration, packet_size, hash_type, alibaba_scenarios_fixture):
        test_name = get_perf_test_name(request, False)

        with allure.step("Adding dynamic description to allure report"):
            allure.dynamic.description(f"Test Alibaba scenario {scenario_name} with packet size {packet_size}B and {hash_type} hash type. "
                                       f"ECMP type: {'stateless' if scenario_configuration.ecmp_type_stateless else 'stateful'}, "
                                       f"ECMP size: {scenario_configuration.ecmp_size}, "
                                       f"{'Create 6 ACLs' if scenario_configuration.create_acls else 'No ACLs'}, "
                                       f"{'Add goto ACL' if scenario_configuration.create_goto_acl else 'No goto ACL'}")
        with allure.step(f"Updating the configuration from the fixture"):
            self.conf_args = alibaba_scenarios_fixture
            self.traffic_jsons = get_alibaba_traffic(self.players, self.conf_args, spine_scenario=scenario_configuration.two_sided_ar)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports with hash type {hash_type}"):
            configure_mloops(self.players)
            run_traffic(self.players, self.scenario, self.traffic_jsons)

        with allure.step(f"Verifying the traffic for packet size {packet_size} with hash type {hash_type}"):
            if scenario_configuration.two_sided_ar:
                skip_first_counters_iteration = False
            else:
                skip_first_counters_iteration = True
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=SPCXRAConsts.DUT_TX_UTIL_AUTO_TH_DICT[PerfConsts.PACKET_SIZE_LIST[0]],
                                      tc_occ_threshold=PerfConsts.OCC_TH_DICT,
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      skip_first_counters_iteration=skip_first_counters_iteration)
            run_validation(config)

        if scenario_configuration.create_acls:
            with allure.step(f"Creating ACL dump"):
                acl_dump = create_acl_dump(self.players)
                logging.info(f"Creating ACL dump {acl_dump}")

            with allure.step(f"Extracting ACL counters"):
                acl_ar_counter, acl_goto_counter, goto_percentage = extract_acl_counters(acl_dump,
                                                                                         scenario_configuration.create_acls,
                                                                                         scenario_configuration.create_goto_acl)

                logging.info(f"ACL AR counter: {acl_ar_counter}")
                logging.info(f"ACL GOTO counter: {acl_goto_counter}")
            with allure.step(f"Verifying the ACL counters. ACL AR counter: {acl_ar_counter}, ACL GOTO counter: {acl_goto_counter} which are {goto_percentage:.3f}% of the total packets"):
                if scenario_configuration.create_acls and acl_ar_counter == 0:
                    raise Exception(f"AR ACL is not working as expected. {acl_ar_counter} is 0")
                if scenario_configuration.create_goto_acl and not (4.8 <= goto_percentage <= 5.2):
                    raise Exception(f"GOTO ACL is not working as expected. GOTO counter: {acl_goto_counter} is {goto_percentage:.3f}% of the total packets (expected 5 ± 0.2%)")

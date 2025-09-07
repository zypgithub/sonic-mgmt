import allure
import logging
import pytest

from ngts.constants.constants import InfraConst
from ngts.helpers.performance.performance_setup_helpers import (configure_mloops, run_traffic, run_validation, get_topology_obj, create_acl_dump,
                                                                ValidationConfig, stop_traffic)
from ngts.helpers.performance.performance_db_helpers import get_perf_test_name
from ngts.constants.performance_constants import SPCXRAConsts
from ngts.performance_tests.alibaba_performance.conftest import get_alibaba_leaf_traffic
from ngts.performance_tests.alibaba_performance.alibaba_leaf_scenarios.conftest import (TESTS_SCENARIO, TestIPCombinations, TestParameters,
                                                                                        TEST_ID_SHAPER_97_5_AR_ENABLED_SPLIT_4_64K_DIPS,
                                                                                        TEST_ID_SHAPER_99_9_AR_ENABLED_SPLIT_4_128_DIPS,
                                                                                        TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_4_64K_DIPS,
                                                                                        TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_2_64K_DIPS)
from ngts.constants.constants import BugHandlerConst
from infra.tools.redmine.redmine_api import is_redmine_issue_active, get_issues_status


@pytest.mark.parametrize(
    "test_params",
    [

        TestParameters(0.975, True, 4, 128, 60, TEST_ID_SHAPER_97_5_AR_ENABLED_SPLIT_4_64K_DIPS),
        TestParameters(0.999, True, 4, 128, 60, TEST_ID_SHAPER_99_9_AR_ENABLED_SPLIT_4_128_DIPS),
        TestParameters(0.975, False, 4, 64000, 64000, TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_4_64K_DIPS),
        TestParameters(0.975, False, 2, 64000, 64000, TEST_ID_SHAPER_97_5_AR_DISABLED_SPLIT_2_64K_DIPS)
    ],
    indirect=True
)
@pytest.mark.parametrize(
    "ip_combinations",
    [
        TestIPCombinations(ipv4_enabled="ipv4_enabled", ipv6_enabled="ipv6_disabled"),
        TestIPCombinations(ipv4_enabled="ipv4_disabled", ipv6_enabled="ipv6_enabled"),
        TestIPCombinations(ipv4_enabled="ipv4_enabled", ipv6_enabled="ipv6_enabled"),
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
    def test_alibaba_performance_leaf_scenario(self, request, conf_args, ip_combinations):
        logging.info(f"Testing with IPv4={conf_args['is_ipv4']}, IPv6={conf_args['is_ipv6']}")
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
                                 f"{conf_args['left_num_dip_to_send']} dips to host. "
                                 f"{conf_args['right_num_dip_to_send']} dips to spine. "
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

            with allure.step(f"Creating ACL dump"):
                acl_dump = create_acl_dump(self.players)
                logging.info(f"Creating ACL dump {acl_dump}")

            with allure.step(f"Publishing ACL dump"):
                if acl_dump:
                    allure.attach(acl_dump, name="ACL_Dump", attachment_type=allure.attachment_type.TEXT)

            with allure.step(f"Verifying the traffic"):
                expected_bw = {
                    "left_ports": {"tx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096], "rx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096]},
                    "right_ports": {"tx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096] / 2, "rx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096] / 2}
                }
                ignore_counter_list = ['tx_ecn_marked_tc_3']
                config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                          chip_type=self.chip_type,
                                          bw_threshold=expected_bw,
                                          power_threshold=self.power_thresholds_by_chip_type,
                                          skip_first_counters_iteration=True,
                                          ignore_counter_list=ignore_counter_list)
                run_validation(config)

    def _run_single_test_with_packet_size(self, packet_size, conf_args, test_name, create_acl_dump_flag=True):
        """
        Run a single test iteration with the specified packet size.

        Args:
            packet_size (int): The packet size to test
            conf_args (dict): Configuration arguments
            test_name (str): Test name for reporting
            create_acl_dump_flag (bool): Whether to create ACL dump for this iteration

        Returns:
            tuple: (bool, str or None) - (test_passed, acl_dump_content)
        """
        acl_dump_content = None
        try:
            # Update packet size in configuration
            modified_conf_args = conf_args.copy()
            modified_conf_args['packet_size'] = packet_size

            with allure.step(f"Testing packet size: {packet_size}"):
                with allure.step(f"Get Alibaba traffic with packet size {packet_size}"):
                    leaf_traffic_jsons = get_alibaba_leaf_traffic(self.players, modified_conf_args)

                with allure.step(f"Run Traffic on all the ports with packet size {packet_size}"):
                    run_traffic(self.players, self.scenario, leaf_traffic_jsons)

                if create_acl_dump_flag:
                    with allure.step(f"Creating ACL dump for packet size {packet_size}"):
                        acl_dump_content = create_acl_dump(self.players)
                        logging.info(f"Creating ACL dump {acl_dump_content}")

                with allure.step(f"Verifying the traffic with packet size {packet_size}"):
                    expected_bw = {
                        "left_ports": {"tx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096], "rx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096]},
                        "right_ports": {"tx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096] / 2, "rx": SPCXRAConsts.DUT_TX_UTIL_IBM_TH_DICT[4096] / 2}
                    }
                    ignore_counter_list = ['tx_ecn_marked_tc_3']
                    config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                              chip_type=self.chip_type,
                                              bw_threshold=expected_bw,
                                              power_threshold=self.power_thresholds_by_chip_type,
                                              skip_first_counters_iteration=True,
                                              ignore_counter_list=ignore_counter_list)
                    run_validation(config)

                    logger.info(f"Test PASSED with packet size: {packet_size}")
                    return True, acl_dump_content

        except Exception as e:
            logger.info(f"Test FAILED with packet size: {packet_size}, Error: {str(e)}")
            return False, acl_dump_content
        finally:
            # Stop traffic to clean up
            try:
                stop_traffic(self.players)
                configure_mloops(self.players)
            except Exception as cleanup_error:
                logger.warning(f"Failed to stop traffic during cleanup: {cleanup_error}")

    def _binary_search_min_packet_size(self, conf_args, test_name, min_size=1500, max_size=4200, step=100):
        """
        Perform binary search to find the minimum packet size where test passes.

        Args:
            conf_args (dict): Configuration arguments
            test_name (str): Test name for reporting
            min_size (int): Minimum packet size to test
            max_size (int): Maximum packet size to test
            step (int): Step size (must be multiple of this value)

        Returns:
            tuple: (int or None, str or None) - (minimum_packet_size, relevant_acl_dump_content)
        """
        # Generate list of valid packet sizes (multiples of step)
        packet_sizes = list(range(min_size, max_size + 1, step))
        acl_dumps = {}  # Dictionary to store ACL dumps by packet size

        with allure.step(f"Starting binary search for minimum packet size in range [{min_size}, {max_size}] with step {step}"):
            logger.info(f"Binary search packet sizes: {packet_sizes}")

            # First check if the maximum packet size passes
            test_passed, acl_dump_content = self._run_single_test_with_packet_size(max_size, conf_args, test_name)
            if acl_dump_content:
                acl_dumps[max_size] = acl_dump_content
            if not test_passed:
                # If max packet size fails, return None for min_passing_size and the max ACL dump
                logger.error(f"Maximum packet size {max_size} failed, cannot find minimum passing size")
                relevant_acl_dump = acl_dumps.get(max_size)
                return None, relevant_acl_dump

            # Binary search implementation
            left, right = 0, len(packet_sizes) - 1
            min_passing_size = None

            while left <= right:
                mid = (left + right) // 2
                current_packet_size = packet_sizes[mid]

                with allure.step(f"Binary search iteration: testing packet size {current_packet_size} (index {mid})"):
                    logger.info(f"Testing packet size: {current_packet_size} (left={left}, right={right}, mid={mid})")

                    test_passed, acl_dump_content = self._run_single_test_with_packet_size(current_packet_size, conf_args, test_name)
                    if acl_dump_content:
                        acl_dumps[current_packet_size] = acl_dump_content

                    if test_passed:
                        # Test passed, try smaller packet sizes
                        min_passing_size = current_packet_size
                        right = mid - 1
                        logger.info(f"Packet size {current_packet_size} PASSED, searching for smaller sizes")
                    else:
                        # Test failed, try larger packet sizes
                        left = mid + 1
                        logger.info(f"Packet size {current_packet_size} FAILED, searching for larger sizes")

            # Return the relevant ACL dump path
            final_packet_size = min_passing_size if min_passing_size is not None else max_size
            relevant_acl_dump = acl_dumps.get(final_packet_size)

            logger.info(f"Binary search completed. Final packet size: {final_packet_size}, ACL dumps collected: {list(acl_dumps.keys())}")

            return min_passing_size, relevant_acl_dump

    @pytest.mark.skip(reason="Helper test to get the min packet size for Ali scenarios.")
    @allure.title('alibaba_performance_leaf_scenario_binary_search. Added dynamically in test body')
    @allure.description('Binary search to find minimum packet size where test passes')
    def test_alibaba_performance_leaf_scenario_binary_search(self, request, conf_args, ip_combinations):
        test_name = get_perf_test_name(request)

        with allure.step(f"Testing with IPv4={conf_args['is_ipv4']}, IPv6={conf_args['is_ipv6']}"):
            with allure.step("Adding dynamic description to allure report"):
                scenario_name = (f"Alibaba Performance Binary Search Leaf Scenario. "
                                 f"{32 * conf_args['split_left']} X {32 * conf_args['split_right']} ports. "
                                 f"shaper value: {conf_args['shaper_value']}. "
                                 f"Binary search packet size range: [1500, 4200]. "
                                 f"{'with' if conf_args['is_ipv6'] else 'without'} IPv6. "
                                 f"{'with' if conf_args['is_ipv4'] else 'without'} IPv4. "
                                 f"{'with' if conf_args['ar_enabled'] else 'without'} AR. "
                                 f"{conf_args['left_num_dip_to_send']} dips to host. "
                                 f"{conf_args['right_num_dip_to_send']} dips to spine. "
                                 )

                scenario_description = f"{scenario_name} "
                f"{'with' if conf_args['set_lpm_root'] else 'without'} LPM root. "
                f"{'with' if conf_args['disable_locality'] else 'without'} locality. "

                allure.dynamic.title(scenario_name)
                allure.dynamic.description(scenario_description)

            # Perform binary search to find minimum packet size
            min_packet_size, acl_dump_content = self._binary_search_min_packet_size(conf_args, test_name)

            # Publish ACL dump if available (before any potential test failure)
            if acl_dump_content:
                with allure.step(f"Publishing ACL dump for packet size {min_packet_size or 4200}"):
                    allure.attach(acl_dump_content, name="Final_ACL_Dump", attachment_type=allure.attachment_type.TEXT)

            if min_packet_size is not None:
                with allure.step(f"Minimum passing packet size found: {min_packet_size}"):
                    logger.info(f"Binary search completed successfully. Minimum packet size: {min_packet_size}")
                    allure.attach(
                        str(min_packet_size),
                        name="Minimum Passing Packet Size",
                        attachment_type=allure.attachment_type.TEXT
                    )
            else:
                with allure.step("No passing packet size found in the tested range"):
                    logger.error("Binary search failed to find any passing packet size")
                    pytest.fail("No packet size in range [1500, 4200] resulted in a passing test")

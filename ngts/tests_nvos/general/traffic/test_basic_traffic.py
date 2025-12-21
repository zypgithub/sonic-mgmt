import logging
import pytest
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.Tools import Tools

logger = logging.getLogger()


@pytest.mark.general
@pytest.mark.skynet
def test_basic_ib_traffic(engines, devices, players, interfaces, start_sm, setup_name):
    """
    Basic IB traffic test with link error verification.

    Steps:
    1. Clear counters on traffic ports before test
    2. Capture baseline for PHY detail counters (cannot be cleared)
    3. Send IB traffic from HA to HB
    4. Send IB traffic from HB to HA
    5. Verify no link errors occurred on traffic ports
    6. Verify no PHY detail counter changes during traffic

    Uses device-specific error counters (devices.dut.traffic_error_counters)
    to support platform-specific validation.
    """
    with allure.step('Clear counters on traffic ports before test'):
        Tools.TrafficValidatorTool.clear_traffic_port_counters(engines.dut).verify_result()

    with allure.step('Capture PHY detail counter baseline'):
        baselines = Tools.TrafficValidatorTool.capture_baseline(engines.dut)

    with allure.step('Send from HA to HB'):
        Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, setup_name, True).verify_result()

    with allure.step('Send from HB to HA'):
        Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, setup_name, True, reverse_direction=True
                                                   ).verify_result()

    with allure.step('Verify no error of any kind occurred'):
        with allure.independent_step('Verify no link errors on traffic ports'):
            Tools.TrafficValidatorTool.verify_no_link_errors(engines.dut, devices.dut).verify_result()

        with allure.independent_step('Verify no PHY detail counter changes'):
            Tools.TrafficValidatorTool.compare_with_baseline(baselines, engines.dut).verify_result()


@pytest.mark.general
@pytest.mark.skynet
def test_basic_ipoib_traffic(engines, devices, players, interfaces, start_sm, setup_name):
    """
    Basic IPoIB traffic test with link error verification.

    Steps:
    1. Clear counters on traffic ports before test
    2. Capture baseline for PHY detail counters (cannot be cleared)
    3. Send IPoIB traffic from HA to HB
    4. Send IPoIB traffic from HB to HA
    5. Verify no link errors occurred on traffic ports
    6. Verify no PHY detail counter changes during traffic

    Uses device-specific error counters (devices.dut.traffic_error_counters)
    to support platform-specific validation.
    """
    with allure.step('Clear counters on traffic ports before test'):
        Tools.TrafficValidatorTool.clear_traffic_port_counters(engines.dut).verify_result()

    with allure.step('Capture PHY detail counter baseline'):
        baselines = Tools.TrafficValidatorTool.capture_baseline(engines.dut)

    with allure.step('Send from HA to HB'):
        Tools.TrafficGeneratorTool.send_ipoib_traffic(players, interfaces, True).verify_result()

    with allure.step('Send from HB to HA'):
        Tools.TrafficGeneratorTool.send_ipoib_traffic(players, interfaces, True, reverse_direction=True).verify_result()

    with allure.step('Verify no error of any kind occurred'):
        with allure.independent_step('Verify no link errors on traffic ports'):
            Tools.TrafficValidatorTool.verify_no_link_errors(engines.dut, devices.dut).verify_result()

        with allure.independent_step('Verify no PHY detail counter changes'):
            Tools.TrafficValidatorTool.compare_with_baseline(baselines, engines.dut).verify_result()

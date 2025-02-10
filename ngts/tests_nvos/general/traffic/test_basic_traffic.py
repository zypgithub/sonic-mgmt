import logging
import pytest
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.Tools import Tools

logger = logging.getLogger()


@pytest.mark.general
@pytest.mark.skynet
def test_basic_ib_traffic(players, interfaces, start_sm, setup_name):
    with allure.step('Send from HA to HB'):
        Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, setup_name, True).verify_result()
    with allure.step('Send from HB to HA'):
        Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, setup_name, True, reverse_direction=True
                                                   ).verify_result()


@pytest.mark.general
@pytest.mark.skynet
def test_basic_ipoib_traffic(players, interfaces, start_sm, setup_name):
    with allure.step('Send from HA to HB'):
        Tools.TrafficGeneratorTool.send_ipoib_traffic(players, interfaces, True).verify_result()
    with allure.step('Send from HB to HA'):
        Tools.TrafficGeneratorTool.send_ipoib_traffic(players, interfaces, True, reverse_direction=True).verify_result()

import logging
import pytest
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.Tools import Tools
from infra.tools.redmine.redmine_api import is_redmine_issue_active

logger = logging.getLogger()


@pytest.mark.general
@pytest.mark.skynet
def test_basic_traffic(players, interfaces, start_sm):
    """
    Basic traffic test
    """
    with allure.step("Validate ib traffic"):
        Tools.TrafficGeneratorTool.send_ib_traffic(players, interfaces, True).verify_result()

    with allure.step("Validate ipoib traffic"):
        Tools.TrafficGeneratorTool.send_ipoib_traffic(players, interfaces, True).verify_result()

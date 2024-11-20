import allure
import logging
import pytest

from ngts.helpers.performance.performance_setup_helpers import (run_traffic,
                                                                validate_traffic_results)
logger = logging.getLogger()


class TestSPCXRA:

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, players, engines):
        self.topology_obj = topology_obj
        self.players = players
        self.engines = engines
        self.cli_object = self.players['dut']['cli']
        self.scenario = "spcx_ra"

    @allure.title('spcx_ra')
    def test_spcx_ra(self):
        """
        This test will SPCX_RA
        :return: raise assertion error if output is not there.
        """
        run_traffic(self.players, self.scenario)
        validate_traffic_results(self.players, self.scenario)

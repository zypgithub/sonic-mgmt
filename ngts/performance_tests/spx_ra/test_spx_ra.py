import allure
import logging
import pytest
from infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker


"""

Nos agnostic test case for SONIC CL and DVS to configure IP interface using a static configuration file
The static configuration file can be found under :-
sonic-mgmt/ngts/performance_config_templates

"""

logger = logging.getLogger()


class TestIP:

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, players):
        self.topology_obj = topology_obj
        self.players = players
        self.cli_object = self.players['dut']['cli']

    @allure.title('Test ip interface show')
    def test_ip_of_interface(self):
        """
        This test will show ip address.
        :return: raise assertion error if output is not there.
        """
        logger.info("Checking for ip interface output.")
        output = self.cli_object.ip.show_ip_interfaces()
        logger.info(f"Send ping from DUT to RIGHT_TG")
        ping_dut_args = {
            'sender': 'dut',
            'args': {
                'count': 5,
                'dst': '13.48.0.2'
            }
        }
        PingChecker(self.players, ping_dut_args).run_validation()

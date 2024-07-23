import pytest
import logging
import re
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.common.helpers.assertions import pytest_assert
from tests.common.config_reload import config_reload
from tests.common.utilities import wait_until
from tests.common.platform.interface_utils import get_dpu_npu_ports_from_hwsku

IP_ADDRESS_LIST = {"ACS-SN4280": ["169.254.200.1", "169.254.200.2", "169.254.200.3", "169.254.200.4"],
                   "Mellanox-SN4280-O28": ["169.254.200.1", "169.254.200.2", "169.254.200.3", "169.254.200.4"]}

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('t1'),
    pytest.mark.skip_check_dut_health
]


@pytest.fixture(scope="module", autouse=True)
def skip_non_smartswitch_testbed(duthost, tbinfo):
    hwsku = duthost.facts["hwsku"]
    if hwsku not in IP_ADDRESS_LIST.keys():
        pytest.skip("This test is only for smart switch")


@pytest.fixture(autouse=True)
def apply_ip_assignment_config(duthost):
    # Apply the ip assignment config if it was not applied in deployment
    config_applied_by_test = False
    config_facts = duthost.get_running_config_facts()
    if config_facts['DEVICE_METADATA']['localhost'].get('subtype') != 'SmartSwitch':
        with allure.step('Apply DPU IP assignment configuration'):
            duthost.copy(src='smart_switch/dpu_ip_assignment_config.json',
                         dest='/tmp/dpu_ip_assignment_config.json')
            duthost.shell('sudo sonic-cfggen -j /tmp/dpu_ip_assignment_config.json --write-to-db')
            duthost.shell('sudo config save -y')
            config_applied_by_test = True
            config_reload(duthost, safe_reload=True)

    yield

    if config_applied_by_test:
        with allure.step('Restore the config via loading minigraph'):
            config_reload(duthost, config_source='minigraph', safe_reload=True, check_intf_up_ports=True)


def test_dpu_ip_assignment(duthost, creds):
    hwsku = duthost.facts["hwsku"]
    internal_port_list = get_dpu_npu_ports_from_hwsku(duthost)
    ip_addresses = IP_ADDRESS_LIST.get(hwsku, IP_ADDRESS_LIST["ACS-SN4280"])

    with allure.step("Check the DHCP server status"):
        output = duthost.shell("show dhcp_server ipv4 info")['stdout']
        pattern = r"bridge-midplane.*PORT.*169\.254\.200\.254.*enabled"
        pytest_assert(re.search(pattern, output), "The DHCP server info is not correct.")

    with allure.step("Check the DHCP lease status"):
        def _check_dhcp_lease():
            duthost.shell("show dhcp_server ipv4 info")
            output = duthost.shell("show dhcp_server ipv4 lease")['stdout']
            for address in ip_addresses:
                if not re.search(address, output):
                    return False
            return True
        pytest_assert(wait_until(600, 5, 0, _check_dhcp_lease),
                      "There is no lease for all internal ports, "
                      "please check the test log.")

    for address in ip_addresses:
        with allure.step(f"Ping the dpu IP address {address}"):
            duthost.shell(f"ping -c 5 {address}")

    with allure.step("Check the switch internal port status are up"):
        pytest_assert(duthost.links_status_up(internal_port_list), "Not all internal ports are up")

    with allure.step("Check the DPU Ethernet0 port status are up"):
        duthost.copy(src='smart_switch/get_dpu_interface_status.py',
                     dest='/tmp/get_dpu_interface_status.py')
        duthost.shell("python3 /tmp/get_dpu_interface_status.py")
        pattern = r"Ethernet0.*up.*up"
        for address in ip_addresses:
            output = duthost.shell(f"cat /tmp/interface_status_output_{address}")['stdout']
            pytest_assert(re.search(pattern, output), f"The Ethernet0 port of dpu {address} is not up.")


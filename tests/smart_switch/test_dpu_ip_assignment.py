import pytest
import logging
import re
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until
from tests.common.platform.interface_utils import get_dpu_npu_ports_from_hwsku

IP_ADDRESS_LIST = {"ACS-SN4280": ["169.254.200.1", "169.254.200.2", "169.254.200.3", "169.254.200.4"],
                   "Mellanox-SN4280-O28": ["169.254.200.1", "169.254.200.2", "169.254.200.3", "169.254.200.4"],
                   "Mellanox-SN4280-O8C40": ["169.254.200.1", "169.254.200.2", "169.254.200.3", "169.254.200.4"]}

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.skip_check_dut_health,
    pytest.mark.usefixtures('copy_proxy_ssh')
]


@pytest.fixture(scope="module", autouse=True)
def skip_non_smartswitch_testbed(duthost, tbinfo):
    hwsku = duthost.facts["hwsku"]
    if hwsku not in IP_ADDRESS_LIST.keys():
        pytest.skip("This test is only for smart switch")


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
        # This is a WA only for the BU bobcat setups due the not fully customized DPUs
        if duthost.hostname in ['r-bobcat-01', 'r-bobcat-03']:
            for dpu_mgmt_ip in IP_ADDRESS_LIST['Mellanox-SN4280-O28']:
                cmd = "cat /sys/class/net/eth0/address"
                mac = duthost.shell(f'sudo proxy_ssh.py --dpu-mgmt-ip {dpu_mgmt_ip} --cmd "{cmd}"')['stdout']
                cmd = f"redis-cli -n 4 hset 'DEVICE_METADATA|localhost' mac {mac}"
                duthost.shell(f'sudo proxy_ssh.py --dpu-mgmt-ip {dpu_mgmt_ip} --cmd "{cmd}"')
                duthost.shell(f'sudo proxy_ssh.py --dpu-mgmt-ip {dpu_mgmt_ip} --cmd "sudo config save -y"')
                duthost.shell(f'sudo proxy_ssh.py --dpu-mgmt-ip {dpu_mgmt_ip} --cmd "sudo config reload -y" --async')

            def _check_containers_up(dpu_ip):
                containers = ["snmp", "pmon", "lldp", "gnmi", "bgp", "swss", "syncd", "eventd"]
                docker_status = duthost.shell(
                    f'sudo proxy_ssh.py --dpu-mgmt-ip {dpu_ip} --cmd "docker ps"', module_ignore_errors=True)['stdout']
                for container in containers:
                    pattern = f"Up.*{container}"
                    if not re.search(pattern, docker_status):
                        return False
                return True

            for dpu_mgmt_ip in IP_ADDRESS_LIST['Mellanox-SN4280-O28']:
                pytest_assert(wait_until(120, 20, 0, _check_containers_up, dpu_mgmt_ip),
                              f"Not all containers are up after config reload in DPU {dpu_mgmt_ip}")
        # Remove the WA above when we stop using the BU bobcat setups

        pattern = r"Ethernet0.*up.*up"
        cmd = "show interface status Ethernet0"
        for address in ip_addresses:
            output = duthost.shell(f'sudo proxy_ssh.py --dpu-mgmt-ip {address} --cmd "{cmd}"')['stdout']
            pytest_assert(re.search(pattern, output), f"The Ethernet0 port of dpu {address} is not up.")

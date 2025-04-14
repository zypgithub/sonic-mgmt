import logging
import pytest
import random
import ptf.testutils as testutils
import ptf.packet as scapy
import datetime
import types
import re
import time
import sys
import os

from ptf.mask import Mask
from tests.common.config_reload import config_reload
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.common.helpers.assertions import pytest_assert
from tests.common.constants import RESOLV_CONF_NAMESERVERS
from tests.common.utilities import wait_until
current_path = sys.path.copy()
sys.path.insert(0, "dash")
from tests.dash.conftest import add_dpu_info
sys.path = current_path

logger = logging.getLogger(__name__)

DPDK_CONTAINER_NAME = "dpdk-app-container"
DPDK_APP = "nbu-harbor.gtm.nvidia.com/sonic/dpdk-app:latest"
SWITCH_DATA_PORT = {'x86_64-nvidia_sn4280-r0': 'Ethernet64'}
ptf_port_index = 0

pytestmark = [
    pytest.mark.topology('any'),
]

if not RESOLV_CONF_NAMESERVERS['public']:
    RESOLV_CONF_NAMESERVERS['public'] = ["10.211.0.124", "10.245.1.121", "10.7.77.135"]

@pytest.fixture(scope="module", params=["pull", "image", "file"])
def option(request):
    return request.param


def check_byo_status(status, dpuhost):
    dockers_up = {"enabled": ["byo-app-container", "database"],
                  "disabled": ["snmp", "pmon", "lldp", "gnmi", "bgp", "swss", "syncd", "eventd", "database"]}
    dockers_down = {"enabled": ["snmp", "pmon", "lldp", "gnmi", "bgp", "swss", "syncd", "eventd"],
                    "disabled": ["byo-app-container"]}
    output = dpuhost.shell("docker ps")['stdout']
    for docker in dockers_down[status]:
        if re.search(f"Up.*{docker}", output):
            logger.warning(f"The docker {docker} is not expected to be up while the BYO status is {status}")
            return False
    for docker in dockers_up[status]:
        if not re.search(f"Up.*{docker}", output):
            logger.warning(f"The docker {docker} is expected to be up while the BYO status is {status}")
            return False
    return True


@pytest.fixture(scope="module", autouse=True)
def setup(duthost, tbinfo, dpuhost, platform, enable_dpu_mgmt_forwarding):
    global ptf_port_index
    # Enable the dpu mgmt forwarding
    with allure.step("Config vlan for the smartswitch dataplane"):
        # Config vlan for the smartswitch dataplane
        mg_facts = duthost.get_extended_minigraph_facts(tbinfo)
        switch_data_port = SWITCH_DATA_PORT[platform]
        for ip_interface in mg_facts['minigraph_interfaces']:
            if ip_interface['attachto'] == switch_data_port:
                duthost.shell(f"config interface ip remove {ip_interface['attachto']} "
                              f"{ip_interface['addr']}/{ip_interface['mask']}")
        duthost.shell('config vlan add 1000')
        duthost.shell(f'config vlan member add 1000 {switch_data_port} --untagged')
        dpu_data_port = dpuhost.data_port_on_npu
        duthost.shell(f'config vlan member add 1000 {dpu_data_port} --untagged')
        ptf_port_index = mg_facts['minigraph_ptf_indices'][switch_data_port]
    with allure.step("Align the DPU time"):
        # The time on DPU need to be synced for accessing the docker registry
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dpuhost.shell(f"sudo date -s \'{current_time}\'")
    with allure.step("Config dns nameserver for DPU"):
        for nameserver in RESOLV_CONF_NAMESERVERS['public']:
            dpuhost.shell(f"sudo config dns nameserver add {nameserver}", module_ignore_errors=True)

    with allure.step("Shutdown bgp to enable the access to the docker registry"):
        duthost.shell("config bgp shutdown all")

    yield

    with allure.step("Start bgp"):
        duthost.shell("config bgp startup all")
    with allure.step("Disable byo on the dpu"):
        dpuhost.shell(f"sudo sonic-byo.py disable")
        pytest_assert(check_byo_status('disabled', dpuhost), "Failed to disable BYO on DPU.")
    with allure.step("Reload switch config"):
        config_reload(duthost, safe_reload=True)


@pytest.fixture(scope="function", autouse=True)
def disable_byo(dpuhost):

    yield

    with allure.step("Disable BYO"):
        dpuhost.shell(f"sudo sonic-byo.py disable")
        pytest_assert(check_byo_status('disabled', dpuhost), "Failed to disable BYO on DPU.")


def get_docker_image_id(docker, dpuhost):
    try:
        image_id = re.search(r' \w{12} ', dpuhost.shell(f"docker image ls {docker}")['stdout']).group().strip()
    except AttributeError:
        return False
    return image_id


@pytest.mark.disable_loganalyzer
def test_byo(ptfadapter, dpuhost, option):
    """
    Initiate the byo flow on a dpu and verify the demo provided by the DPDK app.
    A packet whose dst mac matches the data port’s mac is forwarded by the dpu.
    When forwarded, the src mac of the packet will be the port’s mac, and the dst mac is 02:00:00:00:00:00
    """
    byo_check_timeout = 30
    docker_pull_timeout = 1200

    if option != "pull":
        with allure.step(f"Pull the dpdk-app image: {DPDK_APP}"):
            dpuhost.shell(f"docker pull {DPDK_APP}", module_async=True)
            pull_success = wait_until(docker_pull_timeout, 30, 0, get_docker_image_id, DPDK_APP, dpuhost)
            pytest_assert(pull_success, f"Failed to pull the docker image: {DPDK_APP}")
            image_id = get_docker_image_id(DPDK_APP, dpuhost)

    if option == "pull":
        with allure.step('Enable BYO on the DPU with the "pull" option'):
            # The docker pull may take very long time, so run the command in async mode to avoid ssh timeout
            dpuhost.shell(f"sudo sonic-byo.py enable --pull {DPDK_APP}", module_async=True)
            byo_check_timeout = docker_pull_timeout
    elif option == "file":
        with allure.step('Save the dpdk-app image to a file since the test option is "file"'):
            dpuhost.shell(f"sudo docker save {image_id} -o /tmp/dpdk-app.gz")
        with allure.step('Remove the image'):
            dpuhost.shell(f"sudo docker image rm -f {image_id}")
        with allure.step('Enable BYO on the DPU with the "file" option'):
            dpuhost.shell(f"sudo sonic-byo.py enable --file /tmp/dpdk-app.gz")
    elif option == "image":
        with allure.step('Enable BYO on the DPU with the "image" option'):
            dpuhost.shell(f"sudo sonic-byo.py enable --image {image_id}")

    with allure.step("Check the BYO is successfully enabled"):
        pytest_assert(wait_until(byo_check_timeout, 20, 0, check_byo_status, "enabled", dpuhost),
                      "Failed to enable BYO.")

    # 5 seconds delay for the DPDK configuration to take effect
    time.sleep(5)

    with allure.step("Send a packet with DPU data port mac address as the dst mac address,"
                     " and check it is forwarded by the DPU"):
        data_port_mac_address = dpuhost.shell("cat /sys/class/net/Ethernet0/address")['stdout']
        pytest_assert(data_port_mac_address, "Failed to get the DPU data port mac address")

        packet = testutils.simple_tcp_packet(
            eth_src="00:00:00:00:00:01",
            eth_dst=data_port_mac_address,
            ip_src="1.1.1.1",
            ip_dst="2.2.2.2",
            tcp_sport=0x1234,
            tcp_dport=0x4321
        )
        expected_packet = testutils.simple_tcp_packet(
                eth_src=data_port_mac_address,
                eth_dst="02:00:00:00:00:00",
                ip_src="1.1.1.1",
                ip_dst="2.2.2.2",
                tcp_sport=0x1234,
                tcp_dport=0x4321
        )
        testutils.send(ptfadapter, ptf_port_index, packet, 1)
        testutils.verify_packet(ptfadapter, expected_packet, ptf_port_index)

    with allure.step("Send a packet with a dummy address as the dst mac address, and check it is dropped the DPU"):
        packet = testutils.simple_tcp_packet(
            eth_src="00:00:00:00:00:01",
            eth_dst="00:00:00:00:00:02",
            ip_src="1.1.1.1",
            ip_dst="2.2.2.2",
            tcp_sport=0x1234,
            tcp_dport=0x4321
        )
        expected_packet = Mask(packet)
        expected_packet.set_do_not_care_packet(scapy.Ether, "src")
        expected_packet.set_do_not_care_packet(scapy.Ether, "dst")
        testutils.send(ptfadapter, ptf_port_index, packet, 1)
        testutils.verify_no_packet(ptfadapter, expected_packet, ptf_port_index)

import logging
import pytest
import os

from tests.smart_switch.dpuhost import DpuHost
from ipaddress import ip_address
from tests.common.platform.interface_utils import get_dpu_npu_ports_from_hwsku

logger = logging.getLogger(__name__)
SMARTSWITCH_PLATFORMS = ['x86_64-nvidia_sn4280-r0']
DPU_INFO = {
    'x86_64-nvidia_sn4280-r0': {
        "dpu0": {"mgmt_ip": "169.254.200.1", "data_port": "Ethernet224"},
        "dpu1": {"mgmt_ip": "169.254.200.2", "data_port": "Ethernet232"},
        "dpu2": {"mgmt_ip": "169.254.200.3", "data_port": "Ethernet240"},
        "dpu3": {"mgmt_ip": "169.254.200.4", "data_port": "Ethernet248"}
    }
}


@pytest.fixture(scope="session")
def enable_dpu_mgmt_forwarding(duthost):
    # Enable the dpu mgmt forwarding if the dut is smartswitch
    duthost.shell('sudo sonic-dpu-mgmt-traffic.sh -e')

    yield

    duthost.shell('sudo sonic-dpu-mgmt-traffic.sh -d')


@pytest.fixture(scope="session", autouse=True)
def platform(duthost):
    return duthost.facts["platform"]


@pytest.fixture(scope="session")
def skip_unsupported_platform(duthost, platform):
    if platform not in SMARTSWITCH_PLATFORMS and 'nvda_bf' not in platform:
        pytest.skip("BYO is only supported on DPU or smartswitch platforms")


@pytest.fixture(scope="session")
def copy_proxy_ssh(duthost, platform):
    user = os.getenv('SONIC_SWITCH_USER')
    password = os.getenv('SONIC_SWITCH_PASSWORD')
    duthost.shell(f'echo {user} >> SONIC_USER')
    duthost.shell(f'echo {password} >> SONIC_PASSWORD')
    result = duthost.shell('ls /usr/local/bin/proxy_ssh.py', module_ignore_errors=True)
    if result['rc'] == 2:
        duthost.copy(src='smart_switch/proxy_ssh.py',
                     dest='/usr/local/bin/proxy_ssh.py')
        duthost.shell("sudo chmod 777 /usr/local/bin/proxy_ssh.py")
        logger.info("The proxy_ssh.py is copied to /usr/local/bin/proxy_ssh.py")


@pytest.fixture(scope="session", autouse=True)
def dpuhosts(duthost, copy_proxy_ssh):
    dpuhosts = []
    base_ip = ip_address("169.254.200.1")
    data_port_base_ip = ip_address("10.0.0.74")
    dpu_npu_port_list = sorted(get_dpu_npu_ports_from_hwsku(duthost))
    for index, port in enumerate(dpu_npu_port_list):
        npu_data_port_ip = str(data_port_base_ip + index * 2)
        dpu_data_port_ip = str(ip_address(npu_data_port_ip) + 1)
        dpu_info = {
            "name": f"dpu{index}",
            "mgmt_ip": str(base_ip + index),
            "data_port": port,
            "npu_data_port_ip": npu_data_port_ip,
            "dpu_data_port_ip": dpu_data_port_ip,
            "dataplane_mask_length": 31
        }
        dpuhosts.append(DpuHost(duthost, **dpu_info))
    return dpuhosts


def dpu_shell(dpu_mgmt_ip):
    def _dpu_shell(self, cmd, module_ignore_errors=False, module_async=False):
        command = f'sudo proxy_ssh.py --dpu-mgmt-ip {dpu_mgmt_ip} --cmd "{cmd}"'
        if not module_ignore_errors:
            command += ' --validate'
        if module_async:
            command += ' --async'
        return self.shell(command)
    return _dpu_shell

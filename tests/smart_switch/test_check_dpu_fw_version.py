import logging
import pytest
import re

from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.common.helpers.assertions import pytest_assert
from tests.smart_switch.conftest import DPU_INFO

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.usefixtures('skip_unsupported_platform', 'copy_proxy_ssh'),
    pytest.mark.skip_check_dut_health
]

logger = logging.getLogger(__name__)


def test_check_dpu_fw_version(duthost, platform, localhost):
    with allure.step("Get the expected fw version"):
        dpu0_mgmt_ip = DPU_INFO[platform]['dpu0']['mgmt_ip']
        show_version_cmd = 'show ver | grep "Software Version"'
        sonic_version_output = \
            duthost.shell(f"sudo proxy_ssh.py --dpu-mgmt-ip {dpu0_mgmt_ip} --cmd '{show_version_cmd}'")['stdout']
        sonic_image_hash = re.search(r'[a-z0-9]{9,}$', sonic_version_output).group()
        nfs_path = "/auto/sw_system_release/sonic/sonic_dpu"
        image_path = localhost.shell(f"ls {nfs_path} | grep {sonic_image_hash}")['stdout']
        readme_path = nfs_path + '/' + image_path + '/dev/README'
        fw_version_output = localhost.shell(f"cat {readme_path} | grep FW_VERSION")['stdout']
        fw_version_pattern = r'\d{2}\.\d{2}\.\d{4}'
        expected_fw_version = re.search(fw_version_pattern, fw_version_output).group()
    with allure.step("Check fw versions of all the DPUs"):
        cmd = f'sudo mlxfwmanager | grep FW'
        for dpu in DPU_INFO[platform]:
            fw_version_output = duthost.shell(f"sudo proxy_ssh.py --dpu-mgmt-ip {DPU_INFO[platform][dpu]['mgmt_ip']} --cmd '{cmd}'")['stdout']
            fw_version = re.search(fw_version_pattern, fw_version_output).group()
            pytest_assert(fw_version == expected_fw_version,
                          f"The fw version of {dpu}: {fw_version} is not as expected: {expected_fw_version}")

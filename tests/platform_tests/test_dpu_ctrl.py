import pytest
import logging
import random
import json
from tests.common.helpers.assertions import pytest_assert
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from tests.common.utilities import wait_until
from tests.common.reboot import reboot

logger = logging.getLogger()

pytestmark = [
    pytest.mark.topology('t1')
]

DPU_LIST = ["dpu0", "dpu1", "dpu2", "dpu3"]
SKU_SUPPORT_DPU_CTL_LIST = ["Mellanox-SN4280-O28"]

DPU_PIC_ID_RISHIM_MAP = {
    "dpu0": {"pci_id": "0000:08:00.0", "rshim": "rshim@0"},
    "dpu1": {"pci_id": "0000:07:00.0", "rshim": "rshim@1"},
    "dpu2": {"pci_id": "0000:01:00.0", "rshim": "rshim@2"},
    "dpu3": {"pci_id": "0000:02:00.0", "rshim": "rshim@3"},
}


@pytest.fixture(scope="module", autouse=True)
def skip_sku_not_support_dpu_ctl(duthosts, rand_one_dut_hostname):
    duthost = duthosts[rand_one_dut_hostname]
    dut_hwsku = duthost.facts["hwsku"]

    if dut_hwsku not in SKU_SUPPORT_DPU_CTL_LIST:
        pytest.skip(f"Skip the test due to {dut_hwsku} not support dpu ctl")


@pytest.fixture(scope="module", autouse=True)
def recover_dpu(duthosts, rand_one_dut_hostname, skip_sku_not_support_dpu_ctl):
    duthost = duthosts[rand_one_dut_hostname]

    yield

    if not all_dpu_up(duthost):
        duthost.shell("sudo dpuctl dpu-power-on --all --force")


@pytest.fixture(scope="module", autouse=True)
def dpu_bridge_midplane_ip_map(duthost):
    cmd_dump_config_db = "sonic-db-dump -n CONFIG_DB -y"
    config_db_res = json.loads(duthost.shell(cmd_dump_config_db)["stdout"])
    dpu_bridge_midplane_ip_map = {}
    for dpu in DPU_LIST:
        dpu_bridge_midplane_ip_map[dpu] = \
            config_db_res[f"DHCP_SERVER_IPV4_PORT|bridge-midplane|{dpu}"].get('value').get('ips@')
    logger.info(f"dpu bridge midplane ips map is:{dpu_bridge_midplane_ip_map}")
    yield dpu_bridge_midplane_ip_map


def test_dpu_power_off_and_on(duthosts, localhost, dpu_npu_port_list, rand_one_dut_hostname, dpu_bridge_midplane_ip_map):
    """
    This test case is to verify dpu power off and on
    1. Select several dpus or all to power off
    2. Check dpus are down
    3. Check the corresponding dpu npu port is down,
    4. Check the corresponding PCI links are removed by checking the output of "lspci -D | grep Blue"
    5. Check the corresponding bridge-midplane are removed by checking the output of "ip link | grep "dpu""
    6. reboot switch randomly( None(skip reboot), cold, soft)
    7, repeat step 9 ~ step 12
    8. Power on the selected dpus
    9. Check dpus are up
    10. Check the corresponding dpu npu port is up and the dpu ip can be pingable
    11. Check the corresponding PCI link are back by checking the output of "lspci -D | grep Blue"
        Check ID for each dpu should keep same as previous one
    12. Check the corresponding bridge-midplane are back by checking the output of "ip link | grep "dpu"",
        check bridge-midplane for each dpu should keep same as previous one
    13. reboot switch randomly( None(skip reboot), cold, soft)
    14. repeat step 9 ~ step 12
    """
    duthost = duthosts[rand_one_dut_hostname]
    dpu_num = random.choice(["random", "all"])
    force_option = random.choice([False, True])
    test_dpu_list, test_dpu_npu_port_list, dpu_list_arg = get_test_dpu_and_port(
        dpu_num, dpu_npu_port_list, rand_one_dut_hostname)

    force_option_arg = " --force" if force_option else ""

    with allure.step(f"Power off {dpu_list_arg} {force_option_arg}"):
        cmd_dpu_power_off = f"sudo dpuctl dpu-power-off {dpu_list_arg} {force_option_arg}"
        duthost.shell(cmd_dpu_power_off)["stdout"]
        do_verification_after_power_off_dpu(duthost, test_dpu_list, test_dpu_npu_port_list, dpu_bridge_midplane_ip_map)

    reboot_type = random.choice(["None", "cold"])
    if reboot_type != "None":
        with allure.step(f"dut {reboot_type} reboot  after power off dpu"):
            logger.info("Do {} reboot".format(reboot_type))
            reboot(duthost, localhost, reboot_type=reboot_type, reboot_helper=None, reboot_kwargs=None)
            do_verification_after_power_on_dpu(duthost, test_dpu_list, test_dpu_npu_port_list,
                                                dpu_bridge_midplane_ip_map)

    with allure.step(f"Power on {dpu_list_arg} {force_option_arg}"):
        cmd_dpu_power_on = f"sudo dpuctl dpu-power-on {dpu_list_arg} {force_option_arg}"
        duthost.shell(cmd_dpu_power_on)["stdout"]
        do_verification_after_power_on_dpu(duthost, test_dpu_list, test_dpu_npu_port_list, dpu_bridge_midplane_ip_map)

    reboot_type = random.choice(["None", "cold"])
    if reboot_type != "None":
        with allure.step(f"dut {reboot_type} reboot after power on dpu"):
            logger.info("Do {} reboot".format(reboot_type))
            reboot(duthost, localhost, reboot_type=reboot_type, reboot_helper=None, reboot_kwargs=None)
            do_verification_after_power_on_dpu(duthost, test_dpu_list, test_dpu_npu_port_list,
                                               dpu_bridge_midplane_ip_map)


def test_dpu_dpu_reset(duthosts, dpu_npu_port_list, rand_one_dut_hostname, dpu_bridge_midplane_ip_map):
    """
    This test case is to verify the behavior of switch and dpu after dpu reset
    1. Get all info for all PCI links and bridge-midplane
    2. Dpu reset
    3. Check dpus are up
    4. Check the corresponding dpu npu port is up and the dpu ip can be pingable
    5. Check the info for PCI links and bridge-midplane are same as previous one
    """
    duthost = duthosts[rand_one_dut_hostname]
    dpu_num = random.choice(["random", "all"])
    test_dpu_list, test_dpu_npu_port_list, dpu_list_arg = get_test_dpu_and_port(
        dpu_num, dpu_npu_port_list, rand_one_dut_hostname)

    with allure.step(f"Reset {dpu_list_arg}"):
        cmd_dpu_reset = f"sudo dpuctl dpu-reset {dpu_list_arg} "
        duthost.shell(cmd_dpu_reset, module_ignore_errors=True, module_async=True)

    with allure.step(f"Check dpu has been reset"):
        with allure.step(f"Check {test_dpu_list} are down"):
            verify_dpu_status(duthost, test_dpu_list, dpu_ready="False", dpu_shutdown_ready="False")

        do_verification_after_power_on_dpu(duthost, test_dpu_list, test_dpu_npu_port_list, dpu_bridge_midplane_ip_map)


def get_test_dpu_list(dpu_list_arg):
    dpu_list = DPU_LIST if "all" in dpu_list_arg else dpu_list_arg.split(",")
    allure.step(f"get test dpu list:{dpu_list}")
    return dpu_list


def verify_dpu_npu_port_down(duthost, dpu_npu_port_list):
    with allure.step(f"Verify dpu npu port is down"):
        pytest_assert(wait_until(100, 5, 0, duthost.links_status_down, dpu_npu_port_list),
                      "dpu dpu port are not down")


def verify_dpu_npu_port_up(duthost, dpu_npu_port_list):
    with allure.step(f"Verify dpu npu port is up"):
        pytest_assert(wait_until(300, 5, 0, duthost.links_status_up, dpu_npu_port_list),
                      "dpu dpu port are not up")


def verify_dpu_status(duthost, dpu_list, dpu_ready, dpu_shutdown_ready):
    def _verify_dpu_status():
        dpu_status = get_dpu_status(duthost)
        for one_dpu_status in dpu_status:
            if one_dpu_status['dpu'] in dpu_list:
                assert one_dpu_status['dpu ready'] == dpu_ready and \
                       one_dpu_status['dpu shutdown ready'] == dpu_shutdown_ready, \
                    f" Expected value: dpu ready {dpu_ready},  dpu shutdown ready {dpu_shutdown_ready}." \
                    f" Actual value: dpu ready {one_dpu_status['dpu ready']}, " \
                    f"dpu shutdown ready {one_dpu_status['dpu shutdown ready']}"
        logger.info("tested dpu status are ok")
        return True

    with allure.step(f"Verify dpu status"):
        pytest_assert(wait_until(200, 5, 0, _verify_dpu_status),
                      f"dpu ready is not {dpu_ready}, dpu shutdown ready is not {dpu_shutdown_ready}")


def verify_dpu_pci_links(duthost, dpu_list, is_link_existing):
    dpu_pci_links = get_dpu_pci_links(duthost)
    for dpu in dpu_list:
        if is_link_existing:
            assert DPU_PIC_ID_RISHIM_MAP[dpu]['pci_id'] in ",".join(dpu_pci_links), \
                f"For {dpu}, the pic_id:{DPU_PIC_ID_RISHIM_MAP[dpu]['pci_id']} doesn't exist in {dpu_pci_links}"
        else:
            assert DPU_PIC_ID_RISHIM_MAP[dpu]['pci_id'] not in ",".join(dpu_pci_links), \
                f"For {dpu}, the pic_id:{DPU_PIC_ID_RISHIM_MAP[dpu]['pci_id']} still exists in {dpu_pci_links}"
            assert len(dpu_pci_links) == (len(DPU_LIST) -len(dpu_list)) * 2, \
                f"pci links number is not correct. test dpu list: {dpu_list}\n, dpu_pci_link: {dpu_pci_links}"


def verify_dpu_bridge_midplane_ip_link(duthost, dpu_list, is_link_existing):
    dpu_bridge_midplane_ip_link = get_dpu_bridge_midplane_ip_links(duthost)
    for dpu in dpu_list:
        if is_link_existing:
            assert dpu in ",".join(dpu_bridge_midplane_ip_link), \
                f"For {dpu}, the bridge midplane doesn't exist in {dpu_bridge_midplane_ip_link}"
        else:
            assert dpu not in ",".join(dpu_bridge_midplane_ip_link), \
                f"For {dpu}, the bridge midplane still exists in {dpu_bridge_midplane_ip_link}"
            assert len(dpu_bridge_midplane_ip_link) == (len(DPU_LIST) -len(dpu_list)),\
                f" bridge midplane ip number is not correct.test pud list {dpu_list}\n, " \
                f"midplane ip links:{dpu_bridge_midplane_ip_link}"


def verify_dpu_ip_pinable(duthost, dpu_list, dpu_bridge_midplane_ip_map):
    for dpu in dpu_list:
        with allure.step(f"Verify {dpu} is pingable"):
            duthost.shell(f"ping -c 5 {dpu_bridge_midplane_ip_map[dpu]}")


def get_dpu_status(duthost):
    cmd_get_dpu_status = "sudo dpuctl dpu-status"
    return duthost.show_and_parse(cmd_get_dpu_status)


def get_test_dpu_and_port(dpu_num, dpu_npu_port_list, rand_one_dut_hostname):
    test_dpu_list = random.sample(DPU_LIST, k=random.randint(1, len(DPU_LIST))) if dpu_num == "random" else DPU_LIST
    dpu_list_arg = ",".join(test_dpu_list) if dpu_num == "random" else f" --{dpu_num}"
    temp_dpu_npu_port_list = dpu_npu_port_list[rand_one_dut_hostname]
    temp_dpu_npu_port_list.sort(key=lambda port: int(port.replace("Ethernet", "")))
    test_dpu_npu_port_list = [temp_dpu_npu_port_list[int(dpu.replace('dpu', ""))] for dpu in test_dpu_list]
    logger.info(f"test dpu info:\n test dpu list:{test_dpu_list}"
                f"\ntest dpu port list:{test_dpu_npu_port_list} "
                f"\ndpu list arg:{dpu_list_arg} ")
    return test_dpu_list, test_dpu_npu_port_list, dpu_list_arg


def all_dpu_up(duthost):
    dpu_status = get_dpu_status(duthost)
    for one_dpu_status in dpu_status:
        if one_dpu_status['dpu ready'] != "True":
            logger.error(f"There is down dpu:{one_dpu_status}")
            return False
    logger.info("all dpus are up")
    return True


def get_dpu_pci_links(duthost):
    cmd_get_dpu_pic_links = "lspci -D | grep Blue"
    dpu_pci_links = duthost.shell(cmd_get_dpu_pic_links, module_ignore_errors=True)["stdout_lines"]
    logger.info(f"dpu pic links:{dpu_pci_links}")
    return dpu_pci_links


def get_dpu_bridge_midplane_ip_links(duthost):
    cmd_get_bridge_midplane_ip_links = "ip link | grep 'dpu'"
    dpu_bridge_midplane_links = duthost.shell(
        cmd_get_bridge_midplane_ip_links, module_ignore_errors=True)["stdout_lines"]
    logger.info(f"dpu bridge midplane links:{dpu_bridge_midplane_links}")
    return dpu_bridge_midplane_links


def verify_dpu_ip_links_and_pci_link_and_dpu_ip_pingable(duthost, dpu_bridge_midplane_ip_map, dpu_list, is_link_existing):
    link_status = "existing" if is_link_existing else "removal"
    with allure.step(f"Verify dpu midplane ip link is {link_status}"):
        verify_dpu_bridge_midplane_ip_link(duthost, dpu_list, is_link_existing)
    with allure.step(f"Verify dpu pic link {link_status}"):
        verify_dpu_pci_links(duthost, dpu_list, is_link_existing)
    if is_link_existing:
        with allure.step("Verify dpu ip is pingable"):
            verify_dpu_ip_pinable(duthost, dpu_list, dpu_bridge_midplane_ip_map)


def do_verification_after_power_off_dpu(duthost, test_dpu_list, test_dpu_npu_port_list, dpu_bridge_midplane_ip_map):
    with allure.step(f"verify {test_dpu_list} are down"):
        verify_dpu_status(duthost, test_dpu_list, dpu_ready="False", dpu_shutdown_ready="True")
    verify_dpu_npu_port_down(duthost, test_dpu_npu_port_list)
    verify_dpu_ip_links_and_pci_link_and_dpu_ip_pingable(duthost, dpu_bridge_midplane_ip_map, test_dpu_list,
                                                         is_link_existing=False)


def do_verification_after_power_on_dpu(duthost, test_dpu_list, test_dpu_npu_port_list, dpu_bridge_midplane_ip_map):
    with allure.step(f"verify {test_dpu_list} are up"):
        verify_dpu_status(duthost, test_dpu_list, dpu_ready="True", dpu_shutdown_ready="False")

    verify_dpu_npu_port_up(duthost, test_dpu_npu_port_list)
    verify_dpu_ip_links_and_pci_link_and_dpu_ip_pingable(duthost, dpu_bridge_midplane_ip_map, test_dpu_list,
                                                         is_link_existing=True)


import allure
import pytest
import time
import logging

from tests.common.config_reload import config_reload
from snake_common import ssh_client, onyx_cmd, get_sku, generate_vlans, gen_fanout_config, \
    gen_sonic_dut_config, dut_snake_config_name, fanout_snake_sonic_config_name
from tests.common.fixtures.conn_graph_facts import conn_graph_facts, fanout_graph_facts  # noqa F401

logger = logging.getLogger(__name__)
# Default authentication (eventually use Noga for this)

SONIC_USER = "admin"
SONIC_PASS = "YourPaSsWoRd"

ONYX_USER = "admin"
ONYX_PASS = "admin"

# Globals

SONIC_CONFIG = "/etc/sonic/config_db.json"
SONIC_BACKUP_CONFIG = "/etc/sonic/config_db.json.bak"
ONYX_CONFIG = "/var/home/root/config.bak"


def pytest_generate_tests(metafunc):
    val = metafunc.config.getoption('--sku')
    module_type = metafunc.config.getoption('--module')
    if 'sku_name' in metafunc.fixturenames and val is not None:
        metafunc.parametrize('sku_name', [val], scope="module")
    if 'module_type' in metafunc.fixturenames and module_type is not None:
        metafunc.parametrize('module_type', [module_type], scope="module")


@pytest.fixture(scope='module', autouse=True)
def fanout(duthost, fanouthosts, localhost):
    for fanout in list(fanouthosts.values()):
        break
    yield fanout


@pytest.fixture(scope='module', autouse=True)
def backup_restore_fanout(duthost, fanout, localhost):
    if fanout.os == "onyx":
        logger.info("backup onyx fanout config")
        onyx, onyx_file = ssh_client(fanout.hostname, ONYX_USER, ONYX_PASS)

        onyx_cmd(onyx, ["en", "con term",
                        "con upload active scp://{}:{}@localhost:{}".format(ONYX_USER, ONYX_PASS, ONYX_CONFIG)])
        onyx_file.get(ONYX_CONFIG)
    else:
        logger.info("backup sonic fanout config")
        fanout.shell(f"sudo cp {SONIC_CONFIG} {SONIC_BACKUP_CONFIG}")

    yield

    logger.info("restore fanout config")
    if fanout.os == "onyx":
        allure.step("Restore Fanout configuration backup")
        onyx_file.put("config.bak", ONYX_CONFIG)
        onyx_cmd(onyx, ["en", "con term", "con delete config.bak"])
        onyx_cmd(onyx,
                 ["en", "con term", "con fetch scp://{}:{}@localhost:{}".format(ONYX_USER, ONYX_PASS, ONYX_CONFIG)])
        onyx_cmd(onyx, ["en", "con term", "con switch config.bak"])

        localhost.wait_for(host=fanout.hostname, port=22, state='started', delay=10, timeout=300)
    else:
        logger.info("restore sonic fanout config")
        fanout.shell(f"sudo cp {SONIC_BACKUP_CONFIG} {SONIC_CONFIG} ")
        fanout.shell("sudo reboot",  module_async=True)


@pytest.fixture(scope='module', autouse=True)
def backup_restore_dut(duthost, localhost):
    logger.info("backup dut config")
    duthost.shell(f"sudo cp {SONIC_CONFIG} {SONIC_BACKUP_CONFIG}")

    yield

    logger.info("restore dut config")
    duthost.shell(f"sudo cp {SONIC_BACKUP_CONFIG} {SONIC_CONFIG} ")
    config_reload(duthost)


@pytest.fixture(scope='module', autouse=True)
def dut_port_to_fanout_port_map(duthost, conn_graph_facts):
    dut_port_to_fanout_port_map = {}
    for dut_port, peer_device_info in conn_graph_facts["device_conn"][duthost.hostname].items():
        dut_port_to_fanout_port_map[dut_port] = peer_device_info.get("peerport")
    logger.info(f"Dut ports to fanout ports map:{dut_port_to_fanout_port_map}")
    return dut_port_to_fanout_port_map


@pytest.fixture(scope='module', autouse=True)
def dut_port_to_speed_map(duthost, conn_graph_facts):
    dut_port_to_speed_map = {}
    for dut_port, peer_device_info in conn_graph_facts["device_conn"][duthost.hostname].items():
        dut_port_to_speed_map[dut_port] = peer_device_info.get("speed")
    logger.info(f"Dut port speed map:{dut_port_to_speed_map}")
    return dut_port_to_speed_map


@pytest.fixture(scope='module', autouse=True)
def fanout_port_to_speed_map(duthost, conn_graph_facts):
    fanout_port_to_speed_map = {}
    for _, peer_device_info in conn_graph_facts["device_conn"][duthost.hostname].items():
        fanout_port_to_speed_map[peer_device_info["peerport"]] = peer_device_info.get("speed")
    logger.info(f"Fanout port speed map:{fanout_port_to_speed_map}")
    return fanout_port_to_speed_map


@pytest.fixture(scope='module', autouse=True)
def dut_sku(duthost, conn_graph_facts):
    dut_sku = conn_graph_facts["device_info"][duthost.hostname]["HwSku"]
    logger.info(f"dut sku is :{dut_sku}")
    return dut_sku


@pytest.fixture(scope='module', autouse=True)
def fanout_sku(fanout, fanout_graph_facts):
    fanout_sku = fanout_graph_facts[fanout.hostname]["device_info"]["HwSku"]
    logger.info(f"fanout sku is :{fanout_sku}")
    return fanout_sku


@pytest.fixture(scope='module')
def generate_sku(request, duthost, fanout, dut_sku, fanout_sku,
                 dut_port_to_fanout_port_map, dut_port_to_speed_map, fanout_port_to_speed_map, module_type):
    with allure.step("Generate SKU VLANs"):
        dut_config_data = get_sku(duthost, dut_sku, dut_snake_config_name)
        vlan_vrf_config = generate_vlans(dut_config_data, dut_port_to_fanout_port_map, request)
        gen_fanout_config(fanout, fanout_sku, dut_config_data, fanout_port_to_speed_map, module_type, **vlan_vrf_config)
        gen_sonic_dut_config(dut_config_data, dut_port_to_speed_map,  **vlan_vrf_config)
    return max([vrf[0] for vlan, vrf in vlan_vrf_config["dut_vrf_map"].items()])


@pytest.fixture(scope='module')
def configure_switches(duthost, localhost, fanout, generate_sku):
    with allure.step("Deploy configuration to Fanout"):
        if fanout.os == "onyx":
            onyx, onyx_file = ssh_client(fanout.hostname, ONYX_USER, ONYX_PASS)
            onyx_cmd(onyx, ["en", "con term", "con delete snake"])
            onyx_cmd(onyx, ["en", "con term", "con new snake", "con switch snake"])
            onyx.close()
            time.sleep(300)

            localhost.wait_for(host=fanout.hostname, port=22, state='started', delay=10, timeout=300)
            onyx, onyx_file = ssh_client(fanout.hostname, ONYX_USER, ONYX_PASS)

            onyx_file.put("onyx-config", "/var/home/root/sku-config")
            onyx_cmd(onyx, ["en", "con term", "con text file sku-config delete"])
            onyx_cmd(onyx, ["en", "con term", "con text fetch scp://{}:{}@localhost/var/home/root/sku-config".format(ONYX_USER, ONYX_PASS)])
            onyx_cmd(onyx, ["en", "con term", "con text file sku-config apply"])
            time.sleep(60)
        else:
            fanout.copy(src=fanout_snake_sonic_config_name, dest=SONIC_CONFIG)
            fanout.shell("sudo reboot", module_async=True)

    with allure.step("Deploy configuration to DUT"):
        duthost.copy(src=dut_snake_config_name, dest=SONIC_CONFIG)
        config_reload(duthost, wait=300)

    with allure.step("Close dut firewall in case blocking iperf"):
        duthost.shell("sudo iptables -F")

    if fanout.os != "onyx":
        with allure.step("close fanout firewall in case blocking iperf"):
            fanout.shell("sudo iptables -F")

    yield generate_sku


def pytest_addoption(parser):
    parser.addoption("--sku", action="store", type=str,
                     help="Type of SKU to use during snake test")
    parser.addoption("--module", action="store", type=str, default='qsfp',
                     help="Type of module in testbed for onyx fanout only")
    parser.addoption("--snake_test_port_num", action="store", type=int, default=0,
                     help="The total number of snake test ports."
                          "The default value is 0 which means the test number will be got according "
                          "the links definition the file of "
                          "ansible/files/hwsku_vars/xxx_setup/xxx_sku/sonic_nvidia_links.csv"
                          "The number should be set to even integer, e.g. 10, it means only 10 ports can be tested ")

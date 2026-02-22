"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only canonical setups.

"""

import pytest
import logging
import time

from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.ib_router.constants import IbRouterConsts
from ngts.nvos_tools.infra.IbRouterTool import IbRouterTool
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.opensm.OpenSmTool import OpenSmTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool

logger = logging.getLogger()

TEMP_FOLDER = "/tmp/"


@pytest.fixture(autouse=True, scope='session')
def init_extra_host_engines(topology_obj, engines):
    """
    init engine objects to extended amount of host nicknames - ha, hb, hc and so on
    """
    IbRouterTool.init_extra_host_engines(topology_obj, engines)


@pytest.fixture(autouse=True, scope='session')
def init_extra_host_interfaces(topology_obj, interfaces):
    """
    init interfaces data for extended amount of host nicknames - ha, hb, hc and so on
    """
    # ha, hb, hc and so on are the traffic dockers in XDR router setup
    for host_nickname in IbRouterConsts.ALL_HOSTS_NICKNAMES:
        if host_nickname in topology_obj.players:
            interfaces[f"{host_nickname}_dut_1"] = topology_obj.ports[f'{host_nickname}-dut-1']


@pytest.fixture(autouse=False, scope='session')
def stop_sm(engines, init_extra_host_engines):
    """
    Stops OpenSM on each traffic host
    """
    IbRouterTool.stop_sm_on_hosts(engines)


@pytest.fixture(autouse=False, scope='function')
def verify_sm_running_on_all_hosts(engines):
    """
    make sure SM is active on all hosts in SM_HOSTS_NICKNAMES
    no test should touch the SM, so if the process is down it might indicate a crash
    """
    with allure.step(f"Making sure SM is running on all SM hosts"):
        for sm_host_nickname in IbRouterConsts.SM_HOSTS_NICKNAMES:
            is_running = OpenSmTool.verify_open_sm_is_running_on_server(engines, sm_host_nickname)
            assert is_running, f"SM is not alive on {sm_host_nickname}"


@pytest.fixture(autouse=True, scope='session')
def reset_router_config_file(engines):
    """
    this function replace the file OPENSM_CONF_PATH/ROUTER_POLICY_FILE_NAME with ROUTER_POLICY_MASTER_FILE_NAME
    one or more tests might touch it
    """
    IbRouterTool.reset_router_config_file(engines)


@pytest.fixture(autouse=False, scope='session')
def start_sm_on_hosts(engines, stop_sm, enable_ib_router_profile, configure_leaf_ports):
    IbRouterTool.start_sm_on_hosts(engines)


@pytest.fixture(autouse=False, scope='session')
def disable_croc_fnm_ports(engines):
    """
    log to each crocodile switch in the setup and disable the FNM ports with the commands:
            sonic-db-cli CONFIG_DB hset "IB_PORT|Infiniband288" "admin_status" "down"
            sonic-db-cli CONFIG_DB hset "IB_PORT|Infiniband290" "admin_status" "down"
            sonic-db-cli CONFIG_DB hset "IB_PORT|Infiniband292" "admin_status" "down"
    """
    IbRouterTool.disable_croc_fnm_ports(engines)


@pytest.fixture(autouse=False, scope='session')
def enable_ib_router_profile(engines, stop_sm, disable_croc_fnm_ports):
    """
    helper function that will enable IB router profile in case it is disabled or has the incorrect number of swids
    """
    IbRouterTool.enable_ib_router_profile()


@pytest.fixture(autouse=False, scope='function')
def disable_ib_router_profile(engines):
    """
    helper function that will enable IB router profile in case it is disabled or has the incorrect number of swids
    """
    IbRouterTool.disable_ib_router_profile()


@pytest.fixture(autouse=False, scope='session')
def configure_leaf_ports(engines, enable_ib_router_profile):
    """
    helper function that will map the ports on the router towards the leaf switches to their SWID
    """
    IbRouterTool.configure_leaf_port_mapping(engines)
    IbRouterTool.verify_leaf_port_mapping()

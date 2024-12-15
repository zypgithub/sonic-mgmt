from ngts.tools.topology_tools.topology_by_setup import get_topology_by_setup_name_and_aliases
from ngts.tools.infra import update_sys_path_by_community_plugins_path
from ngts.tools.infra import get_topology_from_noga

update_sys_path_by_community_plugins_path()

from plugins.allure_server import pytest_addoption, pytest_sessionfinish, pytest_terminal_summary, \
    cache_pytest_session_run_cmd, attach_pytest_specific_test_run_cmd_to_allure_report  # noqa: E402


def ansible_host_pattern_param_already_loaded(session):
    ansible_host_pattern_loaded = False
    if hasattr(session.config.option, 'ansible_host_pattern'):
        ansible_host_pattern_loaded = False if session.config.option.ansible_host_pattern == "stub_string" or \
            not session.config.option.ansible_host_pattern else True
    return ansible_host_pattern_loaded


def get_setup_topology(session):
    setup_topology = 'ptf-any'
    if hasattr(session.config.option, 'sonic_topo'):
        if session.config.option.sonic_topo:
            setup_topology = session.config.option.sonic_topo
    return setup_topology


def pytest_sessionstart(session):
    session.config.option.allure_server_addr = "allure.nvidia.com"
    session.config.option.allure_server_port = ''

    if not ansible_host_pattern_param_already_loaded(session):
        topology = get_topology_from_noga(session)
        dut_name = topology.players['dut']['attributes'].noga_query_data['attributes']['Common']['Name']
        session.config.option.ansible_host_pattern = dut_name

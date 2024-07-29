import os
import re

from ngts.tools.topology_tools.topology_by_setup import get_topology_by_setup_name_and_aliases
from ngts.tools.infra import update_sys_path_by_community_plugins_path
from ngts.scripts.sonic_deploy.community_only_methods import is_dualtor_topo

update_sys_path_by_community_plugins_path()

from plugins.conditional_mark import pytest_addoption, pytest_collection, pytest_collection_modifyitems  # noqa: E402


def testbed_param_already_loaded(session):
    return hasattr(session.config.option, 'testbed')


def get_setup_topology(session):
    setup_topology = 'ptf-any'
    if hasattr(session.config.option, 'sonic_topo'):
        if session.config.option.sonic_topo:
            setup_topology = session.config.option.sonic_topo
    return setup_topology


def get_list_of_ignore_condition_files(session):
    conditions_file_regexp = r'tests_mark_conditions.*.yaml\Z'
    relative_path = 'tests/common/plugins/conditional_mark/'
    conditions_folder_path = session.config.option.ansible_inventory.replace('ansible/inventory', relative_path)
    condition_files_list = []
    for file_name in os.listdir(conditions_folder_path):
        if re.match(conditions_file_regexp, file_name):
            condition_files_list.append(os.path.join(conditions_folder_path, file_name))
    return condition_files_list


def mark_conditions_files_param_already_provided(session):
    if session.config.option.mark_conditions_files:
        return True
    return False


def pytest_sessionstart(session):
    setup_topology = get_setup_topology(session)
    if not testbed_param_already_loaded(session):
        topology = get_topology_by_setup_name_and_aliases(session.config.option.setup_name, slow_cli=False)
        dut_name = topology.players['dut']['attributes'].noga_query_data['attributes']['Common']['Name']
        session.config.option.testbed = f'{dut_name}-{setup_topology}'
    if is_dualtor_topo(setup_topology):
        session.config.option.testbed = f'{session.config.option.setup_name}-{setup_topology}'
    testbed_file_full_path = session.config.option.ansible_inventory.replace('inventory', 'testbed.yaml')
    session.config.option.testbed_file = testbed_file_full_path

    if not mark_conditions_files_param_already_provided(session):
        condition_files_list = get_list_of_ignore_condition_files(session)
        session.config.option.mark_conditions_files = condition_files_list

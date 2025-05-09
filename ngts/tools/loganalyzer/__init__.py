import os
import pytest
import logging

from pytest_ansible.errors import AnsibleConnectionFailure
from tests.common.errors import RunAnsibleModuleFail
from ngts.tools.infra import update_sys_path_by_community_plugins_path
from ngts.constants.constants import NvosCliTypes, PlayersAliases, CliType
from ngts.constants.performance_constants import PerfConsts
from ngts.nvos_constants.constants_nvos import NvosConst
from devices.sonic import SonicHost
from plugins.ansible_fixtures import ansible_adhoc
from plugins.loganalyzer import pytest_addoption, loganalyzer, log_rotate_modular_chassis


update_sys_path_by_community_plugins_path()
logger = logging.getLogger()


def is_loganalyzer_enabled(request):
    """
    Returns False if '--disable_loganalyzer' flag was provided
    """
    if request.config.getoption("--disable_loganalyzer") or "disable_loganalyzer" in request.keywords:
        logging.info("Log analyzer disabled")
        return False
    return True


def pytest_cmdline_main(config):
    """
    Pytest hook which adds default parameters, required for pytest-ansible module
    We define ansible_host_pattern with stub string. In other case will need to provide additional pytest argument
    with dut hostname
    :param config: pytest build-in
    """
    path = os.path.abspath(__file__)
    sonic_mgmt_path = path.split('/ngts/')[0]
    config.option.ansible_inventory = sonic_mgmt_path + '/ansible/inventory'
    config.option.ansible_host_pattern = 'stub_string'


@pytest.fixture(scope="session")
def duthosts(ansible_adhoc, topology_obj, request):
    """
    Emulate duthosts fixture from community
    :param ansible_adhoc: ansible_adhoc fixture
    :param topology_obj: topology_obj fixture
    :param request: request pytest builtin
    :return: list of ansible engines
    """
    ansible_engines_list = []

    for dut in PlayersAliases.duts_list:
        dut_info = topology_obj.players.get(dut)

        if dut_info:
            dut_ansible_engine = None
            dut_hostname = dut_info['attributes'].noga_query_data['attributes']['Common']['Name']
            if is_loganalyzer_enabled(request):
                try:
                    password = dut_info['engine'].password
                    username = dut_info['engine'].username
                    dut_ansible_engine = SonicHost(ansible_adhoc, dut_hostname, ssh_user=username, ssh_passwd=password)
                except Exception as err:
                    if isinstance(err, AnsibleConnectionFailure) and dut_info['attributes'].noga_query_data['attributes']['Topology Conn.']['CLI_TYPE'] in \
                            NvosCliTypes.NvueCliTypes:
                        logger.info(f'Ignore when NVOS dut is down')
                        continue
                    elif isinstance(err, KeyError) and 'dpu' in dut_hostname:
                        logger.info(f'Ignore the DPUs on smart switch setup if the ansible host is not available')
                        continue
                    else:
                        raise err
                ansible_engines_list.append(dut_ansible_engine)
                logging.info(f"{dut_hostname} added to ansible_engines_list")

    return ansible_engines_list

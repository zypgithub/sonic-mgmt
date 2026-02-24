import os
import logging

import pytest
from pytest import StashKey

from ngts.tools.infra import update_sys_path_by_community_plugins_path
from ngts.tools.infra import get_topology_from_noga

update_sys_path_by_community_plugins_path()

from plugins.allure_server import pytest_addoption, pytest_terminal_summary, \
    cache_pytest_session_run_cmd, attach_pytest_specific_test_run_cmd_to_allure_report, \
    export_session_info_to_allure  # noqa: E402
from plugins.allure_server import pytest_sessionfinish as _community_pytest_sessionfinish  # noqa: E402

logger = logging.getLogger()

# Type-safe stash key for Allure environment data (stored on pytest config).
_allure_env_key: StashKey[dict] = StashKey()

# Regression/MARS: Allure env keys and optional pytest option (None = from os.environ only).
_REGRESSION_ALLURE_ENV = [
    ("issu_version", "--issu_version"),
    ("dut_ip", None),
    ("sonic_mgmt_repo_branch", None),
    ("chip_type", None),
    ("branch", None),
    ("dut_name", None),
    ("target_version", "--target_version"),
    ("downgrade_version", "--downgrade_version"),
    ("traffic_host_ip", None),
    ("dut_type", None),
    ("setup_name", "--setup_name"),
    ("dump_backup_location", None),
    ("traffic_ports", None),
    ("custom_tarball_name", None),
    ("base_version", "--base_version"),
    ("release_name", "--release_name"),
    ("sonic_mgmt_repo_name", None),
]


def allure_set_environment(config, key, value):
    """
    Add a key-value pair to the Allure report environment.

    Call from a session- or module-scoped fixture to populate the Allure
    environment tab. Values are written to environment.properties at session end.

    :param config: pytest Config object (e.g. request.config).
    :param key: Environment entry name (e.g. "Branch", "Custom_Label").
    :param value: String value. Non-strings are converted to str.
    """
    env = config.stash.setdefault(_allure_env_key, {})
    env[str(key)] = str(value) if value is not None else ""


@pytest.fixture(scope="session", autouse=True)
def _allure_regression_environment(pytestconfig):
    """
    Session-scoped fixture: populate Allure environment from pytest options and env vars.

    Reads values from pytest CLI options (e.g. --setup_name, --target_version) when present,
    falling back to os.environ for the rest (e.g. dut_ip, dut_name, chip_type).
    Keys with no value are skipped.
    """
    for allure_key, option_name in _REGRESSION_ALLURE_ENV:
        value = None
        if option_name is not None:
            try:
                value = pytestconfig.getoption(option_name, default=None)
            except (ValueError, KeyError):
                pass
        if value is None or value == "":
            value = os.environ.get(allure_key) or os.environ.get(allure_key.upper())
        if value is not None and str(value).strip() != "":
            allure_set_environment(pytestconfig, allure_key, str(value).strip())
    yield


def ansible_host_pattern_param_already_loaded(session):
    # the ansible_host_pattern param is defined when it has the value
    # which is not "stub_string" or "localhost"
    return hasattr(session.config.option, 'ansible_host_pattern') and \
        session.config.option.ansible_host_pattern and \
        session.config.option.ansible_host_pattern != "stub_string" and \
        session.config.option.ansible_host_pattern != "localhost"


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


def pytest_sessionfinish(session, exitstatus):
    """
    write NGTS environment metadata, then delegate to community plugin.

    Our hook writes environment.properties first with NGTS regression/MARS data.
    Then the community hook runs — its get_setup_session_info() will overwrite this file if it meets the requirements.
    In the case of NVOS, it will not run, leaving the file untouched after this hook implementation.
    The community hook then uploads all files (including our environment.properties) to the allure server.
    """
    if not session.config.getoption("--collectonly"):
        allure_report_dir = getattr(session.config.option, "allure_report_dir", None)
        allure_env = session.config.stash.get(_allure_env_key, {})
        if allure_report_dir and allure_env:
            export_session_info_to_allure(allure_env, allure_report_dir)

    _community_pytest_sessionfinish(session, exitstatus)

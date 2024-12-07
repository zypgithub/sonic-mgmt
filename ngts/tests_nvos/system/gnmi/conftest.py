import logging

import pytest

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player, verify_gnmi_client_tools_installed

logger = logging.getLogger()


@pytest.fixture(scope='session')
def scp_player(engines) -> LinuxSshEngine:
    return get_scp_player(engines)


@pytest.fixture(scope='session', autouse=True)
def verify_gnmi_client_tools_installed_on_player():
    verify_gnmi_client_tools_installed()

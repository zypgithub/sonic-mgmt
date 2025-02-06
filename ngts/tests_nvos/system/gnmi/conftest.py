import logging

import pytest

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.helpers.pytest_helpers import get_cur_test_param_value
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player, verify_gnmi_client_tools_installed, \
    setup_gnmi_cert_tests, cleanup_gnmi_cert_tests

logger = logging.getLogger()


@pytest.fixture(scope='session')
def scp_player(engines) -> LinuxSshEngine:
    return get_scp_player(engines)


@pytest.fixture(scope='session', autouse=True)
def verify_gnmi_client_tools_installed_on_player():
    verify_gnmi_client_tools_installed()


@pytest.fixture(scope='module')
def gnmi_certs_ipv4(engines, dut_hostname, scp_player):
    tmp_certs_dir, certs = setup_gnmi_cert_tests(engines, dut_hostname, scp_player)
    yield certs
    cleanup_gnmi_cert_tests(tmp_certs_dir, certs)


@pytest.fixture(scope='module')
def gnmi_certs_ipv6(engines, dut_hostname, scp_player, dut_ipv6_addr):
    tmp_certs_dir, certs = setup_gnmi_cert_tests(engines, dut_hostname, scp_player, dut_ipv6_addr)
    yield certs
    cleanup_gnmi_cert_tests(tmp_certs_dir, certs)


@pytest.fixture
def gnmi_certs(request, gnmi_certs_ipv4, gnmi_certs_ipv6):
    if get_cur_test_param_value(request, 'addressing_type') == AddressingType.IPV6:
        return gnmi_certs_ipv6
    else:
        return gnmi_certs_ipv4

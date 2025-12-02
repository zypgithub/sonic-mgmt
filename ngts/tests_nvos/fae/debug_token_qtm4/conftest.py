"""
Conftest for QTM4 Debug Token tests.
"""
import pytest

from ngts.nvos_tools.infra.SecureBootTool import SecureBootTool


@pytest.fixture(scope='session')
def skip_if_opn_system(topology_obj):
    """
    Skip functionality tests if the system is OPN (production).

    Use this fixture in tests that require IPN (dev) systems for debug token functionality.
    Basic tests can still run on OPN systems.
    """
    if SecureBootTool.is_prod_system(topology_obj.players['dut']):
        pytest.skip("Debug token functionality tests are only supported on IPN systems. Skipping on OPN system.")

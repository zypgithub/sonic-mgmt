"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import pytest
import logging
from ngts.helpers.performance.performance_setup_helpers import apply_test_configuration
logger = logging.getLogger()


@pytest.fixture(scope='session', autouse=True)
def basic_test_configuration(topology_obj, players, engines):
    apply_test_configuration(players, scenario="static_topology")
    yield

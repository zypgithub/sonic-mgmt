"""

conftest.py

Defines the methods and fixtures which will be used by pytest for only performance setups.

"""
import pytest
import importlib.util
from ngts.helpers.performance_setup_helpers import PerformanceHelpers


@pytest.fixture(scope='session', autouse=True)
def basic_test_configuration(players, engines):
    PerformanceHelpers().apply_basic_configuration(players, engines, scenario="static_topology")

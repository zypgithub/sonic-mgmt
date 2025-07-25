import logging
import pytest

logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    # Add a command line option to enable nasa debuggability
    parser.addoption(
        "--nasa_debug",
        action="store_true",
        help="Turn on NASA debuggability for the tests to enable the debug info in the tech support."
    )


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line(
        "markers", "nasa_debuggability_tests: Tests to skip when NASA debuggability is explicitly enabled"
    )
    if config.getoption("--nasa_debug"):
        config.pluginmanager.import_plugin("ngts.tools.nasa_debug.nasa_debug_plugin")


@pytest.fixture(scope="session", autouse=True)
def nasa_debug(request):
    logger.info("Fixture NASA debug: {}".format(request.config.getoption("--nasa_debug")))
    return request.config.getoption("--nasa_debug")

from .nasa_debug_utils import NASA_DEBUG_ENTITY, NASA_DEBUG_DUMP_DIR, nasa_entity_debug_set
from .nasa_debug_utils import get_nasa_entity_debug_enabled, get_nasa_entity_debug_file
from .nasa_debug_utils import nasa_debuggability_enable, nasa_debuggability_disable
from .nasa_debug_utils import get_file_size
from .nasa_debug_utils import nasa_debug, enable_nasa_debuggability


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

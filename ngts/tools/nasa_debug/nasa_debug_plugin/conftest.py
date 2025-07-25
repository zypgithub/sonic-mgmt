import pytest
import logging
from .nasa_debug_utils import nasa_debuggability_enable_all, nasa_debuggability_disable_all

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True, scope="module")
def enable_nasa_debuggability(request, dpuhosts):
    """This fixture is used to enable NASA debuggability for the tests to enable the debug info in the tech support.
       Except for the debuggability tests themselves.

    """
    debuggability_test = request.node.get_closest_marker('nasa_debuggability_tests')
    if not debuggability_test:
        # for DASH tests, enable the debuggability on all DPUs
        logger.info("Enabling NASA debuggability to capture tech support info")
        nasa_debuggability_enable_all(dpuhosts)

        yield

        # for DASH tests, disable the debuggability on all DPUs
        logger.info("Disabling NASA debuggability to capture tech support info")
        nasa_debuggability_disable_all(dpuhosts)
    else:
        logger.info("Skipping enabling/disabling NASA debuggability to capture tech support info")
        yield

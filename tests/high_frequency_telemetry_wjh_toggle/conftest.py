# =============================================================================
# WJH Toggle Support
# =============================================================================
# Module-level fixture that toggles WJH state:
#   - If WJH is currently enabled, set to disabled and run tests
#   - If WJH is currently disabled, set to enabled and run tests
#
# If WJH container does not exist, all tests will be skipped.
# Original WJH state is restored after module completes.
# =============================================================================

import pytest
import logging
import inspect
import tests.high_frequency_telemetry.conftest as original_conftest

# Dynamically import all fixtures (functions decorated with @pytest.fixture)
for name, obj in inspect.getmembers(original_conftest):
    if hasattr(obj, '_pytestfixturefunction'):
        globals()[name] = obj

logger = logging.getLogger(__name__)


def _get_wjh_state(duthost):
    """Get the current WJH feature state."""
    try:
        feature_status, success = duthost.get_feature_status()
        if success:
            state = feature_status.get('what-just-happened')
            return state.lower() if state else None
        return None
    except Exception as e:
        logger.warning(f"Failed to get wjh state: {e}")
        return None


def _set_wjh_state(duthost, state):
    """Set the WJH feature state."""
    duthost.shell(f"sudo config feature state what-just-happened {state}")
    logger.info(f"Set what-just-happened to {state}")


@pytest.fixture(scope="module", autouse=True)
def wjh_state(duthosts, enum_rand_one_per_hwsku_hostname):
    """Module-level fixture to toggle WJH state.

    Automatically toggles WJH to the opposite state:
    - If currently enabled -> set to disabled
    - If currently disabled -> set to enabled

    If WJH container does not exist, tests will be skipped.
    Original WJH state is restored after module completes.
    """
    duthost = duthosts[enum_rand_one_per_hwsku_hostname]

    # Check if WJH container exists
    if 'what-just-happened' not in duthost.get_running_containers():
        pytest.skip("WJH container not found on DUT, skipping WJH toggle test")

    # Get current state
    original_state = _get_wjh_state(duthost)
    logger.info(f"WJH original state: {original_state}")

    # Toggle to opposite state
    target_state = "disabled" if original_state == "enabled" else "enabled"
    logger.info(f"=== WJH TOGGLE: {original_state} -> {target_state} ===")
    _set_wjh_state(duthost, target_state)

    yield target_state

    # Restore original state
    if original_state:
        logger.info(f"Restoring WJH to original state: {original_state}")
        _set_wjh_state(duthost, original_state)

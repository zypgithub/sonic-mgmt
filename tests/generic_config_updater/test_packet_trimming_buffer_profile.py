import logging
import pytest

from tests.common.gu_utils import apply_patch, expect_op_success, expect_op_failure
from tests.common.gu_utils import generate_tmpfile, delete_tmpfile
from tests.common.gu_utils import format_json_patch_for_multiasic
from tests.common.gu_utils import create_checkpoint, delete_checkpoint, rollback_or_reload

pytestmark = [
    pytest.mark.topology("t0", "t1")
]

logger = logging.getLogger(__name__)

# Buffer profile name for packet trimming action test
BUFFER_PROFILE_NAME = "queue1_downlink_lossy_profile"

# Packet discard action values
TRIMMING_ACTION_ENABLE = "trim"
TRIMMING_ACTION_DISABLE = "drop"
TRIMMING_ACTION_INVALID = "invalid_action"


@pytest.fixture(autouse=True)
def setup_env(duthost):
    """
    Setup/teardown fixture for buffer profile trimming action test.

    Args:
        duthost: DUT.
    """
    create_checkpoint(duthost)

    yield

    try:
        logger.info("Rolled back to original checkpoint")
        rollback_or_reload(duthost)

    finally:
        delete_checkpoint(duthost)


@pytest.mark.parametrize("action_value", [TRIMMING_ACTION_DISABLE, TRIMMING_ACTION_ENABLE])
def test_packet_trimming_buffer_profile_action(
    rand_selected_dut, loganalyzer, skip_if_packet_trimming_not_supported, action_value
):
    """
    Test packet trimming buffer profile action configuration.
    """
    json_patch = [
        {
            "op": "replace",
            "path": f"/BUFFER_PROFILE/{BUFFER_PROFILE_NAME}/packet_discard_action",
            "value": action_value
        }
    ]
    json_patch = format_json_patch_for_multiasic(duthost=rand_selected_dut, json_data=json_patch)

    tmpfile = generate_tmpfile(rand_selected_dut)
    logger.info("tmpfile {}".format(tmpfile))

    try:
        output = apply_patch(rand_selected_dut, json_data=json_patch, dest_file=tmpfile)
        expect_op_success(rand_selected_dut, output)

    finally:
        delete_tmpfile(rand_selected_dut, tmpfile)


def test_packet_trimming_buffer_profile_action_xfail(
    rand_selected_dut, loganalyzer, skip_if_packet_trimming_not_supported
):
    """
    Negative test for packet_discard_action with invalid value.
    """
    # Ignore expected error logs during rollback
    if loganalyzer:
        ignoreRegex = [
            r'.*sonic_yang: Data Loading Failed:Invalid value .* in "packet_discard_action" element.*'
        ]
        loganalyzer[rand_selected_dut.hostname].ignore_regex.extend(ignoreRegex)

    json_patch = [
        {
            "op": "replace",
            "path": f"/BUFFER_PROFILE/{BUFFER_PROFILE_NAME}/packet_discard_action",
            "value": TRIMMING_ACTION_INVALID
        }
    ]
    json_patch = format_json_patch_for_multiasic(duthost=rand_selected_dut, json_data=json_patch)

    tmpfile = generate_tmpfile(rand_selected_dut)
    logger.info("tmpfile {}".format(tmpfile))

    try:
        output = apply_patch(rand_selected_dut, json_data=json_patch, dest_file=tmpfile)
        expect_op_failure(output)

    finally:
        delete_tmpfile(rand_selected_dut, tmpfile)

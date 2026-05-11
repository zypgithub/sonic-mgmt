import logging
import re

import allure
import pytest
from tests.common.helpers.assertions import pytest_assert

logger = logging.getLogger(__name__)

VAR_LOG_MOUNT = "/var/log"
PROBE_FILENAME = ".writable_probe"

THRESHOLD_FACTOR = 0.05

DIRS_TO_CHECK = (
    "/home/admin",
    "/tmp",
)


def _expected_var_log_dir_size(chip_type):
    """
    SPC6 and above: 8 GiB; SPC5 and below: 4 GiB.
    return expected size in MB.
    """
    m = re.match(r"^SPC(\d+)$", str(chip_type).strip(), re.IGNORECASE)
    n = int(m.group(1))

    return 8 * 1024 if n >= 6 else 4 * 1024


def _query_var_log_dir_size(dut_engine):
    """Return total filesystem size in MB for the mount containing VAR_LOG_MOUNT (df -BM)."""
    cmd = f"sudo df -BM {VAR_LOG_MOUNT} 2>/dev/null | tail -1 | awk '{{print $2}}'"
    raw = dut_engine.run_cmd(cmd, validate=True).strip()
    if not raw:
        pytest.fail(f"df produced empty size for {VAR_LOG_MOUNT}; cmd={cmd!r}")

    try:
        return int(raw.rstrip("M"))
    except ValueError:
        pytest.fail(f"Could not parse df size as int from {raw!r} (cmd={cmd!r})")


class TestVarLogDirSize:

    def test_var_log_dir_size(self, engines, chip_type):
        dut_engine = engines.dut

        expected_size = _expected_var_log_dir_size(chip_type)

        with allure.step("Verify /var/log mount total size vs chip_type (±5%)"):
            actual_size = _query_var_log_dir_size(dut_engine)
            lo = int(expected_size * (1 - THRESHOLD_FACTOR))
            hi = int(expected_size * (1 + THRESHOLD_FACTOR))
            logger.info(
                f"var/log size: chip_type={chip_type} expected={expected_size}MB actual={actual_size}MB allowed=[{lo},{hi}]MB",
            )
            pytest_assert(
                lo <= actual_size <= hi,
                f"/var/log size out of range (chip_type={chip_type!r}): actual={actual_size}MB expected~{expected_size}MB range=[{lo},{hi}]MB",
            )

        with allure.step("Verify configured dirs can be listed and writable"):
            for path in DIRS_TO_CHECK:
                ls_cmd = f"test -d {path} && ls -ld {path}"
                try:
                    dut_engine.run_cmd(ls_cmd, validate=True)
                except Exception as exc:
                    pytest_assert(False, f"cannot list {path!r}: {exc}")

                probe = f"{path}/{PROBE_FILENAME}"
                wr_cmd = f"touch {probe} && rm -f {probe}"
                try:
                    dut_engine.run_cmd(wr_cmd, validate=True)
                except Exception as exc:
                    pytest_assert(False, f"cannot write to {path!r}: {exc}")
            logger.info(f"dirs ok: {', '.join(DIRS_TO_CHECK)}")

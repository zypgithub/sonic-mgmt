"""OTEL telemetry — NVUE CLI / ``nv show`` tests (ported from Cumulus SSIM ``otel_show``).

These validate applied NVUE state after ``nv set`` (config → ``--applied`` show parity).
They do **not** collect OTLP artifacts or assert exported metric values. Functional
OTLP tests live in ``test_otel_mgmt_vrf_*.py`` and ``test_otel_metric_coverage.py``.

Add new CLI/show coverage here rather than the functional OTEL test files.
"""

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.system.telemetry.otel.dual_platform import (
    run_transceiver_info_validation,
)

pytestmark = [
    pytest.mark.system,
    pytest.mark.otel,
]


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test_nv_show_system_telemetry_platform_stats_class_transceiver_info_validation(
    engines, devices, otel_suite_mgmt, test_api,
):
    """Validate the transceiver-info platform-stats class (SSIM otel_show).

    Checks root telemetry and ``stats-group sg_01``: ``state`` and ``sample-interval``.
    """
    TestToolkit.tested_api = test_api
    run_transceiver_info_validation(engines, devices, otel_suite_mgmt)

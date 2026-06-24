"""OTEL telemetry — secured (TLS) mgmt-VRF tests (ported from Cumulus; run on NVOS too).

Test bodies are identical across platforms; all NVOS/Cumulus divergence lives in
:mod:`ngts.tests_nvos.system.telemetry.otel.dual_platform`. Cumulus exports over the
``mgmt`` VRF with a destination certificate; NVOS exports over the ``default`` VRF
with a gRPC-level certificate — see the ``otel_suite_mgmt_secured`` fixture.
"""

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.system.telemetry.otel.dual_platform import (
    run_secured_collection_and_validate,
)

pytestmark = [
    pytest.mark.system,
    pytest.mark.otel,
]


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test01_otel_data_collection_mgmt_vrf_secured(
    engines, devices, otel_suite_mgmt_secured, otel_telemetry_cache, is_ib_router, test_api, tmp_path
):
    """OTLP metric collection on the mgmt/default VRF with TLS (SSIM otlp test01)."""
    TestToolkit.tested_api = test_api
    run_secured_collection_and_validate(
        engines, devices, otel_suite_mgmt_secured, is_ib_router, str(tmp_path)
    )

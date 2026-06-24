"""Cumulus lab: OTEL split-pipeline stats-group tests (SSIM ``test_telemetry_split_pipelines``)."""

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.tests_nvos.system.telemetry.otel.cumulus.constants import CumulusOtelConst
from ngts.tests_nvos.system.telemetry.otel.cumulus.split_pipeline import (
    apply_split_pipeline_test01_stats_group,
    prepare_split_pipeline_insecure_pre_run,
    prepare_split_pipeline_secured_pre_run,
    run_split_pipeline_test01_verification,
)
from ngts.tests_nvos.system.telemetry.otel.cumulus.telemetry_health import (
    assert_otlp_session_established,
)

pytestmark = [
    pytest.mark.cumulus,
    pytest.mark.otel,
    pytest.mark.split_pipelines,
]


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test01_otel_telemetry_split_mgmt_vrf_TLS(
    engines, otel_suite_mgmt_secured, test_api, tmp_path,
):
    TestToolkit.tested_api = test_api
    vrf = CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT
    cur_dir = str(tmp_path)
    collector = otel_suite_mgmt_secured.primary

    prepare_split_pipeline_secured_pre_run(engines.dut, collector, vrf=vrf)
    with allure.step("Apply split-pipeline test_01 stats-group (mgmt VRF TLS)"):
        apply_split_pipeline_test01_stats_group(
            engines.dut,
            otel_suite_mgmt_secured.primary_ip,
            include_router_lldp=False,
        )

    run_split_pipeline_test01_verification(
        engines.dut,
        collector,
        cur_dir,
        vrf=vrf,
        prepare_session=False,
    )


@pytest.mark.parametrize("test_api", [ApiType.NVUE])
def test01_otel_telemetry_split_mgmt_vrf_No_TLS(
    engines, otel_suite_mgmt, test_api, tmp_path,
):
    TestToolkit.tested_api = test_api
    vrf = CumulusOtelConst.TELEMETRY_EXPORT_VRF_MGMT
    cur_dir = str(tmp_path)
    collector = otel_suite_mgmt.primary

    prepare_split_pipeline_insecure_pre_run(engines.dut, vrf=vrf)
    with allure.step("Verify OTLP session before split-pipeline overlay"):
        assert_otlp_session_established(collector)

    with allure.step("Apply split-pipeline test_01 stats-group (mgmt VRF insecure)"):
        apply_split_pipeline_test01_stats_group(
            engines.dut,
            otel_suite_mgmt.primary_ip,
            include_router_lldp=True,
        )

    run_split_pipeline_test01_verification(
        engines.dut,
        collector,
        cur_dir,
        vrf=vrf,
        prepare_session=True,
    )

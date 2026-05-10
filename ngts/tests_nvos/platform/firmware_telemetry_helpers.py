from __future__ import annotations

from typing import List

from ngts.nvos_constants.constants_nvos import NvosConst, PlatformConsts
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.helpers import validate_gnmi_server_docker_state
from ngts.tests_nvos.system.gnmi.mapping.helpers import parse_gnmic_flat_output, run_gnmic_once_flat
from ngts.tests_nvos.system.reboot_telemetry_helpers import gnmi_client_for_dut


def gnmi_client_from_dut_node(engines, dut_node) -> GnmiClient:
    return gnmi_client_for_dut(engines.dut, dut_node)


def expand_nvue_key_to_gnmi_components(nvue_key: str, dut_device) -> List[str]:
    if nvue_key == PlatformConsts.FW_ASIC:
        asics = list(getattr(dut_device, "asic_numbers", []) or [])
        return asics or ["ASIC1"]
    if nvue_key == PlatformConsts.FW_SMA:
        sma_amount = int(getattr(dut_device, "sma_amount", 0) or 0)
        return [f"SMA{i}" for i in range(1, sma_amount + 1)] if sma_amount > 0 else []
    return [nvue_key]


def _firmware_version_gnmi_path(component_name: str) -> str:
    return f"components/component[name={component_name}]/state/firmware-version"


def _normalize_gnmi_firmware_value(value) -> str:
    return "" if value is None else str(value).strip().strip('"').strip("'")


def _assert_gnmi_firmware_version_from_flat(
    component_name: str, path: str, out: str
) -> str:
    """Parse ``run_gnmic_once_flat`` output and assert non-empty, not N/A. Returns normalized value."""
    raw = parse_gnmic_flat_output(out)
    actual = _normalize_gnmi_firmware_value(raw)
    assert actual, f"Empty gNMI firmware-version for {component_name!r} path={path!r}"
    assert actual != NvosConst.NOT_AVAILABLE, (
        f"gNMI firmware-version is N/A for {component_name!r} path={path!r}"
    )
    return actual


def _assert_gnmi_matches_nvue_from_value(
    component_name: str, path: str, actual: str, nvue_version: str
) -> None:
    expected = str(nvue_version).strip().strip('"').strip("'")
    assert actual == expected, (
        f"Firmware mismatch for {component_name!r}: gNMI={actual!r}, NVUE={expected!r}, path={path!r}"
    )


def assert_gnmi_firmware_version_matches_nvue(
    gnmi_client: GnmiClient, component_name: str, nvue_version: str
) -> None:
    """Single gNMI Get: assert firmware-version is present/not N/A and matches NVUE."""
    # Wait for 'nv-gnmi' docker after FW-install reboot (NVUE returns first, socket races).
    validate_gnmi_server_docker_state(TestToolkit.engines, should_run=True)
    path = _firmware_version_gnmi_path(component_name)
    out, _duration = run_gnmic_once_flat(path, client=gnmi_client)
    actual = _assert_gnmi_firmware_version_from_flat(component_name, path, out)
    _assert_gnmi_matches_nvue_from_value(component_name, path, actual, nvue_version)


def assert_gnmi_firmware_version(gnmi_client: GnmiClient, component_name: str) -> None:
    path = _firmware_version_gnmi_path(component_name)
    out, _duration = run_gnmic_once_flat(path, client=gnmi_client)
    _assert_gnmi_firmware_version_from_flat(component_name, path, out)


def assert_gnmi_matches_nvue_version(
    gnmi_client: GnmiClient, component_name: str, nvue_version: str
) -> None:
    path = _firmware_version_gnmi_path(component_name)
    out, _duration = run_gnmic_once_flat(path, client=gnmi_client)
    raw = parse_gnmic_flat_output(out)
    actual = _normalize_gnmi_firmware_value(raw)
    _assert_gnmi_matches_nvue_from_value(component_name, path, actual, nvue_version)

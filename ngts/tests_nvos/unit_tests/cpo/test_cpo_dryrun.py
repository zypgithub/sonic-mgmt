"""Offline dry-run of the real Gen2 CPO show tests.

Runs the actual test functions from tests_nvos/platform/cpo/test_cpo_show.py
end-to-end - test body, tool layer, command building, JSON parsing and
validators - against a FakeDutEngine that serves generated sample outputs
instead of an SSH connection (see fake_dut.py, incl. how to add a test).
`devices.dut` is a real PortiaCpo4Asic object, so topology and port lists are
the genuine article. NVUE only; action/reset/event tests stay DUT-only.

Run offline (no setup) with:
    python -m pytest ngts/tests_nvos/unit_tests/cpo -c ngts/pytest.ini \
        -o filterwarnings=ignore --noconftest
"""

import inspect
import time
from types import SimpleNamespace

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.unit_tests.cpo import sample_outputs as samples
from ngts.tests_nvos.unit_tests.cpo.fake_dut import FakeDutEngine, build_show_tree

PORTIA_CPO_4ASIC_KEY = "N7220_LD - Portia_CPO_4ASIC"


def _dry_run_tests() -> tuple:
    from ngts.tests_nvos.platform.cpo import test_cpo_show

    return (
        test_cpo_show.test_cpo_show_platform,
        test_cpo_show.test_cpo_show_laser_source,
        test_cpo_show.test_cpo_show_interface,
        test_cpo_show.test_cpo_show_health,
        test_cpo_show.test_cpo_topology_consistency,
    )


@pytest.fixture
def fake_fixtures(monkeypatch) -> dict:
    """Name -> fake for every fixture the dry-run tests may take."""
    monkeypatch.setenv("NVU_SWITCH_NEW_PASSWORD", "dummy")
    monkeypatch.setenv("NVU_SWITCH_USER", "dummy")
    monkeypatch.setenv("NVU_SWITCH_PASSWORD", "dummy")
    from ngts.nvos_tools.Devices.DeviceFactory import DeviceFactory

    device = DeviceFactory.create_device(PORTIA_CPO_4ASIC_KEY)
    # the sample generators are written against this exact topology
    assert device.cpo == samples.TOPOLOGY

    monkeypatch.setattr(TestToolkit, "tested_api", ApiType.NVUE)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    return {
        "engines": SimpleNamespace(dut=FakeDutEngine(build_show_tree(device))),
        "devices": SimpleNamespace(dut=device),
        "random_api": ApiType.NVUE,
    }


@pytest.mark.parametrize("show_test", _dry_run_tests(), ids=lambda test: test.__name__)
def test_dry_run(show_test, fake_fixtures):
    wanted = inspect.signature(show_test).parameters.keys()
    missing = wanted - fake_fixtures.keys()
    assert not missing, f"{show_test.__name__} needs fixtures {sorted(missing)} - add fakes to fake_fixtures"
    show_test(**{name: fake_fixtures[name] for name in wanted})

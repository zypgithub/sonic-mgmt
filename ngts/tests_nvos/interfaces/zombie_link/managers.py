"""
Thin wrapper over existing ``devices.dut`` fields for the zombie-link test.

No new DUT state; no class-name branching. Each property picks the first
already-populated field for the role, with a derived fallback computed from
other existing DUT fields:

- ``ports_under_test`` — first non-empty of:
  1. ``dut.nvl_access_ports_list`` (NVL5 / NVL6 access ports).
  2. Traffic ports derived from ``dut.interface_list`` by subtracting
     ``network_ports``, ``mgmt_ports`` and ``fnm_external_port_list`` — yields
     ``sw<N>p<M>`` (Black Mamba), ``sw<N>p1`` (Taipan), ``sw<A|B><N>p<M>``
     (Crocodile), without any platform-specific shape hardcoded here.

- ``fnm_ports_under_test`` — first non-empty of:
  1. ``dut.nvl_internal_fnm_ports`` (NVL5 / NVL6 internal FNM list).
  2. ``dut.fnm_external_port_list`` (external FNM, e.g. ``['fnm1']``). On
     multi-ASIC platforms the internal-FNM (``fnma<N>p<M>``) apply path is not
     consistently wired up — ``nv config apply`` rejects with "Interface does
     not exist" — so we test the external FNM port instead.

Both properties return ``None`` when nothing is populated; the test
pytest.skips that case cleanly. Adding a new platform = populate one of
these existing DUT fields; this file stays untouched.
"""

from typing import List, Optional


def _first_non_empty(*candidates):
    """Return the first non-empty iterable as a list, or ``None``."""
    for c in candidates:
        if c:
            return list(c)
    return None


def _traffic_ports_from_interface_list(dut) -> List[str]:
    """Derive the traffic-port subset from ``dut.interface_list``.

    Strips mgmt/network and external-FNM entries — leaves only the
    switching ports (``sw*p*`` family, regardless of platform-specific shape).
    """
    iface_list = getattr(dut, 'interface_list', None) or []
    exclude = set()
    for attr in ('network_ports', 'mgmt_ports', 'fnm_external_port_list'):
        exclude.update(getattr(dut, attr, None) or [])
    return [p for p in iface_list if p not in exclude]


class ZombieLinkManager:
    """Reads existing DUT port fields, with fallback per role."""

    def __init__(self, devices):
        self.devices = devices
        self.dut = devices.dut

    @property
    def ports_under_test(self) -> Optional[List[str]]:
        """Ports for the range-configuration test. ``None`` skips."""
        return _first_non_empty(
            getattr(self.dut, 'nvl_access_ports_list', None),
            _traffic_ports_from_interface_list(self.dut),
        )

    @property
    def fnm_ports_under_test(self) -> Optional[List[str]]:
        """FNM ports (internal or external) for the FNM test. ``None`` skips."""
        return _first_non_empty(
            getattr(self.dut, 'nvl_internal_fnm_ports', None),
            getattr(self.dut, 'fnm_external_port_list', None),
        )


def get_zombie_link_manager(devices) -> ZombieLinkManager:
    return ZombieLinkManager(devices)

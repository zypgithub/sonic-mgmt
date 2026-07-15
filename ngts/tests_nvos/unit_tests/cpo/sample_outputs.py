"""Sample `nv show` outputs for Gen2 CPO, mirroring CPO_HLD.md section 2.3.1.3.

These are the JSON-mode equivalents of the HLD's human-readable samples, used
as offline parser fixtures (Phase 1 validation gate). Shapes and field names
follow the HLD; values are representative. Generated for the default Portia
simx topology (4 CPOs, 4 OEs + 1 ELS each, 64 channels, 16 lasers).
"""

from ngts.nvos_tools.Devices.cpo.CpoTopology import CpoTopology

TOPOLOGY = CpoTopology(cpo_count=4)

# 2 ports per CPO in this fixture; the real port count comes from the DUT and is
# only cross-checked (cpo_to_ports vs port_to_cpo), never asserted as a constant.
_PORTS_PER_CPO = {
    cpo: [f"sw{(idx - 1) * 7 + 1}p1s1", f"sw{(idx - 1) * 7 + 1}p1s2"]
    for idx, cpo in enumerate(TOPOLOGY.cpo_names(), start=1)
}


def _channel_entry() -> dict:
    return {
        "rx-power": {"power": "-1.0 dBm", "alarm": "off", "alarm-severity": "none"},
        "tx-power": {"power": "-0.6 dBm", "alarm": "off", "alarm-severity": "none"},
        "rx-los": "False",
        "tx-los": "False",
        "tx-fault": "False",
        "laser-source-input-power": {
            "power": "-1.0 dBm",
            "alarm": "off",
            "alarm-severity": "none",
        },
        "fault-opcode": 0,
        "dp-state": "Initialized",
    }


def _oe_entry(serial_suffix: int) -> dict:
    return {
        "identifier": "OE 16x",
        "serial-number": f"MT2219FT0317{serial_suffix:02d}",
        "temperature": "36.8C",
    }


def _cpo_thresholds() -> dict:
    return {
        "warning": {
            "rx-power-high": "2.0 dBm",
            "rx-power-low": "-8.0 dBm",
            "tx-power-high": "2.0 dBm",
            "tx-power-low": "-6.0 dBm",
        },
        "alarm": {
            "rx-power-high": "3.0 dBm",
            "rx-power-low": "-10.0 dBm",
            "tx-power-high": "3.0 dBm",
            "tx-power-low": "-8.0 dBm",
        },
    }


def make_cpo_detail(cpo: str) -> dict:
    """`nv show platform cpo <cpo-id>` (HLD 'nv show platform cpo cpoN', Portia)."""
    return {
        "status": "Inserted",
        "error-status": "N/A",
        "identifier": "CPO Virtual Module",
        "fw-version": "42.40.15",
        "associated-ports": ", ".join(_PORTS_PER_CPO[cpo]),
        "associated-laser-sources": ", ".join(TOPOLOGY.els_for_cpo(cpo)),
        "associated-optical-engines": ", ".join(TOPOLOGY.oes_for_cpo(cpo)),
        "thresholds": _cpo_thresholds(),
        "oe": {
            oe: _oe_entry(i) for i, oe in enumerate(TOPOLOGY.oes_for_cpo(cpo), start=1)
        },
        "channel": {ch: _channel_entry() for ch in TOPOLOGY.channel_names()},
    }


def _laser_entry() -> dict:
    return {
        "enabled": "true",
        "oper-status": "up",
        "error-status": "N/A",
        "ramping-status": "on",
        "power-restriction": "off",
        "laser-age": "50%",
        "target-output-power": "1.50mW",
        "laser-mpd-current": "0.12mA",
        "laser-bias-current": {
            "current": "12.2 mA",
            "alarm": "off",
            "alarm-severity": "none",
            "threshold": {
                "high-alarm": "14.0 mA",
                "low-alarm": "8.0 mA",
                "high-warning": "13.0 mA",
                "low-warning": "9.0 mA",
            },
        },
        "tec-current": "55mA",
        "tec-voltage": "2.9V",
        "laser-temperature": "23.5C",
        "laser-health": "25 mV",
        "tec-health": "15 mV",
        "frequency-error": "2.3 GHz",
        "tx-power": {"power": "32 mW", "alarm": "off", "alarm-severity": "none"},
    }


def make_laser_source_detail(els: str) -> dict:
    """`nv show platform laser-source <els-id>` (HLD Portia sample)."""
    return {
        "diagnostics-status": "Diagnostic Data Available",
        "status": "Inserted",
        "error-status": "N/A",
        "vendor-date-code": "220505",
        "identifier": "ELS",
        "vendor-name": "NVIDIA",
        "vendor-rev": "A4",
        "vendor-pn": "CPO-800G-2x400G",
        "vendor-sn": "MT2443FT01035",
        "fw-version": "42.40.15",
        "parent": TOPOLOGY.cpo_for_els(els),
        "temperature": {
            "temperature": "28.00 C",
            "high-alarm-threshold": "80.00 C",
            "high-warning-threshold": "60.00 C",
        },
        "power-consumption": "3.52W",
        "icc-current": "122mA",
        "threshold": {
            "warning": {"tx-power-upper": "0.0 dBm", "tx-power-lower": "-3.0 dBm"},
            "alarm": {"tx-power-upper": "1.0 dBm", "tx-power-lower": "-5.0 dBm"},
        },
        "laser": {laser: _laser_entry() for laser in TOPOLOGY.laser_names()},
    }


def make_interface_cpo(port: str, cpo: str, oe: str, channels: list[str]) -> dict:
    """`nv show interface <port> cpo` for a Portia CPO trunk subport."""
    return {
        "parent": cpo,
        "status": "Inserted",
        "error-status": "N/A",
        "identifier": "CPO Virtual Module",
        "fw-version": "42.40.15",
        "associated-ports": port,
        "associated-laser-sources": ", ".join(TOPOLOGY.els_for_cpo(cpo)),
        "associated-optical-engines": oe,
        "thresholds": _cpo_thresholds(),
        "oe": {oe: _oe_entry(1)},
        "channel": {ch: _channel_entry() for ch in channels},
    }


# `nv show platform cpo` (summary) - keyed by CPO name
SHOW_PLATFORM_CPO = {
    cpo: {
        "fw-version": "42.40.15",
        "associated-ports": ", ".join(_PORTS_PER_CPO[cpo]),
        "associated-laser-sources": ", ".join(TOPOLOGY.els_for_cpo(cpo)),
        "associated-optical-engines": ", ".join(TOPOLOGY.oes_for_cpo(cpo)),
    }
    for cpo in TOPOLOGY.cpo_names()
}

# `nv show platform cpo <cpo-id>` for every CPO - keyed by CPO name
SHOW_PLATFORM_CPO_DETAIL = {cpo: make_cpo_detail(cpo) for cpo in TOPOLOGY.cpo_names()}

# `nv show platform laser-source` (summary) - keyed by ELS name
SHOW_PLATFORM_LASER_SOURCE = {
    els: {
        "identifier": "ELS x16",
        "vendor-name": "NVIDIA",
        "vendor-pn": f"MCP7Y60-H01{chr(ord('A') + i)}",
        "vendor-sn": f"MT2233VS0222{i + 1}",
        "vendor-rev": "A4",
        "fw-version": "42.40.15",
    }
    for i, els in enumerate(TOPOLOGY.els_names())
}

SHOW_PLATFORM_LASER_SOURCE_DETAIL = {
    els: make_laser_source_detail(els) for els in TOPOLOGY.els_names()
}

SHOW_INTERFACE_CPO_SW8P1S1 = make_interface_cpo(
    port="sw8p1s1", cpo="cpo2", oe="oe6", channels=["channel-17", "channel-18"]
)

# port -> parent cpo, as reported by `nv show interface <port> cpo` per port
PORT_TO_CPO = {port: cpo for cpo, ports in _PORTS_PER_CPO.items() for port in ports}

# `nv show fae system cpo els-initialization` (Portia: 5 steps)
SHOW_FAE_ELS_INITIALIZATION = {
    els: {
        "fiber-check": "failed",
        "laser-tuning": "N/A",
        "laser-up": "N/A",
        "laser-fine-tune": "failed",
        "power-setpoint": "failed",
    }
    for els in TOPOLOGY.els_names()
}

# `nv show fae system cpo els-initialization-per-laser` (per-laser breakdown).
# NOTE: per the HLD sample this output keys lasers as laser1..laser16 (no dash),
# UNLIKE the laser-source show / activate action which use laser-1..laser-16.
# Pin the real key format on the DUT in Phase 5.
SHOW_FAE_ELS_INITIALIZATION_PER_LASER = {
    els: {
        "els-initialization": {
            f"laser{i}": {
                "fiber-check": "failed",
                "fiber-tuning": "N/A",
                "laser-up": "not-reached",
                "laser-fine-tune": "failed",
                "power-setpoint": "failed",
                "error": "Operation failed - No specified reason",
            }
            for i in range(1, TOPOLOGY.lasers_per_els + 1)
        }
    }
    for els in TOPOLOGY.els_names()
}

# `nv show fae system cpo`
SHOW_FAE_SYSTEM_CPO = {"cpo-dump-state": "enabled"}

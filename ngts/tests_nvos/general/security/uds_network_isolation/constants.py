"""Constants for UDS Network Isolation tests.

Port and UDS path definitions are setup-dependent:
- NVLink setups (Juliet-based): NMX-C, NMX-T, NV-Bridge, nv-umf, and nv-gnmi sockets.
- XDR setups (Crocodile, BlackMamba): nv-umf and nv-gnmi UDS; no NMX / NV-Bridge.
"""
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class ComponentPaths:
    """UDS socket paths for a single component."""
    name: str
    uds_paths: Tuple[str, ...] = field(default_factory=tuple)


# ── UDS paths by component ──────────────────────────────────────────────────

NMX_C_PATHS = ComponentPaths(
    name="nmx-c",
    uds_paths=(
        "/var/run/nmx-c/nmx-c-gwapi.socket",
        "/var/run/nmx-c/nmx-c-fib.socket",
        "/var/run/nmx-c/nmx-c-rest.socket",
        "/var/run/nmx-c/nmx-c-gnmi.socket",
    ),
)

NMX_T_PATHS = ComponentPaths(
    name="nmx-t",
    uds_paths=(
        "/var/run/nmx-t/control.sock",
    ),
)

NV_BRIDGE_PATHS = ComponentPaths(
    name="nv-bridge",
    uds_paths=(
        "/var/run/nv-bridge/restapi_listen_port.sock",
        "/etc/nv-bridge/envoy_listen_port.sock",
    ),
)

# NV-UMF and nv-gnmi Unix sockets (host paths).  Omitted: nv-gnoi-state.json is
# a regular file, not a UDS, and is out of scope for socket permission tests.
#
# Note: proxy.sock is bound only while nv-gnmi holds an active upstream
# subscribe channel into nv-umf, so TC-DNI-01 keeps a gnmic STREAM subscribe
# alive for the duration of the UDS validation block (see
# TC_DNI01_GNMI_SUBSCRIBE_INTERFACE).
TC_DNI01_GNMI_SUBSCRIBE_INTERFACE = "Ethernet0"
NV_UMF_PATHS = ComponentPaths(
    name="nv-umf",
    uds_paths=(
        "/var/run/nv-umf/agent-registration.sock",
        "/var/run/nv-umf/contract.sock",
        "/var/run/nv-umf/proxy.sock",
        "/var/run/nv-umf/nvos-agent.sock",
    ),
)

NV_GNMI_PATHS = ComponentPaths(
    name="nv-gnmi",
    uds_paths=(
        "/var/run/nv-gnmi/gnmi-otlp.sock",
        "/var/run/nv-gnmi/gnoi.sock",
        "/var/run/nv-gnmi/gnmi.sock",
    ),
)

# ── Published (external) TCP ports ───────────────────────────────────────────

# Externally published gNMI/gRPC (host): 9339.  (9379 may appear as a mapped
# alias depending on product naming; 9339 remains the primary case identifier.)
PUBLISHED_PORTS_NVLINK: Dict[int, str] = {
    9339: "gNMI server (external)",
    9351: "NMX-T",
    9352: "NMX-T",
    9353: "NMX-T",
    9354: "NMX-T",
    9370: "NMX-C gwapi",
    9379: "Public gNMI",
    50052: "NV-Bridge server",
    443: "HTTPS server",
}

PUBLISHED_PORTS_XDR: Dict[int, str] = {
    9339: "gNMI server (external)",
    9379: "Public gNMI",
}

# ── Internal ports that must NOT be exposed ──────────────────────────────────

# OTLP default (4317) must not be listening on the host; telemetry uses UDS
# (e.g. gnmi-otlp.sock) instead of a TCP listener on 4317.
INTERNAL_PROBE_PORTS_NVLINK: Dict[int, str] = {
    4317: "OTLP/telemetry",
    6379: "Redis (internal)",
    6666: "Internal service",
    9001: "Internal service",
    9350: "NMX-T (internal)",
    9371: "NMX-C (internal)",
    9372: "NMX-C (internal)",
    9373: "NMX-C (internal)",
    9374: "NMX-C (internal)",
    9375: "NMX-C (internal)",
    9376: "NMX-C (internal)",
    9377: "NMX-C (internal)",
    9380: "NMX-C (internal)",
    9381: "NV-Bridge cluster internal",
    9382: "NV-Bridge cluster internal",
    9383: "NV-Bridge cluster internal",
    9384: "NV-Bridge cluster internal",
    9385: "NV-Bridge cluster internal",
    9386: "NV-Bridge cluster internal",
    9387: "NV-Bridge cluster internal",
    9388: "NV-Bridge cluster internal",
    9389: "NV-Bridge cluster internal",
    50051: "NV-Bridge (internal)",
    50053: "NV-Bridge Envoy (internal)",
}

INTERNAL_PROBE_PORTS_XDR: Dict[int, str] = {
    4317: "OTLP/telemetry (not exposed on host; use UDS)",
}

# ── Per-setup profiles ───────────────────────────────────────────────────────

NVLINK_COMPONENTS = [
    NMX_C_PATHS,
    NMX_T_PATHS,
    NV_BRIDGE_PATHS,
    NV_UMF_PATHS,
    NV_GNMI_PATHS,
]
XDR_COMPONENTS = [NV_UMF_PATHS, NV_GNMI_PATHS]

# Monitor user name
MONITOR_USER = "monitor"

# SSH port (always expected open in external scans)
SSH_PORT = 22

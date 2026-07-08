"""Constants for the NVOS OTEL telemetry test suite (insecure OTLP gRPC, file exporter).

Generic telemetry constants (subtree names, default values, platform-stats class
names, etc.) live in :mod:`ngts.nvos_constants.constants_nvos.TelemetryConsts`.
This module holds only the OTel-collector-specific test choices: binary names,
install paths/URLs, timeouts, the minimal collector YAML, and capability /
metric-name gating used by the OTel coverage tests.
"""

import enum
from typing import Dict, Tuple
from ngts.nvos_constants.constants_nvos import TelemetryConsts


class OtelCapability:
    """Capabilities emitted by ``helpers.dut_capabilities``."""

    HAS_IB_ROUTER_PROFILE = "has-ib-router-profile"
    SUPPORTS_PEER_PORT_STATS = "supports-peer-port-stats"
    HAS_CONNECTED_TRANSCEIVERS = "has-connected-transceivers"
    # NVLink-only platform metrics (absent on IB / Crocodile-class systems).
    SUPPORTS_NVLINK_PLATFORM_METRICS = "supports-nvlink-platform-metrics"


class OtelCollectorLabel(enum.Enum):
    """Identifies which of the two OTel collector instances in the suite this is.

    Both instances are identical OTel collectors; the label only selects per-instance
    constants (``OtelCollectorConst.{PRIMARY,SECONDARY}_*``) and which ``engines.*``
    host the collector runs on (see ``OtelCollectorConst.HOST_ATTR_BY_LABEL``).
    """

    PRIMARY = "primary"
    SECONDARY = "secondary"


def _otel_collector_config_yaml(
    otlp_port: int,
    file_exporter_path: str,
    max_megabytes: int,
    max_backups: int,
    bind_addr: str = "0.0.0.0",
) -> str:
    """OTEL collector config: OTLP gRPC receiver in, file exporter out (with rotation)."""
    endpoint = f"{bind_addr}:{otlp_port}"
    return f"""receivers:
  otlp:
    protocols:
      grpc:
        endpoint: {endpoint}
processors: {{}}
exporters:
  file:
    path: {file_exporter_path}
    rotation:
      max_megabytes: {max_megabytes}
      max_backups: {max_backups}
service:
  telemetry:
    metrics:
      level: none
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [file]
"""


def _otel_collector_config_yaml_tls(
    otlp_port: int,
    file_exporter_path: str,
    max_megabytes: int,
    max_backups: int,
    *,
    cert_file: str,
    key_file: str,
    bind_addr: str = "0.0.0.0",
) -> str:
    """OTEL collector config with TLS on the OTLP gRPC receiver."""
    endpoint = f"{bind_addr}:{otlp_port}"
    return f"""receivers:
  otlp:
    protocols:
      grpc:
        endpoint: {endpoint}
        tls:
          cert_file: {cert_file}
          key_file: {key_file}
processors: {{}}
exporters:
  file:
    path: {file_exporter_path}
    rotation:
      max_megabytes: {max_megabytes}
      max_backups: {max_backups}
service:
  telemetry:
    metrics:
      level: none
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [file]
"""


class OtelCollectorConst:
    BINARY_NAME = "otelcol-contrib"

    OTLP_GRPC_PORT = 4317
    OTLP_GRPC_BIND_ADDR = "0.0.0.0"

    # Both collectors install identically: download the upstream `.tar.gz`, drop the
    # `otelcol-contrib` binary in `/usr/local/bin`, and run it as a `nohup` foreground
    # process with a log file (identified later via ``pgrep -f`` on the binary + config
    # signature). One pinned version for both roles to avoid skew.
    OTEL_COLLECTOR_VERSION = "0.130.0"
    OTEL_COLLECTOR_CONTRIB_GITHUB_RELEASES_BASE = (
        "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download"
    )

    OTEL_TLS_CA_NAME = "ca"

    # Per-label host attribute on the ``engines`` fixture. PRIMARY runs on the sonic-mgmt
    # container (per-DUT); SECONDARY runs on the HA player (per-testbed).
    HOST_ATTR_BY_LABEL: Dict[OtelCollectorLabel, str] = {
        OtelCollectorLabel.PRIMARY: "sonic_mgmt",
        OtelCollectorLabel.SECONDARY: "ha",
    }

    # Primary collector on engines.sonic_mgmt.
    BASE_PATH = "/etc/otelcol"
    PRIMARY_CONFIG_PATH = f'{BASE_PATH}/primary-config.yaml'
    PRIMARY_OUTPUT_JSON_PATH = f'{BASE_PATH}/primary-test.json'
    PRIMARY_OUTPUT_JSON_ROTATED_GLOB = f'{BASE_PATH}/primary-test-*.json'
    PRIMARY_STAGED_OUTPUT_JSON_PATH = "/tmp/otel-artifacts/otel-primary-out.json"
    PRIMARY_LOG_PATH = "/tmp/otelcol-primary.log"
    PRIMARY_FILE_EXPORT_MAX_MB = 600
    PRIMARY_FILE_EXPORT_MAX_BACKUPS = 1

    # Secondary collector on engines.ha (per-testbed; fails if HA is absent).
    SECONDARY_CONFIG_PATH = f'{BASE_PATH}/secondary-config.yaml'
    SECONDARY_OUTPUT_JSON_PATH = f'{BASE_PATH}/secondary-test.json'
    SECONDARY_OUTPUT_JSON_ROTATED_GLOB = f'{BASE_PATH}/secondary-test-*.json'
    SECONDARY_STAGED_OUTPUT_JSON_PATH = "/tmp/otel-artifacts/otel-secondary-out.json"
    SECONDARY_LOG_PATH = "/tmp/otelcol-secondary.log"
    SECONDARY_FILE_EXPORT_MAX_MB = 600
    SECONDARY_FILE_EXPORT_MAX_BACKUPS = 1

    PRIMARY_CONFIG_YAML = _otel_collector_config_yaml(
        OTLP_GRPC_PORT,
        PRIMARY_OUTPUT_JSON_PATH,
        PRIMARY_FILE_EXPORT_MAX_MB,
        PRIMARY_FILE_EXPORT_MAX_BACKUPS,
        bind_addr=OTLP_GRPC_BIND_ADDR,
    )
    SECONDARY_CONFIG_YAML = _otel_collector_config_yaml(
        OTLP_GRPC_PORT,
        SECONDARY_OUTPUT_JSON_PATH,
        SECONDARY_FILE_EXPORT_MAX_MB,
        SECONDARY_FILE_EXPORT_MAX_BACKUPS,
        bind_addr=OTLP_GRPC_BIND_ADDR,
    )

    # Telemetry subtree names (interface-stats / peer-port-stats / ib-router-stats /
    # platform-stats) and platform-stats class names live in TelemetryConsts as the
    # single source of truth; consumers should reference them via
    # ``TelemetryConsts.{INTERFACE_STATS, PEER_PORT_STATS, IB_ROUTER_STATS,
    # PLATFORM_STATS}``, ``TelemetryConsts.ALL_STATS_SUBTREES`` and
    # ``TelemetryConsts.PLATFORM_CLASSES`` rather than re-declaring the strings here.

    # NVUE telemetry sample intervals. `platform-stats export sample-interval` is restricted
    # to [60, 86400]; the other groups have no enforced lower bound, so we keep them at 10s.
    INTERFACE_STATS_SAMPLE_INTERVAL_SEC = 10
    PEER_PORT_STATS_SAMPLE_INTERVAL_SEC = 10
    IB_ROUTER_STATS_SAMPLE_INTERVAL_SEC = 10
    PLATFORM_STATS_SAMPLE_INTERVAL_SEC = 60

    # Floor of 70s ensures a platform-stats sample (60s + warm-up) always fits in the wait.
    OTEL_COLLECTION_WARM_UP_SEC = 10
    OTEL_COLLECTION_MIN_WAIT_SEC = 70

    @staticmethod
    def collection_window_sec(max_sample_interval_sec: int) -> int:
        return max(
            max_sample_interval_sec + OtelCollectorConst.OTEL_COLLECTION_WARM_UP_SEC,
            OtelCollectorConst.OTEL_COLLECTION_MIN_WAIT_SEC,
        )

    @staticmethod
    def artifact_poll_timeout_sec(max_sample_interval_sec: int) -> int:
        """Poll budget for a non-empty file-exporter artifact.

        Used after :meth:`collection_window_sec` sleep (or includes that window when no
        prior sleep). Cumulus/mgmt OTLP can deliver the first non-empty batch slightly
        after the nominal collection window; logs showed ~62s poll after a 70s sleep
        with ``ARTIFACT_TIMEOUT_SEC=60`` alone.
        """
        return (
            OtelCollectorConst.collection_window_sec(max_sample_interval_sec) +
            OtelCollectorConst.ARTIFACT_TIMEOUT_SEC
        )

    START_TIMEOUT_SEC = 90
    START_RETRY_INTERVAL_SEC = 3
    ARTIFACT_TIMEOUT_SEC = 60

    # Present in OTLP export via prometheus-node-exporter / scrape pipeline; not NVUE
    # ``nvswitch_*`` catalog metrics. Ignored when YAML is absent on the DUT.
    OTEL_PROMETHEUS_SIDECAR_NAME_PREFIXES: Tuple[str, ...] = (
        "node_",
        "scrape_",
        "process_",
        "promhttp_",
        "go_",
    )
    OTEL_PROMETHEUS_SIDECAR_EXACT_NAMES: Tuple[str, ...] = ("up",)

    # Source of truth on the DUT for the expected OTLP metric names.
    METRICS_CLASSES_PATH_ON_SWITCH = "/etc/nv-umf-manager/metrics-classes.yaml"
    METRICS_CLASSES_STAGED_ON_DUT = "/tmp/ngts-metrics-classes.yaml"
    METRICS_CLASSES_CANDIDATE_PATHS = (
        METRICS_CLASSES_PATH_ON_SWITCH,
        "/usr/share/nv-umf-manager/metrics-classes.yaml",
        "/usr/lib/nv-umf-manager/metrics-classes.yaml",
        "/opt/mellanox/nv-umf-manager/metrics-classes.yaml",
    )

    # NVOS-only: UMF agent mapping contract (metric type + attribute labels per metric).
    # The NVOS equivalent of the Cumulus attribute-count / value-type checks.
    AGENT_MAPPINGS_PATH_ON_SWITCH = (
        "/etc/nv-umf-agent/mappings/umf-agent/agent-mappings.yaml"
    )
    AGENT_MAPPINGS_STAGED_ON_DUT = "/tmp/ngts-agent-mappings.yaml"
    AGENT_MAPPINGS_CANDIDATE_PATHS = (AGENT_MAPPINGS_PATH_ON_SWITCH,)

    # `metrics-classes.yaml` group-name prefixes used for ``startswith`` matching.
    # For most NVUE subtrees the YAML group name *is* the NVUE name (or starts with
    # it), so we can reuse ``TelemetryConsts.*`` directly:
    #   - ``interface-stats`` covers ``interface-stats`` and ``interface-stats-phy``
    #   - ``platform-stats``  covers all ``platform-stats-*`` subgroups
    #     (cpu / disk / memory / health-info / asic-power / platform-info /
    #     environment-sensor / transceiver-info)
    #   - ``ib-router-stats`` covers ``ib-router-stats``
    # The peer-port subtree is asymmetric: the YAML splits it into two sibling
    # groups, ``peer-port-stats`` AND ``peer-port-phy-stats``. ``peer-port-phy-stats``
    # does NOT start with ``peer-port-stats`` (it diverges at the 11th character),
    # so we must use the shorter shared prefix ``peer-port`` to capture both groups.
    # Using ``TelemetryConsts.PEER_PORT_STATS`` here would silently drop every
    # ``nvswitch_peer_port_phy_*`` metric from the expected set.
    _PEER_PORT_METRICS_GROUP_PREFIX = "peer-port"

    METRICS_CLASSES_PLATFORM_STATS_GROUP_PREFIXES = (TelemetryConsts.PLATFORM_STATS,)
    METRICS_CLASSES_FULL_EXPORT_GROUP_PREFIXES = (
        TelemetryConsts.INTERFACE_STATS,
        _PEER_PORT_METRICS_GROUP_PREFIX,
        TelemetryConsts.PLATFORM_STATS,
        TelemetryConsts.IB_ROUTER_STATS,
    )

    # When the capability is ABSENT on the DUT, expected names starting with any of the listed
    # prefixes are removed from the *expected* set before strict equality.
    OTLP_METRIC_NAME_PREFIXES_GATED_BY_CAPABILITY: Dict[str, Tuple[str, ...]] = {
        OtelCapability.HAS_CONNECTED_TRANSCEIVERS: ("nvswitch_platform_transceiver_",),
        OtelCapability.HAS_IB_ROUTER_PROFILE: ("nvswitch_ib_router_",),
        OtelCapability.SUPPORTS_PEER_PORT_STATS: ("nvswitch_peer_port_",),
    }

    # NVOS exports these even when the ib-routing profile is disabled; do not gate them out.
    OTLP_IB_ROUTER_METRICS_ALWAYS_PRESENT: Tuple[str, ...] = (
        "nvswitch_ib_router_enabled",
        "nvswitch_ib_router_swid_count",
    )

    # Exact metric names removed from expected when the linked capability is absent.
    OTLP_METRIC_NAMES_GATED_BY_CAPABILITY: Dict[str, Tuple[str, ...]] = {
        OtelCapability.SUPPORTS_NVLINK_PLATFORM_METRICS: (
            "nvswitch_platform_asic_avg_power",
            "nvswitch_platform_environment_leak_sensor_status",
        ),
    }

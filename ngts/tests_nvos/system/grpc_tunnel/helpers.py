"""Shared helpers for grpc-tunnel tests: multi-collector setup and lifecycle."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import ngts.tools.test_utils.allure_utils as allure
from ngts.tests_nvos.system.grpc_tunnel.constants import GrpcTunnelConstants
from ngts.tests_nvos.system.grpc_tunnel.grpcTunnelServer import GrpcTunnelServer


@dataclass
class GrpcTunnelServerSetup:
    """One NVUE grpc-tunnel server entry and its matching dial-out collector."""

    tunnel_name: str
    listen_port: int
    collector: GrpcTunnelServer


@dataclass(frozen=True)
class GrpcTunnelExpectation:
    """Expected show fields for one configured grpc-tunnel server."""

    tunnel_name: str
    address: str
    port: int
    connection_status: str


def create_grpc_tunnels(
    system: Any,
    server: Any,
    *,
    count: int = 10,
) -> Tuple[List[GrpcTunnelServerSetup], List[GrpcTunnelExpectation]]:
    """Create ``count`` NVUE grpc-tunnel servers and matching dial-out collectors on ``server``."""
    tunnel_setups: List[GrpcTunnelServerSetup] = []
    all_tunnel_expectations: List[GrpcTunnelExpectation] = []
    for i in range(count):
        new_tunnel_name = f"testing_{i}"
        tunnel_listen_port = random.randint(49152, 65535)
        system.grpc_tunnel.server.set_new_tunnel(tunnel_name=new_tunnel_name)
        system.grpc_tunnel.server.tunnel_name[new_tunnel_name].set(
            op_param_name=GrpcTunnelConstants.ADDRESS, op_param_value=server.ip
        )
        system.grpc_tunnel.server.tunnel_name[new_tunnel_name].set(
            op_param_name=GrpcTunnelConstants.PORT,
            op_param_value=str(tunnel_listen_port),
            apply=True,
        )
        collector = GrpcTunnelServer(
            username="admin",
            password="admin",
            tunnel_address=f":{tunnel_listen_port}",
            tunnel_name=new_tunnel_name,
            server=server,
        )
        tunnel_setups.append(
            GrpcTunnelServerSetup(
                tunnel_name=new_tunnel_name,
                listen_port=tunnel_listen_port,
                collector=collector,
            )
        )
        all_tunnel_expectations.append(
            GrpcTunnelExpectation(
                tunnel_name=new_tunnel_name,
                address=server.ip,
                port=tunnel_listen_port,
                connection_status="no",
            )
        )
    return tunnel_setups, all_tunnel_expectations


def _tunnel_setups_subset(
    setups: Sequence[GrpcTunnelServerSetup],
    indices: Optional[Sequence[int]],
) -> List[GrpcTunnelServerSetup]:
    if indices is None:
        return list(setups)
    return [setups[i] for i in indices]


def prepare_tunnel_collectors(setups: Sequence[GrpcTunnelServerSetup]) -> None:
    for s in setups:
        s.collector.prepare_with_tls()


def subscribe_tunnel_collectors(
    setups: Sequence[GrpcTunnelServerSetup],
    *,
    indices: Optional[Sequence[int]] = None,
    **subscribe_kwargs,
) -> None:
    """Start gnmic subscribe on each selected setup (default: all). Pass subscribe() kwargs."""
    for s in _tunnel_setups_subset(setups, indices):
        s.collector.subscribe(**subscribe_kwargs)


def stop_tunnel_subscriptions(
    setups: Sequence[GrpcTunnelServerSetup],
    *,
    indices: Optional[Sequence[int]] = None,
) -> None:
    with allure.step("stop tunnels subscriptions"):
        for s in _tunnel_setups_subset(setups, indices):
            s.collector.stop_subscription()


def delete_tunnel_collectors(
    setups: Sequence[GrpcTunnelServerSetup],
    *,
    indices: Optional[Sequence[int]] = None,
) -> None:
    for s in _tunnel_setups_subset(setups, indices):
        s.collector.delete()


def validate_grpc_tunnel_docker_ps(
    engine: Any,
    *,
    tunnel_names: Optional[Sequence[str]] = None,
) -> None:
    """
    When no tunnels are configured, expect base NVOS containers (``nv-umf``, ``nv-gnmi``) and
    no ``nv-grpctunnel-*`` instances. When tunnels are configured, expect exactly
    ``nv-grpctunnel-<name>`` for each server name and no other ``nv-grpctunnel-*`` containers.
    """
    out = engine.run_cmd("docker ps --format '{{.Names}}'", validate=True)
    running = {line.strip() for line in out.splitlines() if line.strip()}
    prefix = GrpcTunnelConstants.GRPC_TUNNEL_DOCKER_PREFIX
    grpc_tunnel_running = {n for n in running if n.startswith(prefix)}

    if not tunnel_names:
        assert GrpcTunnelConstants.DOCKER_NV_UMF in running, (
            f"Expected {GrpcTunnelConstants.DOCKER_NV_UMF!r} running; docker ps names: {sorted(running)}"
        )
        assert GrpcTunnelConstants.DOCKER_NV_GNMI in running, (
            f"Expected {GrpcTunnelConstants.DOCKER_NV_GNMI!r} running; docker ps names: {sorted(running)}"
        )
        assert not grpc_tunnel_running, (
            "Expected no gRPC tunnel client containers when no tunnel servers are configured; found: "
            f"{sorted(grpc_tunnel_running)} (all running: {sorted(running)})"
        )
        return

    expected = {f"{prefix}{name}" for name in tunnel_names}
    missing = expected - running
    assert not missing, (
        f"Missing gRPC tunnel docker(s): {sorted(missing)}. "
        f"docker ps --format names: {sorted(running)}"
    )
    extra = grpc_tunnel_running - expected
    assert not extra, (
        f"Unexpected nv-grpctunnel container(s): {sorted(extra)}; "
        f"expected exactly {sorted(expected)}"
    )


# Keys omitted from equality checks (timestamps/peers vary by run and topology).
_TUNNEL_COMPARE_SKIP_KEYS = frozenset({"established", "local-port", "local-address"})


def _without_established(obj: Any) -> Any:
    """Return ``obj`` recursively without keys that should not affect test assertions."""
    if isinstance(obj, dict):
        return {
            k: _without_established(v)
            for k, v in obj.items()
            if k not in _TUNNEL_COMPARE_SKIP_KEYS
        }
    if isinstance(obj, list):
        return [_without_established(v) for v in obj]
    return obj


def build_expected_tunnel_output(
    *,
    address: str,
    port: int,
    connection_status: str,
) -> Dict[str, Any]:
    """Build expected NVUE JSON payload for one tunnel."""
    connected = connection_status == "yes"
    return {
        "address": address,
        "port": int(port),
        "retry-interval": 60,
        "state": "enabled",
        "status": {
            "connection": {
                "register": connection_status,
                "tunnel": connection_status,
            },
            "local-address": "",
            "local-port": 0,
            "remote-address": address if connected else "",
            "remote-port": int(port) if connected else 0,
        },
        "target-name": None,
        "target-type": "gnmi-gnoi",
    }


def build_expected_tunnels_map(
    expectations: Sequence[GrpcTunnelExpectation],
) -> Dict[str, Dict[str, Any]]:
    """Build expected NVUE JSON map keyed by tunnel name for all tunnels."""
    return {
        e.tunnel_name: build_expected_tunnel_output(
            address=e.address,
            port=e.port,
            connection_status=e.connection_status,
        )
        for e in expectations
    }

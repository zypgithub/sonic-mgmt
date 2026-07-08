"""gNMI dial-out coexistence helpers (SSIM ``test_telemetry_coexistence.py`` parity on mlx lab)."""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pytest

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_tools.infra.EngineAdapterTool import EngineAdapterTool
from ngts.tests_nvos.system.grpc_tunnel.grpcTunnelServer import GrpcTunnelServer
from ngts.tests_nvos.system.grpc_tunnel.helpers import GrpcTunnelServerSetup
from ngts.tests_nvos.system.telemetry.otel.cumulus import cache as telemetryCache
from ngts.tests_nvos.system.telemetry.otel.cumulus.helpers import dut_root_on_nvme_storage
from ngts.tests_nvos.system.telemetry.otel.cumulus.lab_topology import (
    discover_swp_interfaces_on_dut,
    resolve_cumulus_lab_interfaces_on_dut,
)

logger = logging.getLogger(__name__)

# SSIM smoke dial-out ports (``Test_Telemetry_Coexistence_Smoke``).
SMOKE_GNMI_PORT_LLDP = 57358
SMOKE_GNMI_PORT_BGP = 57713

SMOKE_BGP_ATTRS: Tuple[str, ...] = (
    'established_transitions', 'input_queue', 'messages_received', 'messages_sent', 'output_queue',
    'prefixes_installed', 'prefixes_received', 'prefixes_sent', 'session_state', 'local_as', 'last_established',
    'last_notification_error_code_sent', 'last_notification_error_code_received', 'peer_as', 'peer_type',
    'neighbor_add', 'description', 'peer_group',
)

SMOKE_LLDP_ATTRS: Tuple[str, ...] = (
    'lldp_state_enabled', 'interface_lldp_state_enabled', 'neighbor_ttl', 'neighbor_port_id_type',
    'chassis_id', 'chassis_id_type', 'system_name', 'system_description', 'neighbor_age', 'neighbor_port_id',
    'neighbor_chassis_id', 'neighbor_chassis_id_type', 'neighbor_system_name', 'neighbor_system_description',
    'neighbor_management_address_type', 'neighbor_port_description', 'neighbor_router', 'neighbor_telephone',
    'neighbor_other', 'neighbor_repeater', 'neighbor_mac_bridge', 'neighbor_wlan_access_point',
    'neighbor_docsis_cable_device', 'neighbor_station_only', 'neighbor_c_vlan', 'neighbor_s_vlan',
    'neighbor_two_port_mac_relay',
)

INTERFACE_QOS_GNMI_ATTRS: Tuple[str, ...] = (
    'in_broadcast_pkts', 'in_multicast_pkts', 'in_octets', 'in_errors',
)

SYSTEM_GNMI_ATTRS: Tuple[str, ...] = ('cp_out_ipv4_pkts', 'cp_out_ipv6_pkts')

COMPONENT_GNMI_ATTRS: Tuple[str, ...] = ('storage_read_bytes', 'storage_write_seconds')

_GNMI_JSON_DECODER = json.JSONDecoder()
_GNMIC_INSTALL_VERSION = '0.38.2'


@dataclass
class GnmiCollectionJob:
    """One grpc-tunnel + gnmic sample subscription."""

    model: str
    tunnel_name: str
    listen_port: int
    paths: List[str]
    sample_interval: str
    duration_sec: int
    attrs: Tuple[str, ...] = ()
    populate_kwargs: Dict[str, Any] = field(default_factory=dict)
    group_size: int = 1


@dataclass
class GnmiCoexistenceSession:
    setups: List[GrpcTunnelServerSetup] = field(default_factory=list)
    gnmic_bin: str = 'gnmic'
    mtls_configured: bool = False


def _address_family_key(afi_safi_name: str) -> str:
    if afi_safi_name == 'L2VPN_EVPN':
        return 'l2vpn-evpn'
    if afi_safi_name == 'IPV6_UNICAST':
        return 'ipv6-unicast'
    return 'ipv4-unicast'


def _bgp_xpath(attr: str, *, vrf: str, neighbor_address: str, afi_safi_name: str) -> Optional[str]:
    base = (
        f'/network-instances/network-instance[name={vrf}]/protocols/protocol[identifier=BGP][name=BGP]'
        f'/bgp/neighbors/neighbor[neighbor-address={neighbor_address}]'
    )
    af_key = _address_family_key(afi_safi_name)
    mapping = {
        'prefixes_received': f'{base}/afi-safis/afi-safi[afi-safi-name={afi_safi_name}]/state/prefixes/received',
        'prefixes_installed': f'{base}/afi-safis/afi-safi[afi-safi-name={afi_safi_name}]/state/prefixes/installed',
        'prefixes_sent': f'{base}/afi-safis/afi-safi[afi-safi-name={afi_safi_name}]/state/prefixes/sent',
        'established_transitions': f'{base}/state/established-transitions',
        'messages_sent': f'{base}/state/messages/sent/UPDATE',
        'messages_received': f'{base}/state/messages/received/UPDATE',
        'session_state': f'{base}/state/session-state',
        'input_queue': f'{base}/state/queues/input',
        'output_queue': f'{base}/state/queues/output',
        'last_established': f'{base}/state/last-established',
        'local_as': f'{base}/state/local-as',
        'peer_as': f'{base}/state/peer-as',
        'description': f'{base}/state/description',
        'peer_group': f'{base}/state/peer-group',
        'peer_type': f'{base}/state/peer-type',
        'last_notification_error_code_sent': f'{base}/state/messages/sent/last-notification-error-code',
        'last_notification_error_code_received': f'{base}/state/messages/received/last-notification-error-code',
        'neighbor_add': f'{base}/state/neighbor-address',
    }
    return mapping.get(attr)


def _lldp_xpath(attr: str, *, interface: str, neighbor_id: str, port: str, mgmt_address: Optional[str]) -> Optional[str]:
    nb = f'/lldp/interfaces/interface[name={interface}]/neighbors/neighbor[id={neighbor_id}:{port}]'
    mgmt = mgmt_address or '0.0.0.0'
    mapping = {
        'lldp_state_enabled': '/lldp/state/enabled',
        'interface_lldp_state_enabled': f'/lldp/interfaces/interface[name={interface}]/state/enabled',
        'chassis_id': '/lldp/state/chassis-id',
        'chassis_id_type': '/lldp/state/chassis-id-type',
        'system_description': '/lldp/state/system-description',
        'system_name': '/lldp/state/system-name',
        'neighbor_age': f'{nb}/state/age',
        'neighbor_port_id': f'{nb}/state/port-id',
        'neighbor_chassis_id': f'{nb}/state/chassis-id',
        'neighbor_chassis_id_type': f'{nb}/state/chassis-id-type',
        'neighbor_system_name': f'{nb}/state/system-name',
        'neighbor_system_description': f'{nb}/state/system-description',
        'neighbor_management_address_type': f'{nb}/state/management-addresses[address={mgmt}]/type',
        'neighbor_port_description': f'{nb}/state/port-description',
        'neighbor_port_id_type': f'{nb}/state/port-id-type',
        'neighbor_ttl': f'{nb}/state/ttl',
        'neighbor_router': f'{nb}/capabilities/capability[name=ROUTER]/state/enabled',
        'neighbor_telephone': f'{nb}/capabilities/capability[name=TELEPHONE]/state/enabled',
        'neighbor_other': f'{nb}/capabilities/capability[name=OTHER]/state/enabled',
        'neighbor_repeater': f'{nb}/capabilities/capability[name=REPEATER]/state/enabled',
        'neighbor_mac_bridge': f'{nb}/capabilities/capability[name=MAC_BRIDGE]/state/enabled',
        'neighbor_wlan_access_point': f'{nb}/capabilities/capability[name=WLAN_ACCESS_POINT]/state/enabled',
        'neighbor_docsis_cable_device': f'{nb}/capabilities/capability[name=DOCSIS_CABLE_DEVICE]/state/enabled',
        'neighbor_station_only': f'{nb}/capabilities/capability[name=STATION_ONLY]/state/enabled',
        'neighbor_c_vlan': f'{nb}/capabilities/capability[name=C_VLAN]/state/enabled',
        'neighbor_s_vlan': f'{nb}/capabilities/capability[name=S_VLAN]/state/enabled',
        'neighbor_two_port_mac_relay': f'{nb}/capabilities/capability[name=TWO_PORT_MAC_RELAY]/state/enabled',
    }
    return mapping.get(attr)


def _interface_xpath(attr: str, *, interface: str) -> Optional[str]:
    mapping = {
        'in_broadcast_pkts': f'/interfaces/interface[name={interface}]/state/counters/in-broadcast-pkts',
        'in_multicast_pkts': f'/interfaces/interface[name={interface}]/state/counters/in-multicast-pkts',
        'in_octets': f'/interfaces/interface[name={interface}]/state/counters/in-octets',
        'in_errors': f'/interfaces/interface[name={interface}]/state/counters/in-errors',
    }
    return mapping.get(attr)


def _system_xpath(attr: str) -> Optional[str]:
    mapping = {
        'cp_out_ipv4_pkts': '/system/control-plane-traffic/egress/ipv4/counters/out-ipv4-pkts',
        'cp_out_ipv6_pkts': '/system/control-plane-traffic/egress/ipv6/counters/out-ipv6-pkts',
    }
    return mapping.get(attr)


def _component_xpath(attr: str, *, component_name: str) -> Optional[str]:
    mapping = {
        'storage_read_bytes': f'/components/component[name={component_name}]/storage/state/counters/read-bytes',
        'storage_write_seconds': f'/components/component[name={component_name}]/storage/state/counters/write-seconds',
    }
    return mapping.get(attr)


def resolve_model_xpaths(model: str, attrs: Sequence[str], populate_kwargs: Dict[str, Any]) -> List[str]:
    """Map SSIM attr names to OpenConfig/Cumulus subscribe paths."""
    paths: List[str] = []
    kwargs = populate_kwargs or {}
    for attr in attrs or []:
        xp = None
        if model == 'bgp':
            xp = _bgp_xpath(
                attr,
                vrf=kwargs.get('vrf', 'default'),
                neighbor_address=kwargs['neighbor_address'],
                afi_safi_name=kwargs.get('afi_safi_name', 'IPV4_UNICAST'),
            )
        elif model == 'lldp':
            xp = _lldp_xpath(
                attr,
                interface=kwargs['interface'],
                neighbor_id=kwargs['neighbor_id'],
                port=kwargs.get('port', kwargs['interface']),
                mgmt_address=kwargs.get('mgmt_address'),
            )
        elif model == 'interface':
            xp = _interface_xpath(attr, interface=kwargs['interface'])
        elif model == 'system':
            xp = _system_xpath(attr)
        elif model == 'component':
            xp = _component_xpath(attr, component_name=kwargs['component_name'])
        if xp and xp not in paths:
            paths.append(xp)
    return paths


def _parse_json_objects_from_gnmic_log(content: str) -> List[Dict[str, Any]]:
    """Extract top-level JSON objects from gnmic ``-d`` output (SSIM ``multilinedict_to_listofdict``)."""
    objects: List[Dict[str, Any]] = []
    idx = 0
    length = len(content)
    while idx < length:
        pos = content.find('{', idx)
        if pos == -1:
            break
        if pos != 0 and content[pos - 1] != '\n':
            idx = pos + 1
            continue
        try:
            obj, end_idx = _GNMI_JSON_DECODER.raw_decode(content, pos)
            if isinstance(obj, dict):
                objects.append(obj)
            idx = end_idx
        except json.JSONDecodeError:
            next_nl = content.find('\n', pos)
            if next_nl == -1:
                break
            idx = next_nl + 1
    return objects


def _is_sync_response(obj: Dict[str, Any]) -> bool:
    return bool(obj.get('sync_response'))


def _notification_timestamp(obj: Dict[str, Any]) -> Optional[int]:
    for key in ('timestamp', 'time'):
        if key in obj:
            try:
                raw = int(obj[key])
            except (TypeError, ValueError):
                continue
            if raw > 1_000_000_000_000:
                return raw // 1_000_000_000
            return raw
    return None


def _combine_prefix_path(prefix: str, path: str) -> str:
    pfx = (prefix or '').strip('/')
    pth = (path or '').strip('/')
    if pfx and pth:
        return f'/{pfx}/{pth}'
    if pfx:
        return f'/{pfx}'
    if pth:
        return f'/{pth}' if pth.startswith('/') else f'/{pth}'
    return ''


def _extract_updates(obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    prefix = obj.get('prefix', '')
    updates = obj.get('updates') or []
    if not isinstance(updates, list):
        return out
    for upd in updates:
        if not isinstance(upd, dict):
            continue
        path = upd.get('Path') or upd.get('path') or ''
        if prefix:
            xpath = _combine_prefix_path(str(prefix), str(path))
        else:
            xpath = str(path) if str(path).startswith('/') else f'/{path}'
        if not xpath:
            continue
        values = upd.get('values') or upd.get('val') or {}
        entry: Dict[str, Any] = {'xpath': xpath}
        if isinstance(values, dict):
            entry.update(values)
        out[xpath] = entry
    return out


def parse_gnmic_log_to_series(log_content: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Build ``gnmi-series-{model}`` shape: ``{timestamp: {xpath: entry}}``."""
    series: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for obj in _parse_json_objects_from_gnmic_log(log_content or ''):
        if _is_sync_response(obj):
            continue
        ts = _notification_timestamp(obj)
        if ts is None:
            continue
        ts_key = str(ts)
        entries = _extract_updates(obj)
        if not entries:
            continue
        bucket = series.setdefault(ts_key, {})
        for xpath, entry in entries.items():
            bucket[xpath] = entry
    return series


def _parse_interval_to_seconds(sample_interval: Any) -> Optional[float]:
    if sample_interval is None:
        return None
    if isinstance(sample_interval, (int, float)):
        return float(sample_interval)
    text = str(sample_interval).strip().lower()
    if text.endswith('s'):
        try:
            return float(text[:-1])
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def validate_gnmi_sample_interval_per_timestamp(
    *,
    models: Sequence[str],
    sample_interval: Any,
    tolerance: float = 0.25,
    series_key_prefix: str = 'gnmi-series-',
    cache_key: str = 'gnmi_timing',
) -> None:
    """SSIM ``validate_gnmi_sample_interval_per_timestamp`` (stores summary in cache)."""
    s_sec = _parse_interval_to_seconds(sample_interval)
    assert s_sec is not None, 'Invalid sample_interval: %s' % (sample_interval,)
    if tolerance < 1:
        min_gap = s_sec * (1 - tolerance)
        max_gap = s_sec * (1 + tolerance)
    else:
        min_gap = s_sec - tolerance
        max_gap = s_sec + tolerance

    results: Dict[str, Any] = {}
    failures: List[str] = []
    for model in models or []:
        series_key = '%s%s' % (series_key_prefix, model)
        try:
            series = telemetryCache.get_data(series_key)
        except KeyError:
            series = None

        model_result: Dict[str, Any] = {
            'model': model,
            'expected': {
                'sample_interval': s_sec,
                'tolerance': tolerance,
                'min_gap': min_gap,
                'max_gap': max_gap,
            },
        }
        if not isinstance(series, dict) or not series:
            model_result['result'] = 'fail'
            model_result['error'] = 'Missing or empty GNMI series for %s' % (model,)
            results[model] = model_result
            failures.append(model_result['error'])
            continue

        ts_keys: List[int] = []
        for key in series:
            try:
                ts_keys.append(int(key))
            except (TypeError, ValueError):
                continue
        ts_keys = sorted(set(ts_keys))
        if len(ts_keys) < 2:
            model_result['result'] = 'fail'
            model_result['error'] = '%s GNMI series has too few timestamps (%d)' % (model, len(ts_keys))
            results[model] = model_result
            failures.append(model_result['error'])
            continue

        ts_scale = 1_000_000_000 if max(ts_keys) > 1_000_000_000_000 else 1
        violations = []
        for prev_ts, cur_ts in zip(ts_keys[:-1], ts_keys[1:]):
            gap_s = (cur_ts - prev_ts) / ts_scale
            if gap_s < min_gap or gap_s > max_gap:
                violations.append({'prev_ts': prev_ts, 'cur_ts': cur_ts, 'gap_s': gap_s})
        if violations:
            model_result['result'] = 'fail'
            model_result['violations'] = violations
            failures.append('%s sample interval violations: %d' % (model, len(violations)))
        else:
            model_result['result'] = 'pass'
        results[model] = model_result

    try:
        existing = telemetryCache.get_data(cache_key)
    except KeyError:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing.update(results)
    telemetryCache.add_data(cache_key, existing)
    if failures:
        pytest.fail('GNMI per-timestamp interval violations: %s' % (failures,))


def validate_xpath_coverage_per_timestamp(
    *,
    model: str,
    attrs: Sequence[str],
    populate_kwargs: Optional[Dict[str, Any]] = None,
    series_key: Optional[str] = None,
    group_size: Optional[int] = None,
) -> None:
    """SSIM strict xpath coverage using cached ``gnmi-series-{model}``."""
    populate_kwargs = populate_kwargs or {}
    with allure.step('Resolve expected gNMI xpaths (model=%s)' % (model,)):
        expected_xpaths = resolve_model_xpaths(model, attrs, populate_kwargs)
        assert expected_xpaths, "No xpaths resolved for model '%s'" % (model,)
        allure.attach(
            '\n'.join(expected_xpaths),
            'expected_xpaths',
        )

    s_key = series_key or 'gnmi-series-%s' % (model,)
    with allure.step('Load %s from telemetry cache' % (s_key,)):
        try:
            gnmi_series = telemetryCache.get_data(s_key)
        except KeyError:
            gnmi_series = None
        assert isinstance(gnmi_series, dict) and gnmi_series, 'Missing or empty %s in telemetry cache' % (s_key,)
        allure.attach(
            'timestamps=%d populate_kwargs=%r attrs=%r'
            % (len(gnmi_series), populate_kwargs, list(attrs)),
            'gnmi_series_summary',
        )

    if isinstance(group_size, int) and group_size > 0:
        effective_group_size = group_size
    elif model == 'lldp':
        effective_group_size = 6
    elif model in ('bgp', 'interface'):
        effective_group_size = 2
    else:
        effective_group_size = 1

    def _normalize(xpath: str) -> str:
        return xpath[1:] if xpath.startswith('/') else xpath

    series_items = list(gnmi_series.items())
    failures: Dict[str, List[str]] = {}

    with allure.step(
        'Validate xpath coverage per timestamp (group_size=%d, %d timestamps)'
        % (effective_group_size, len(series_items))
    ):
        if effective_group_size <= 1:
            for ts, entries in series_items:
                present = set()
                for key, val in (entries or {}).items():
                    if isinstance(key, str):
                        present.add(key)
                        present.add(_normalize(key))
                    if isinstance(val, dict) and val.get('xpath'):
                        present.add(val['xpath'])
                        present.add(_normalize(val['xpath']))
                missing = [
                    xp for xp in expected_xpaths
                    if xp not in present and _normalize(xp) not in present
                ]
                if missing:
                    failures[str(ts)] = missing
        else:
            total = len(series_items)
            for i in range(total):
                start = max(0, i - (effective_group_size - 1))
                window = series_items[start: i + 1]
                union_present = set()
                for _, entries in window:
                    for key, val in (entries or {}).items():
                        if isinstance(key, str):
                            union_present.add(key)
                            union_present.add(_normalize(key))
                        if isinstance(val, dict) and val.get('xpath'):
                            union_present.add(val['xpath'])
                            union_present.add(_normalize(val['xpath']))
                missing = [
                    xp for xp in expected_xpaths
                    if xp not in union_present and _normalize(xp) not in union_present
                ]
                if missing:
                    failures[str(series_items[i][0])] = missing

        if failures:
            allure.attach(str(failures), 'xpath_coverage_failures')
            pytest.fail(
                'XPath coverage failures for %s (%d timestamps): %s'
                % (model, len(failures), failures)
            )
        allure.attach(
            'all %d timestamps satisfied %d xpaths (group_size=%d)'
            % (len(series_items), len(expected_xpaths), effective_group_size),
            'xpath_coverage_ok',
        )


def discover_bgp_neighbor_address(dut, *, vrf: str = 'default') -> Optional[str]:
    """Return first BGP neighbor address from NVUE show (mlx lab)."""
    out = dut.run_cmd(
        'nv show vrf %s router bgp neighbor -o json 2>&1' % (vrf,),
        validate=False,
        print_output=False,
    )
    if 'error:' in out.lower():
        return None
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not payload:
        return None
    for neighbor in sorted(payload.keys()):
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', neighbor) or ':' in neighbor:
            return neighbor
    return None


def discover_lldp_neighbor_context(dut, *, preferred_iface: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Discover first LLDP neighbor on a front-panel interface."""
    candidates: List[str] = []
    if preferred_iface:
        candidates.append(preferred_iface)
    candidates.extend(discover_swp_interfaces_on_dut(dut))
    seen = set()
    for iface in candidates:
        if iface in seen:
            continue
        seen.add(iface)
        out = dut.run_cmd(
            'nv show interface %s lldp neighbor -o json 2>&1' % (iface,),
            validate=False,
            print_output=False,
        )
        if 'error:' in out.lower() or 'does not exist' in out.lower():
            continue
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or not payload:
            continue
        for neighbor_key in payload:
            neighbor_id, _, port = neighbor_key.partition(':')
            if not neighbor_id:
                neighbor_id = neighbor_key
                port = iface
            mgmt_address = None
            neighbor_obj = payload.get(neighbor_key) or {}
            chassis = neighbor_obj.get('chassis') or {}
            mgmt_ifinfo = chassis.get('management-ifinfo') or {}
            if isinstance(mgmt_ifinfo, dict):
                for _, entry in mgmt_ifinfo.items():
                    if isinstance(entry, dict):
                        mgmt_address = entry.get('management-address-ipv4') or entry.get('management-address-ipv6')
                        if mgmt_address:
                            break
            return {
                'interface': iface,
                'neighbor_id': neighbor_id,
                'port': port or iface,
                'mgmt_address': mgmt_address,
            }
    return None


def discover_storage_component_name(dut) -> str:
    """Return a storage component name for component gNMI (``nvme*`` or ``sda``)."""
    if dut_root_on_nvme_storage(dut):
        out = dut.run_cmd("ls /sys/block 2>/dev/null | grep -E '^nvme' | head -1", validate=False)
        name = (out or '').strip().splitlines()[0] if out else ''
        if name:
            return name
    out = dut.run_cmd(
        'nv show system platform component -o json 2>&1',
        validate=False,
        print_output=False,
    )
    if 'error:' not in out.lower():
        try:
            payload = json.loads(out)
            if isinstance(payload, dict):
                for key in sorted(payload):
                    low = key.lower()
                    if 'nvme' in low or low.startswith('sd') or 'storage' in low:
                        return key
        except json.JSONDecodeError:
            pass
    return 'sda'


def ensure_gnmic_installed_on_collector(server) -> str:
    """Install ``gnmic`` on ``engines.sonic_mgmt`` when missing (grpc-tunnel dial-out)."""
    with allure.step('Ensure gnmic is installed on sonic-mgmt collector'):
        gnmic_bin = EngineAdapterTool.run_cmd(
            server,
            'command -v gnmic 2>/dev/null || true',
            timeout=30,
        ).strip()
        if gnmic_bin:
            logger.info('gnmic found on collector: %s', gnmic_bin)
            return gnmic_bin

        EngineAdapterTool.run_cmd(
            server,
            'bash -c "$(curl -sL https://get-gnmic.openconfig.net)" -- -v %s'
            % (_GNMIC_INSTALL_VERSION,),
            timeout=300,
        )
        gnmic_bin = EngineAdapterTool.run_cmd(
            server,
            'command -v gnmic 2>/dev/null || true',
            timeout=30,
        ).strip()
        if not gnmic_bin:
            pytest.fail(
                'gnmic not available on sonic-mgmt after install attempt; '
                'grpc-tunnel gNMI coexistence cannot run'
            )
        logger.info('gnmic installed on collector: %s', gnmic_bin)
        return gnmic_bin


def _collector_gnmic_base(collector: GrpcTunnelServer, gnmic_bin: str) -> str:
    """Like ``GrpcTunnelServer._gnmic_base`` but with an explicit remote gnmic path."""
    conf_dir = os.path.dirname(collector.config_path)
    conf_name = os.path.basename(collector.config_path)
    inner = '%s --config %s --use-tunnel-server' % (
        shlex.quote(gnmic_bin),
        shlex.quote(conf_name),
    )
    if conf_dir:
        return 'cd %s && %s' % (shlex.quote(conf_dir), inner)
    return inner


def _collector_gnmic_pkill_pattern(collector: GrpcTunnelServer) -> str:
    return 'gnmic --config %s' % (os.path.basename(collector.config_path),)


def _kill_stale_collector_gnmic(collector: GrpcTunnelServer) -> None:
    """Free the tunnel listen port; prior failed fixture setup may leave gnmic running."""
    assert collector.server is not None
    listen_port = GrpcTunnelServer.listen_port(collector.tunnel_address)
    pat = _collector_gnmic_pkill_pattern(collector)
    quoted = shlex.quote(pat)
    EngineAdapterTool.run_cmd(
        collector.server,
        (
            'pkill -INT -f %s 2>/dev/null || true; sleep 1; '
            'pkill -TERM -f %s 2>/dev/null || true; sleep 1; '
            'pkill -9 -f %s 2>/dev/null || true; '
            'fuser -k %d/tcp 2>/dev/null || true; sleep 1'
        ) % (quoted, quoted, quoted, listen_port),
        timeout=90,
    )


def _wait_for_collector_gnmic_listener(
    collector: GrpcTunnelServer,
    *,
    timeout_sec: int = 20,
) -> bool:
    """Return True when gnmic tunnel-server is listening on the configured port."""
    assert collector.server is not None
    listen_port = GrpcTunnelServer.listen_port(collector.tunnel_address)
    marker = ':%d' % (listen_port,)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        out = EngineAdapterTool.run_cmd(
            collector.server,
            (
                "ss -tln 2>/dev/null | grep -F '%s' || "
                "netstat -tln 2>/dev/null | grep -F '%s' || true"
            ) % (marker, marker),
            timeout=30,
        )
        if marker in (out or ''):
            return True
        time.sleep(1)
    return False


def _assert_collector_gnmic_listener(collector: GrpcTunnelServer, *, timeout_sec: int = 20) -> None:
    listen_port = GrpcTunnelServer.listen_port(collector.tunnel_address)
    if _wait_for_collector_gnmic_listener(collector, timeout_sec=timeout_sec):
        return
    assert collector.server is not None
    owners = EngineAdapterTool.run_cmd(
        collector.server,
        (
            "ss -tlnp 2>/dev/null | grep ':%d' || "
            "fuser %d/tcp 2>/dev/null || true"
        ) % (listen_port, listen_port),
        timeout=30,
    )
    pytest.fail(
        'gnmic tunnel-server not listening on :%d after %ds; port owners: %s'
        % (listen_port, timeout_sec, (owners or '').strip()[:500])
    )


def _dut_grpc_tunnel_unit(tunnel_name: str) -> str:
    return 'nv-grpctunneld@%s' % (tunnel_name,)


def _dut_grpc_tunnel_docker_name(tunnel_name: str) -> str:
    return 'nv-grpctunnel-%s' % (tunnel_name,)


def _resolve_dut_gnmi_basic_credentials(dut) -> Tuple[str, str]:
    """SSIM ``GnmiCollectorDialOut*`` uses the DUT NVUE user for gnmic Basic auth."""
    username = getattr(dut, 'username', None) or getattr(dut, 'default_username', None)
    password = getattr(dut, 'password', None) or getattr(dut, 'default_password', None)
    if not username or not password:
        try:
            from ngts.tools.TestToolkit import TestToolkit

            device = TestToolkit.devices.dut
            username = username or device.default_username
            password = password or device.default_password
        except Exception:
            pass
    if not username or not password:
        pytest.fail('Could not resolve DUT username/password for gnmic Basic auth (SSIM cumulus parity)')
    return str(username), str(password)


def _dut_grpc_tunnel_cfg_path(tunnel_name: str) -> str:
    return '/etc/nv-grpctunnel/config/%s.cfg' % (tunnel_name,)


def _dut_shell_lines(text: str) -> list:
    """Non-empty stripped lines from DUT shell output (ignores bash teardown noise)."""
    return [ln.strip() for ln in (text or '').splitlines() if ln.strip()]


def _parse_dut_json_output(text: str) -> Optional[Dict[str, Any]]:
    """Return the first JSON object embedded in DUT shell output."""
    content = text or ''
    pos = content.find('{')
    while pos != -1:
        try:
            obj, _end = _GNMI_JSON_DECODER.raw_decode(content, pos)
        except json.JSONDecodeError:
            pos = content.find('{', pos + 1)
            continue
        if isinstance(obj, dict):
            return obj
        pos = content.find('{', pos + 1)
    return None


def _systemctl_is_active(dut, unit: str) -> str:
    """Return systemctl state; cumulus shells may append unrelated bash errors after the state line."""
    out = dut.run_cmd('systemctl is-active %s' % (unit,), validate=False) or ''
    for line in _dut_shell_lines(out):
        if line in ('active', 'activating', 'inactive', 'failed', 'dead', 'unknown'):
            return line
    return ''


def _assert_dut_grpc_tunnel_cfg_present(dut, tunnel_name: str) -> None:
    """``nv-grpctunneld@`` requires ``ConditionFileNotEmpty`` on the per-server cfg."""
    cfg = _dut_grpc_tunnel_cfg_path(tunnel_name)
    check = dut.run_cmd(
        'test -s %s && echo OK || echo MISSING' % (shlex.quote(cfg),),
        validate=False,
    ) or ''
    if 'OK' in check:
        return
    listing = dut.run_cmd(
        'ls -la /etc/nv-grpctunnel/config/ 2>/dev/null || true',
        validate=False,
    )
    pytest.fail(
        'gRPC tunnel client config %s missing after NVUE apply; '
        'nv-grpctunneld@%s was skipped (ConditionFileNotEmpty). '
        'config dir listing: %s'
        % (cfg, tunnel_name, (listing or '').strip()[:800])
    )


def _configure_dut_grpc_tunnel(
    dut,
    sonic_mgmt_ip: str,
    tunnel_name: str,
    listen_port: int,
    *,
    use_mtls: bool = True,
) -> None:
    """NVUE grpc-tunnel server; mTLS uses SSIM ``configure_grpc_tunnel_vx`` field parity."""
    if use_mtls:
        from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_dialout_mtls import (
            configure_dut_grpc_tunnel_mtls,
        )

        configure_dut_grpc_tunnel_mtls(dut, sonic_mgmt_ip, tunnel_name, listen_port)
    else:
        from ngts.nvos_tools.system.System import System
        from ngts.tests_nvos.system.grpc_tunnel.constants import GrpcTunnelConstants

        with allure.step('Configure grpc-tunnel server %s (NVUE API)' % (tunnel_name,)):
            system = System()
            system.grpc_tunnel.server.set_new_tunnel(tunnel_name=tunnel_name)
            system.grpc_tunnel.server.tunnel_name[tunnel_name].set(
                op_param_name=GrpcTunnelConstants.ADDRESS,
                op_param_value=sonic_mgmt_ip,
            )
            system.grpc_tunnel.server.tunnel_name[tunnel_name].set(
                op_param_name=GrpcTunnelConstants.PORT,
                op_param_value=str(listen_port),
                apply=True,
            )
    _assert_dut_grpc_tunnel_cfg_present(dut, tunnel_name)


def _unset_dut_grpc_tunnel(dut, tunnel_name: str) -> None:
    unit = _dut_grpc_tunnel_unit(tunnel_name)
    try:
        dut.run_cmd('sudo systemctl stop %s' % (unit,), validate=False)
    except Exception:
        pass
    try:
        from ngts.nvos_tools.system.System import System

        System().grpc_tunnel.server.tunnel_name[tunnel_name].unset(apply=True)
    except Exception as exc:
        logger.warning('grpc-tunnel unset %s: %s', tunnel_name, exc)


def _is_dut_grpc_tunnel_client_running(dut, tunnel_name: str) -> bool:
    unit = _dut_grpc_tunnel_unit(tunnel_name)
    state = _systemctl_is_active(dut, unit)
    if state in ('active', 'activating'):
        return True
    docker_name = _dut_grpc_tunnel_docker_name(tunnel_name)
    for ps_cmd in (
        "sudo docker ps --format '{{.Names}}'",
        "docker ps --format '{{.Names}}'",
    ):
        out = dut.run_cmd(
            '%s 2>/dev/null | grep -Fx %s || true' % (ps_cmd, docker_name),
            validate=False,
        ) or ''
        if docker_name in _dut_shell_lines(out):
            return True
    return False


def _start_dut_grpc_tunnel(dut, tunnel_name: str) -> None:
    """Start tunnel client; ``nv config apply`` alone may leave the unit inactive (dead)."""
    unit = _dut_grpc_tunnel_unit(tunnel_name)
    dut.run_cmd('sudo systemctl start %s' % (unit,), validate=False)
    deadline = time.time() + 20
    while time.time() < deadline:
        if _is_dut_grpc_tunnel_client_running(dut, tunnel_name):
            return
        time.sleep(2)
    journal = dut.run_cmd(
        'sudo journalctl -u %s -n 20 --no-pager 2>/dev/null || true' % (unit,),
        validate=False,
    )
    cfg = _dut_grpc_tunnel_cfg_path(tunnel_name)
    pytest.fail(
        'gRPC tunnel client %s not running after systemctl start (cfg=%s). journal: %s'
        % (tunnel_name, cfg, (journal or '').strip()[-800:])
    )


def _restart_dut_grpc_tunnel(dut, tunnel_name: str) -> None:
    """Force an immediate dial-out attempt after gnmic is listening (SSIM ``restart_grpctunnel``)."""
    unit = _dut_grpc_tunnel_unit(tunnel_name)
    if _systemctl_is_active(dut, unit) in ('active', 'activating'):
        dut.run_cmd('sudo systemctl restart %s' % (unit,), validate=False)
    else:
        _start_dut_grpc_tunnel(dut, tunnel_name)


def _grpc_tunnel_connection_status(dut, tunnel_name: str) -> Dict[str, str]:
    """Read ``register``/``tunnel`` from ``nv show system grpc-tunnel server``."""
    show_cmd = 'nv show system grpc-tunnel server %s -o json' % (tunnel_name,)
    out = dut.run_cmd(show_cmd, validate=False) or ''
    data = _parse_dut_json_output(out)
    if not isinstance(data, dict):
        return {}
    conn = (data.get('status') or {}).get('connection') or {}
    return {
        'register': str(conn.get('register') or ''),
        'tunnel': str(conn.get('tunnel') or ''),
    }


def _wait_for_grpc_tunnel_connection(
    dut,
    tunnel_name: str,
    *,
    timeout_sec: int = 45,
) -> bool:
    """Return True when ``nv show`` reports register/tunnel yes for the server."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        conn = _grpc_tunnel_connection_status(dut, tunnel_name)
        if conn.get('register') == 'yes' and conn.get('tunnel') == 'yes':
            return True
        time.sleep(3)
    return False


def _assert_grpc_tunnel_connected(
    dut,
    tunnel_name: str,
    *,
    listen_port: int,
    timeout_sec: int = 90,
) -> None:
    """Hard-fail when DUT grpc-tunnel client never registers with gnmic."""
    if _wait_for_grpc_tunnel_connection(dut, tunnel_name, timeout_sec=timeout_sec):
        logger.info('gRPC tunnel %s connected to gnmic on :%d', tunnel_name, listen_port)
        return
    conn = _grpc_tunnel_connection_status(dut, tunnel_name)
    unit = _dut_grpc_tunnel_unit(tunnel_name)
    journal = dut.run_cmd(
        'sudo journalctl -u %s -n 30 --no-pager 2>/dev/null || true' % (unit,),
        validate=False,
    )
    pytest.fail(
        'gRPC tunnel %s did not reach register/tunnel=yes within %ds (collector :%d). '
        'last status=%s journal tail: %s'
        % (
            tunnel_name,
            timeout_sec,
            listen_port,
            conn,
            (journal or '').strip()[-1200:],
        )
    )


def _setup_gnmi_dialout_mtls(dut, sonic_mgmt):
    """One-time mTLS cert exchange + gnmi-server enable (SSIM pre_suite dial-out stack)."""
    from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_dialout_mtls import (
        configure_dut_gnmi_server_mtls,
        generate_gnmi_dialout_mtls_material,
        install_gnmi_dialout_certs_on_dut,
        resolve_dut_ip,
        upload_collector_mtls_certs,
    )

    dut_ip = resolve_dut_ip(dut)
    material = generate_gnmi_dialout_mtls_material(
        collector_ip=sonic_mgmt.ip,
        dut_ip=dut_ip,
    )
    upload_collector_mtls_certs(sonic_mgmt, material)
    install_gnmi_dialout_certs_on_dut(dut, material, dut_ip=dut_ip)
    configure_dut_gnmi_server_mtls(dut, dut_ip=dut_ip)
    return material, dut_ip


def setup_gnmi_coexistence_session(
    dut,
    sonic_mgmt,
    jobs: Sequence[GnmiCollectionJob],
    *,
    use_mtls: bool = True,
) -> GnmiCoexistenceSession:
    """Create NVUE grpc-tunnel servers and gnmic collectors for each job."""
    from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_dialout_mtls import (
        GNMI_DIALOUT_TARGET_WAIT,
    )

    session = GnmiCoexistenceSession()
    session.gnmic_bin = ensure_gnmic_installed_on_collector(sonic_mgmt)
    gnmi_user, gnmi_pass = _resolve_dut_gnmi_basic_credentials(dut)
    mtls_material = None
    if use_mtls and jobs:
        mtls_material, _dut_ip = _setup_gnmi_dialout_mtls(dut, sonic_mgmt)
        session.mtls_configured = True

    configured_tunnels = set()
    with allure.step('Configure grpc-tunnel + gnmic dial-out collectors'):
        for job in jobs:
            if job.tunnel_name not in configured_tunnels:
                _configure_dut_grpc_tunnel(
                    dut,
                    sonic_mgmt.ip,
                    job.tunnel_name,
                    job.listen_port,
                    use_mtls=use_mtls,
                )
                configured_tunnels.add(job.tunnel_name)
            if use_mtls and mtls_material is not None:
                # SSIM GnmiCollectorDialOut* always sets skip_verify=True: tunneled target is
                # ``:9339`` (localhost) but gnmi-server cert SAN is the DUT management IP.
                _kill_stale_collector_gnmic(
                    GrpcTunnelServer(
                        username=gnmi_user,
                        password=gnmi_pass,
                        tunnel_address=':%d' % (job.listen_port,),
                        tunnel_name=job.tunnel_name,
                        server=sonic_mgmt,
                    )
                )
                collector = GrpcTunnelServer(
                    username=gnmi_user,
                    password=gnmi_pass,
                    tunnel_address=':%d' % (job.listen_port,),
                    tunnel_name=job.tunnel_name,
                    server=sonic_mgmt,
                    skip_verify=True,
                    target_wait_time=GNMI_DIALOUT_TARGET_WAIT,
                    tls_cert_file=mtls_material.remote_gnmic_target_crt,
                    tls_key_file=mtls_material.remote_gnmic_target_key,
                    tls_ca_file=mtls_material.remote_dut_ca_crt,
                    gnmi_tls_ca_file=mtls_material.remote_dut_ca_crt,
                    gnmi_tls_cert_file=mtls_material.remote_gnmic_client_crt,
                    gnmi_tls_key_file=mtls_material.remote_gnmic_client_key,
                )
                collector.write_config()
            else:
                collector = GrpcTunnelServer(
                    username=gnmi_user,
                    password=gnmi_pass,
                    tunnel_address=':%d' % (job.listen_port,),
                    tunnel_name=job.tunnel_name,
                    server=sonic_mgmt,
                )
                collector.prepare_with_tls()
            session.setups.append(
                GrpcTunnelServerSetup(
                    tunnel_name=job.tunnel_name,
                    listen_port=job.listen_port,
                    collector=collector,
                )
            )
            time.sleep(2)
    return session


def teardown_gnmi_coexistence_session(dut, session: GnmiCoexistenceSession) -> None:
    with allure.step('Teardown gNMI coexistence grpc-tunnels'):
        for setup in session.setups:
            try:
                setup.collector.stop_subscription()
            except Exception:
                pass
            try:
                setup.collector.delete()
            except Exception:
                pass
            _unset_dut_grpc_tunnel(dut, setup.tunnel_name)
        session.setups.clear()
        if session.mtls_configured:
            from ngts.tests_nvos.system.telemetry.otel.cumulus.gnmi_dialout_mtls import (
                _release_stale_gnmi_dialout_security,
            )

            _release_stale_gnmi_dialout_security(dut)
            session.mtls_configured = False


def _remote_gnmi_log_path(tunnel_name: str, model: str) -> str:
    return '/tmp/%s_gnmi_%s_sample.json' % (tunnel_name, model)


def _start_gnmic_sample_subscription(
    collector: GrpcTunnelServer,
    *,
    model: str,
    paths: Sequence[str],
    sample_interval: str,
    duration_sec: int,
    gnmic_bin: str = 'gnmic',
) -> str:
    out_path = _remote_gnmi_log_path(collector.tunnel_name, model)
    _kill_stale_collector_gnmic(collector)
    paths_cli = ' '.join('--path %s' % (shlex.quote(p),) for p in paths)
    mtls_suffix = collector.gnmi_mtls_cli_suffix()
    inner = (
        '%s%s -d subscribe --mode stream --stream-mode sample -i %s --encoding json %s '
        '> %s 2>&1'
    ) % (
        _collector_gnmic_base(collector, gnmic_bin),
        mtls_suffix,
        shlex.quote(sample_interval),
        paths_cli,
        shlex.quote(out_path),
    )
    start_cmd = (
        'OUT=%s; rm -f "$OUT"; nohup timeout --foreground %d bash -c %s >/dev/null 2>&1 &'
    ) % (shlex.quote(out_path), int(duration_sec), shlex.quote(inner))
    assert collector.server is not None
    EngineAdapterTool.run_cmd(collector.server, start_cmd, timeout=60)
    _assert_collector_gnmic_listener(collector, timeout_sec=25)
    return out_path


def _read_remote_file(server, path: str) -> str:
    return EngineAdapterTool.run_cmd(
        server,
        'cat %s 2>/dev/null || true' % (shlex.quote(path),),
        timeout=120,
    )


def _wait_for_remote_file(server, path: str, *, min_bytes: int = 64, timeout_sec: int = 30) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        out = EngineAdapterTool.run_cmd(
            server,
            'test -s %s && stat -c %%s %s || echo 0' % (shlex.quote(path), shlex.quote(path)),
            timeout=30,
        )
        try:
            if int((out or '0').strip().splitlines()[-1]) >= min_bytes:
                return
        except ValueError:
            pass
        time.sleep(2)


def _populate_gnmi_cache_from_session(
    sonic_mgmt,
    jobs: Sequence[GnmiCollectionJob],
    session: GnmiCoexistenceSession,
    out_paths: Dict[str, str],
) -> None:
    timing: Dict[str, Any] = {}
    for job, _setup in zip(jobs, session.setups):
        log_path = out_paths[job.model]
        _wait_for_remote_file(sonic_mgmt, log_path, timeout_sec=45)
        log_content = _read_remote_file(sonic_mgmt, log_path)
        series = parse_gnmic_log_to_series(log_content)
        if not series and log_content.strip():
            lowered = log_content.lower()
            if 'command not found' in lowered or 'no such file' in lowered:
                pytest.fail(
                    'gnmic failed on sonic-mgmt for %s (%s): %s'
                    % (job.model, log_path, log_content.strip()[:500])
                )
            if 'authentication handshake failed' in lowered or 'certificate is not valid' in lowered:
                pytest.fail(
                    'gnmic TLS handshake failed for %s (%s); tunnel mTLS is OK but tunneled '
                    'gnmi-server cert must use skip-verify (SSIM dial-out parity). tail: %s'
                    % (job.model, log_path, log_content.strip()[-800:])
                )
            if 'bind: address already in use' in lowered:
                pytest.fail(
                    'gnmic tunnel-server port conflict for %s (%s); stale gnmic still bound. tail: %s'
                    % (job.model, log_path, log_content.strip()[-800:])
                )
            if 'certificate required' in lowered or 'tls: certificate required' in lowered:
                pytest.fail(
                    'gnmic tunneled gnmi-server mTLS failed for %s (%s); need --tls-cert/--tls-key '
                    '(gnmic_client signed by gnmic_ca, SSIM GnmiCollectorDialOutVX parity). tail: %s'
                    % (job.model, log_path, log_content.strip()[-800:])
                )
            if 'unauthenticated' in lowered or 'authentication failed' in lowered:
                pytest.fail(
                    'gnmic gnmi-server Basic auth failed for %s (%s); use DUT NVUE credentials '
                    '(SSIM cumulus/NvidiaR0cks! parity, not admin/admin). tail: %s'
                    % (job.model, log_path, log_content.strip()[-800:])
                )
        if not series:
            pytest.fail(
                'gNMI %s produced no timestamps (%s); check grpc-tunnel register/tunnel and gnmic logs'
                % (job.model, log_path)
            )
        telemetryCache.add_data('gnmi-series-%s' % (job.model,), series)
        timing[job.model] = _timing_summary_from_series(
            job.model,
            series,
            sample_interval=job.sample_interval,
            tolerance=0.25,
        )
        logger.info('gNMI %s: %d timestamps from %s', job.model, len(series), log_path)
    try:
        existing = telemetryCache.get_data('gnmi_timing')
    except KeyError:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing.update(timing)
    telemetryCache.add_data('gnmi_timing', existing)


def run_gnmi_with_parallel_work(
    dut,
    sonic_mgmt,
    jobs: Sequence[GnmiCollectionJob],
    work,
    *,
    startup_grace_sec: int = 20,
    defer_teardown: bool = True,
) -> Optional[GnmiCoexistenceSession]:
    """Start gnmic subscriptions, run ``work()`` (e.g. OTLP collect), then parse gNMI cache.

    When ``defer_teardown`` is True the grpc-tunnel + gnmic session stays up until the caller
    invokes :func:`teardown_gnmi_coexistence_session` (SSIM ``post_suite_hook`` parity).
    """
    if not jobs:
        work()
        return None

    session = setup_gnmi_coexistence_session(dut, sonic_mgmt, jobs)
    out_paths: Dict[str, str] = {}
    succeeded = False
    try:
        max_job_sec = max(j.duration_sec for j in jobs)
        gnmi_run_sec = max_job_sec + startup_grace_sec
        with allure.step('Start gnmic sample subscriptions'):
            for job, setup in zip(jobs, session.setups):
                out_paths[job.model] = _start_gnmic_sample_subscription(
                    setup.collector,
                    model=job.model,
                    paths=job.paths,
                    sample_interval=job.sample_interval,
                    duration_sec=gnmi_run_sec,
                    gnmic_bin=session.gnmic_bin,
                )
        restarted_tunnels = set()
        with allure.step('Restart DUT grpc-tunnel clients after gnmic is listening'):
            for job in jobs:
                if job.tunnel_name in restarted_tunnels:
                    continue
                restarted_tunnels.add(job.tunnel_name)
                _restart_dut_grpc_tunnel(dut, job.tunnel_name)
            for job in jobs:
                _assert_grpc_tunnel_connected(
                    dut,
                    job.tunnel_name,
                    listen_port=job.listen_port,
                    timeout_sec=90,
                )
        work()
        time.sleep(min(startup_grace_sec, 10))
        with allure.step('Parse gnmic logs into telemetry cache'):
            _populate_gnmi_cache_from_session(sonic_mgmt, jobs, session, out_paths)
        succeeded = True
    finally:
        if not (defer_teardown and succeeded):
            teardown_gnmi_coexistence_session(dut, session)
    if defer_teardown and succeeded:
        return session
    return None


def run_gnmi_coexistence_collection(
    dut,
    sonic_mgmt,
    jobs: Sequence[GnmiCollectionJob],
    *,
    startup_grace_sec: int = 20,
    parallel_wait_sec: Optional[int] = None,
    defer_teardown: bool = False,
) -> Optional[GnmiCoexistenceSession]:
    """Run gnmic sample subscriptions; optionally overlap with an external OTLP window."""
    if not jobs:
        return None

    session = setup_gnmi_coexistence_session(dut, sonic_mgmt, jobs)
    out_paths: Dict[str, str] = {}
    succeeded = False
    try:
        with allure.step('Start gnmic sample subscriptions'):
            max_job_sec = max(j.duration_sec for j in jobs)
            gnmi_run_sec = max_job_sec + startup_grace_sec
            for job, setup in zip(jobs, session.setups):
                out_paths[job.model] = _start_gnmic_sample_subscription(
                    setup.collector,
                    model=job.model,
                    paths=job.paths,
                    sample_interval=job.sample_interval,
                    duration_sec=gnmi_run_sec,
                    gnmic_bin=session.gnmic_bin,
                )
            if parallel_wait_sec is None:
                time.sleep(gnmi_run_sec)
            else:
                remaining = max(0, gnmi_run_sec - int(parallel_wait_sec))
                if remaining:
                    time.sleep(remaining)

        with allure.step('Parse gnmic logs into telemetry cache'):
            _populate_gnmi_cache_from_session(sonic_mgmt, jobs, session, out_paths)
        succeeded = True
    finally:
        if not (defer_teardown and succeeded):
            teardown_gnmi_coexistence_session(dut, session)
    if defer_teardown and succeeded:
        return session
    return None


def _timing_summary_from_series(
    model: str,
    series: Dict[str, Dict[str, Dict[str, Any]]],
    *,
    sample_interval: str,
    tolerance: float,
) -> Dict[str, Any]:
    s_sec = _parse_interval_to_seconds(sample_interval) or 0.0
    result: Dict[str, Any] = {
        'model': model,
        'expected': {'sample_interval': s_sec, 'tolerance': tolerance},
        'result': 'fail',
    }
    if not series:
        result['error'] = 'empty series'
        return result
    ts_keys = sorted(int(k) for k in series if str(k).isdigit())
    if len(ts_keys) < 2:
        result['error'] = 'too few timestamps (%d)' % (len(ts_keys),)
        return result
    min_gap = s_sec * (1 - tolerance) if tolerance < 1 else s_sec - tolerance
    max_gap = s_sec * (1 + tolerance) if tolerance < 1 else s_sec + tolerance
    violations = []
    for prev_ts, cur_ts in zip(ts_keys[:-1], ts_keys[1:]):
        gap = float(cur_ts - prev_ts)
        if gap < min_gap or gap > max_gap:
            violations.append({'prev_ts': prev_ts, 'cur_ts': cur_ts, 'gap_s': gap})
    if violations:
        result['violations'] = violations
        result['error'] = '%d interval violations' % (len(violations),)
    else:
        result['result'] = 'pass'
    return result


def build_smoke_gnmi_jobs(dut, *, duration_sec: int = 120) -> List[GnmiCollectionJob]:
    """BGP + LLDP jobs for ``Test_Telemetry_Coexistence_Smoke`` (skip missing topo)."""
    jobs: List[GnmiCollectionJob] = []
    lab = resolve_cumulus_lab_interfaces_on_dut(dut)
    lldp_ctx = discover_lldp_neighbor_context(dut, preferred_iface=lab.test_iface)
    if lldp_ctx:
        lldp_kwargs = dict(lldp_ctx)
        lldp_paths = resolve_model_xpaths('lldp', SMOKE_LLDP_ATTRS, lldp_kwargs)
        if lldp_paths:
            jobs.append(
                GnmiCollectionJob(
                    model='lldp',
                    tunnel_name='coexistence_lldp',
                    listen_port=SMOKE_GNMI_PORT_LLDP,
                    paths=lldp_paths,
                    sample_interval='5s',
                    duration_sec=duration_sec,
                    attrs=SMOKE_LLDP_ATTRS,
                    populate_kwargs=lldp_kwargs,
                    group_size=1,
                )
            )

    bgp_neighbor = discover_bgp_neighbor_address(dut)
    if bgp_neighbor:
        bgp_kwargs = {
            'neighbor_address': bgp_neighbor,
            'vrf': 'default',
            'afi_safi_name': 'IPV4_UNICAST',
        }
        bgp_paths = resolve_model_xpaths('bgp', SMOKE_BGP_ATTRS, bgp_kwargs)
        if bgp_paths:
            jobs.append(
                GnmiCollectionJob(
                    model='bgp',
                    tunnel_name='coexistence_bgp',
                    listen_port=SMOKE_GNMI_PORT_BGP,
                    paths=bgp_paths,
                    sample_interval='3s',
                    duration_sec=duration_sec,
                    attrs=SMOKE_BGP_ATTRS,
                    populate_kwargs=bgp_kwargs,
                    group_size=1,
                )
            )
    return jobs


def build_interface_qos_gnmi_jobs(dut, *, duration_sec: int = 120) -> List[GnmiCollectionJob]:
    lab = resolve_cumulus_lab_interfaces_on_dut(dut)
    iface_kwargs = {'interface': lab.test_iface}
    paths = resolve_model_xpaths('interface', INTERFACE_QOS_GNMI_ATTRS, iface_kwargs)
    if not paths:
        return []
    return [
        GnmiCollectionJob(
            model='interface',
            tunnel_name='coexistence_interface',
            listen_port=57421,
            paths=paths,
            sample_interval='5s',
            duration_sec=duration_sec,
            attrs=INTERFACE_QOS_GNMI_ATTRS,
            populate_kwargs=iface_kwargs,
            group_size=2,
        )
    ]


def build_component_system_gnmi_jobs(dut, *, duration_sec: int = 120) -> List[GnmiCollectionJob]:
    component_name = discover_storage_component_name(dut)
    component_kwargs = {'component_name': component_name}
    system_paths = resolve_model_xpaths('system', SYSTEM_GNMI_ATTRS, {})
    component_paths = resolve_model_xpaths('component', COMPONENT_GNMI_ATTRS, component_kwargs)
    jobs: List[GnmiCollectionJob] = []
    if system_paths:
        jobs.append(
            GnmiCollectionJob(
                model='system',
                tunnel_name='coexistence_system',
                listen_port=57431,
                paths=system_paths,
                sample_interval='5s',
                duration_sec=duration_sec,
                attrs=SYSTEM_GNMI_ATTRS,
                populate_kwargs={'mount_point': '/'},
                group_size=2,
            )
        )
    if component_paths:
        jobs.append(
            GnmiCollectionJob(
                model='component',
                tunnel_name='coexistence_component',
                listen_port=57432,
                paths=component_paths,
                sample_interval='5s',
                duration_sec=duration_sec,
                attrs=COMPONENT_GNMI_ATTRS,
                populate_kwargs=component_kwargs,
                group_size=2,
            )
        )
    return jobs

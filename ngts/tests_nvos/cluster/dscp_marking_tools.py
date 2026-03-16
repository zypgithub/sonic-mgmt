"""
DSCP Marking Test Tools and Utilities

Provides helper classes for testing DSCP marking configuration in cluster environments.

Generic traffic utilities (packet capture, network interface queries) live in
``ngts.nvos_tools.infra.PacketCaptureTool`` and are imported directly where needed.
"""
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from ngts.cli_wrappers.openapi.openapi_command_builder import OpenApiRequest
from ngts.nvos_constants.constants_nvos import ApiType, OutputFormat
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.PacketCaptureTool import (
    NetworkInterfaceUtils,
    PacketCaptureTool,
)
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts

logger = logging.getLogger()


class DscpMarkingConstants:
    """DSCP marking related constants. References ClusterConsts for core values."""

    FIELD_NAME = ClusterConsts.DSCP_MARKING_FIELD
    DEFAULT_VALUE = ClusterConsts.DSCP_DEFAULT_VALUE
    MIN_VALUE = ClusterConsts.DSCP_MIN_VALUE
    MAX_VALUE = ClusterConsts.DSCP_MAX_VALUE

    DSCP_ENUM_MAP: Dict[str, Tuple[int, str]] = ClusterConsts.DSCP_ENUM_MAP
    DSCP_ENUM_NAMES: List[str] = ClusterConsts.DSCP_ENUM_NAMES

    # Timing constants (seconds)
    CAPTURE_FINALIZE_DELAY_SECONDS = 1
    CLUSTER_OPERATION_DELAY_SECONDS = 2
    TRAFFIC_CAPTURE_DURATION_SECONDS = 15  # Fallback; prefer compute_capture_duration_seconds()
    CAPTURE_BUFFER_SECONDS = 10
    TCPDUMP_STARTUP_DELAY = 0.5

    # Cluster connection timing (Bug SW #4099507)
    CLUSTER_CONN_MAX_RETRIES = 12
    CLUSTER_CONN_POLL_INTERVAL_SECONDS = 5

    MAX_ANALYSIS_SNIPPET_LENGTH = 1500

    # CLI commands for traffic generation (REST API doesn't generate inter-node traffic)
    CLI_SHOW_CLUSTER = "nv show cluster"
    CLI_SHOW_CLUSTER_NODE = "nv show cluster node"
    CLI_SHOW_NV_BRIDGE = "nv show system nv-bridge"
    TRAFFIC_TRIGGER_COMMANDS = [CLI_SHOW_CLUSTER, CLI_SHOW_CLUSTER_NODE, CLI_SHOW_NV_BRIDGE]

    DEFAULT_MGMT_INTERFACE = "eth0"

    @staticmethod
    def compute_capture_duration_seconds(num_engines: int) -> int:
        """
        Compute capture duration so tcpdump does not exit before traffic is triggered on all nodes.

        Traffic is triggered sequentially: num_engines * num_commands * delay_per_command,
        plus a buffer. Use this value for start_nv_bridge_capture and for the sleep after
        triggering traffic.
        """
        return (
            num_engines * len(DscpMarkingConstants.TRAFFIC_TRIGGER_COMMANDS) *
            DscpMarkingConstants.CLUSTER_OPERATION_DELAY_SECONDS +
            DscpMarkingConstants.CAPTURE_BUFFER_SECONDS
        )


class ClusterConfigHelper:
    """OOP helper for cluster configuration operations (NVUE and OpenAPI compatible)."""

    NODE_SERVER_FIELD = 'server'

    @staticmethod
    def apply_config(engine, ask_for_confirmation: str = '-y') -> str:
        """Apply configuration.

        Validates the returned output for error keywords (e.g. 'Error:', 'Action failed')
        via SendCommandTool so that a failed apply raises immediately instead of being
        silently ignored.
        """
        output = TestToolkit.GeneralApi[TestToolkit.tested_api].apply_config(
            engine, ask_for_confirmation=ask_for_confirmation)
        return SendCommandTool.verify_no_error_message(output).verify_result()

    @staticmethod
    def save_config(engine) -> str:
        """Save configuration.

        Validates the returned output for error keywords via SendCommandTool.
        """
        output = TestToolkit.GeneralApi[TestToolkit.tested_api].save_config(engine)
        return SendCommandTool.verify_no_error_message(output).verify_result()

    @staticmethod
    def set_cluster_state(cluster: Cluster, state: str, apply: bool = False,
                          dut_engine=None) -> ResultObj:
        """Set cluster state ('enabled' or 'disabled')."""
        return cluster.set(op_param_name="state", op_param_value=state,
                           apply=apply, dut_engine=dut_engine)

    @staticmethod
    def unset_cluster_state(cluster: Cluster, apply: bool = False,
                            dut_engine=None) -> ResultObj:
        """Unset cluster state."""
        return cluster.unset(op_param="state", apply=apply, dut_engine=dut_engine)

    @staticmethod
    def set_dscp_marking(cluster: Cluster, dscp_value: Union[int, str],
                         apply: bool = False, dut_engine=None) -> ResultObj:
        """Set DSCP marking value (numeric 0-63 or enum name)."""
        return cluster.set(op_param_name=DscpMarkingConstants.FIELD_NAME,
                           op_param_value=dscp_value, apply=apply, dut_engine=dut_engine)

    @staticmethod
    def unset_dscp_marking(cluster: Cluster, apply: bool = False,
                           dut_engine=None) -> ResultObj:
        """Unset DSCP marking (revert to default)."""
        return cluster.unset(op_param=DscpMarkingConstants.FIELD_NAME,
                             apply=apply, dut_engine=dut_engine)

    @staticmethod
    def add_cluster_node_server(server_ip: str, cluster: Cluster,
                                apply: bool = False, dut_engine=None) -> ResultObj:
        """Add cluster node primary server. Equivalent to: nv set cluster node primary server <ip>.

        Calls BaseComponent.set() directly instead of Node.Primary.set_cluster_node()
        because the latter (and its helper _set_cluster_node) do not propagate the
        ResultObj returned by set(), causing this method to return None.
        """
        if TestToolkit.tested_api == ApiType.OPENAPI:
            value = {server_ip: {}}
        else:
            value = server_ip
        return cluster.node.primary.set(
            op_param_name=ClusterConfigHelper.NODE_SERVER_FIELD,
            op_param_value=value,
            apply=apply,
            dut_engine=dut_engine
        )

    @staticmethod
    def unset_cluster_node(cluster: Cluster, apply: bool = False,
                           dut_engine=None) -> ResultObj:
        """Unset cluster node configuration."""
        return cluster.unset(op_param="node", apply=apply, dut_engine=dut_engine)

    @staticmethod
    def wait_for_cluster_connection(engine, cluster: Cluster,
                                    max_retries: int = None,
                                    poll_interval: int = None) -> bool:
        """Wait for cluster nmxc-conn to be 'up' by polling.

        Duration is measured and saved via OperationTime.
        """
        max_retries = max_retries or DscpMarkingConstants.CLUSTER_CONN_MAX_RETRIES
        poll_interval = poll_interval or DscpMarkingConstants.CLUSTER_CONN_POLL_INTERVAL_SECONDS
        operation = 'wait_for_cluster_connection'

        start_time = time.time()
        for attempt in range(max_retries):
            try:
                output = cluster.show(dut_engine=engine)
                if isinstance(output, str):
                    try:
                        output = json.loads(output)
                    except (json.JSONDecodeError, TypeError):
                        pass
                if isinstance(output, dict):
                    nmxc_conn = output.get('nmxc-conn', 'unknown')
                    state = output.get('state', 'unknown')
                    logger.info(f"Cluster status on {engine.ip}: state={state}, nmxc-conn={nmxc_conn}")
                    if nmxc_conn == 'up':
                        duration = time.time() - start_time
                        logger.info(
                            f"Cluster connection established on {engine.ip} "
                            f"(attempt {attempt + 1}/{max_retries}, duration={duration:.2f}s)"
                        )
                        OperationTime.save_manual_operation_duration_to_db(operation, duration, engine.ip)
                        return True
            except AssertionError as e:
                logger.warning(f"Cluster show failed on {engine.ip} (transient): {e}")
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"Connection error checking cluster status on {engine.ip}: {e}")
            except (AttributeError, KeyError) as e:
                logger.warning(f"Data error checking cluster status on {engine.ip}: {e}")
            except RuntimeError as e:
                logger.warning(f"Runtime error checking cluster status on {engine.ip}: {e}")

            if attempt < max_retries - 1:
                time.sleep(poll_interval)

        duration = time.time() - start_time
        logger.warning(
            f"Cluster connection not established on {engine.ip} after {max_retries} retries "
            f"(duration={duration:.2f}s)"
        )
        return False


class DscpValueSelector:
    """Converts between numeric and enum DSCP values."""

    @staticmethod
    def get_numeric_value(dscp_value: Union[int, str]) -> int:
        """Convert a DSCP value (numeric or enum name) to its numeric equivalent (0-63)."""
        if isinstance(dscp_value, int):
            return dscp_value
        elif isinstance(dscp_value, str):
            str_value = dscp_value.strip().lower()
            if str_value in DscpMarkingConstants.DSCP_ENUM_MAP:
                return DscpMarkingConstants.DSCP_ENUM_MAP[str_value][0]
            # Try to convert numeric string
            try:
                return int(str_value)
            except (ValueError, TypeError):
                pass
        raise ValueError(f"Invalid DSCP value: {dscp_value}")


class DscpMarkingReader:
    """Reads DSCP marking configuration from cluster."""

    def __init__(self, cluster: Cluster, output_format: OutputFormat = OutputFormat.json):
        self._cluster = cluster
        self._output_format = output_format

    def get_value(self) -> Any:
        """Get current DSCP marking value from cluster show output."""
        output = OutputParsingTool.parse_show_output_to_dict(
            self._cluster.show(output_format=self._output_format),
            output_format=self._output_format
        ).get_returned_value()
        return output.get(DscpMarkingConstants.FIELD_NAME)


class DscpMarkingWriter:
    """Writes DSCP marking configuration to cluster."""

    def __init__(self, cluster: Cluster):
        self._cluster = cluster

    def set_value(self, value: Any, apply: bool = True) -> Any:
        """Set DSCP marking value."""
        return self._cluster.set(
            op_param_name=DscpMarkingConstants.FIELD_NAME,
            op_param_value=value,
            apply=apply
        )

    def unset_value(self, apply: bool = True) -> Any:
        """Reset DSCP marking to default."""
        return self._cluster.unset(
            op_param=DscpMarkingConstants.FIELD_NAME,
            apply=apply
        )


class DscpMarkingVerifier:
    """Verifies DSCP marking configuration matches expected value."""

    def __init__(self, reader: DscpMarkingReader):
        self._reader = reader

    def verify_value(self, expected_value: Any) -> None:
        """Verify DSCP marking matches expected value."""
        actual_value = self._reader.get_value()

        try:
            expected_numeric = DscpValueSelector.get_numeric_value(expected_value)
            actual_numeric = DscpValueSelector.get_numeric_value(actual_value)

            assert actual_numeric == expected_numeric, \
                f"DSCP mismatch. Expected: {expected_value} ({expected_numeric}), " \
                f"Actual: {actual_value} ({actual_numeric})"
        except ValueError as e:
            assert str(actual_value) == str(expected_value), \
                f"DSCP mismatch. Expected: {expected_value}, Actual: {actual_value}. Error: {e}"


class TcFilterReader:
    """Reads traffic control configuration from system."""

    def __init__(self, engines):
        self._engines = engines

    def get_tc_filter(self, interface: str) -> str:
        """Get tc filter output for interface."""
        assert NetworkInterfaceUtils.interface_exists(self._engines.dut, interface), \
            f"Interface '{interface}' does not exist - cannot get tc filter"
        return self._engines.dut.run_cmd(f"sudo tc filter show dev {interface}")

    def get_tc_qdisc(self, interface: str) -> str:
        """Get tc qdisc output for interface."""
        assert NetworkInterfaceUtils.interface_exists(self._engines.dut, interface), \
            f"Interface '{interface}' does not exist - cannot get tc qdisc"
        return self._engines.dut.run_cmd(f"sudo tc qdisc show dev {interface}")


class DscpCaptureVerifier:
    """Verifies DSCP marking in tcpdump packet captures.

    Analyzes TOS (IPv4) or Traffic-Class (IPv6) fields in captured packets
    to confirm the expected DSCP value is present.
    """

    @staticmethod
    def verify_dscp_in_capture(engine, capture_file: str, expected_dscp: int,
                               ipv6: bool = False) -> Tuple[bool, int, str]:
        """Verify captured packets have the expected DSCP value (TOS = DSCP << 2)."""
        expected_tos = expected_dscp << 2
        expected_hex = f"0x{expected_tos:02x}"
        expected_hex_padded = f"0x{expected_tos:04x}"
        protocol = "IPv6" if ipv6 else "IPv4"

        packet_count = PacketCaptureTool.get_packet_count(engine, capture_file)

        if packet_count == 0:
            return False, 0, "No packets captured"

        analysis = PacketCaptureTool.analyze_capture(engine, capture_file)
        tos_counts = DscpCaptureVerifier._analyze_tos_distribution(analysis, ipv6)

        found = False
        if ipv6:
            patterns = [
                rf'class[:\s]*{expected_hex}\b',
                rf'class[:\s]*{expected_hex_padded}\b',
                rf'class[:\s]*0*{expected_tos}\b',
                rf'class[:\s]*0x0*{expected_tos:x}\b',
                rf'tc[:\s]*{expected_hex}\b',
                rf'tc[:\s]*{expected_tos}\b',
            ]
        else:
            patterns = [
                rf'tos\s+{expected_hex}\b',
                rf'tos\s+{expected_hex_padded}\b',
                rf'tos\s+{expected_tos}\b',
                rf'tos\s+0x0*{expected_tos:x}\b',
            ]

        for pattern in patterns:
            if re.search(pattern, analysis, re.IGNORECASE):
                found = True
                break

        expected_dscp_count = tos_counts.get(expected_tos, 0)
        tos_summary = ", ".join(f"0x{t:02x}:{c}" for t, c in sorted(tos_counts.items(), key=lambda x: -x[1])[:5])
        logger.info(f"{protocol} DSCP check on {engine.ip}: pkts={packet_count}, "
                    f"expected={expected_dscp}(TOS {expected_hex}), found={found}, "
                    f"match_count={expected_dscp_count}, top_tos=[{tos_summary}]")

        if not found and packet_count > 0:
            logger.warning(f"{protocol} DSCP {expected_dscp} not found. "
                           f"TOS distribution: {tos_counts}. "
                           f"Searched patterns: {patterns[:2]}...")

        max_len = DscpMarkingConstants.MAX_ANALYSIS_SNIPPET_LENGTH
        snippet = analysis[:max_len] if len(analysis) > max_len else analysis

        return found, packet_count, snippet

    @staticmethod
    def _analyze_tos_distribution(tcpdump_output: str, ipv6: bool = False) -> Dict[int, int]:
        """Analyze TOS/Traffic Class distribution from tcpdump output."""
        tos_counts: Dict[int, int] = {}

        if ipv6:
            hex_patterns = [
                r'class[:\s]*0x([0-9a-fA-F]{1,4})\b',
                r'tc[:\s]*0x([0-9a-fA-F]{1,4})\b',
            ]
            decimal_patterns = [
                r'class[:\s]*(\d{1,3})\b',
                r'tc[:\s]*(\d{1,3})\b',
            ]
        else:
            hex_patterns = [
                r'tos\s+0x([0-9a-fA-F]{1,4})',
            ]
            decimal_patterns = [
                r'tos\s+(\d{1,3})\b',
            ]

        for pattern in hex_patterns:
            matches = re.findall(pattern, tcpdump_output, re.IGNORECASE)
            for match in matches:
                try:
                    tos_val = int(match, 16)
                    if 0 <= tos_val <= 255:  # Valid TOS range
                        tos_counts[tos_val] = tos_counts.get(tos_val, 0) + 1
                except ValueError:
                    continue

        for pattern in decimal_patterns:
            matches = re.findall(pattern, tcpdump_output, re.IGNORECASE)
            for match in matches:
                try:
                    tos_val = int(match)
                    if 0 <= tos_val <= 255:  # Valid TOS range
                        tos_counts[tos_val] = tos_counts.get(tos_val, 0) + 1
                except ValueError:
                    continue

        return tos_counts


class ControlPlaneTrafficTools:
    """Generates and captures control-plane traffic (nv-bridge port 50052) for DSCP verification."""

    NV_BRIDGE_PORT = ClusterConsts.NV_BRIDGE_PORT

    CP_CAPTURE_FILE = "/tmp/control_plane_dscp.pcap"
    NON_CP_CAPTURE_FILE = "/tmp/non_control_plane_dscp.pcap"
    NV_BRIDGE_CAPTURE_PATTERN = "/tmp/nv_bridge_dscp_*.pcap"
    DEFAULT_DSCP_CAPTURE_FILE = "/tmp/dscp_test.pcap"
    IPV6_DSCP_CAPTURE_FILE = "/tmp/ipv6_dscp.pcap"

    CLEANUP_PATTERNS = [
        "/tmp/nv_bridge_dscp_*.pcap",
        "/tmp/control_plane_dscp*.pcap",
        DEFAULT_DSCP_CAPTURE_FILE,
        IPV6_DSCP_CAPTURE_FILE,
    ]

    DSCP_TCPDUMP_KILL_PATTERN = r"tcpdump.*/tmp/.*dscp"

    @staticmethod
    def configure_dscp_on_node(engine, dscp_value: Union[int, str],
                               cluster: Cluster, apply: bool = True) -> bool:
        """Configure DSCP marking on a node. Returns True on success, False on error."""
        try:
            res = ClusterConfigHelper.set_dscp_marking(
                cluster, dscp_value, apply=apply, dut_engine=engine
            )
            if isinstance(res, ResultObj):
                res.verify_result()
            return True
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"Connection error configuring DSCP on {engine.ip}: {e}")
            return False
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid DSCP value {dscp_value} for {engine.ip}: {e}")
            return False
        except RuntimeError as e:
            logger.error(f"Runtime error configuring DSCP on {engine.ip}: {e}")
            return False

    @staticmethod
    def start_nv_bridge_capture(engine, interface: str, capture_file: str = None,
                                duration_seconds: int = 30, ipv6: bool = False) -> str:
        """Start tcpdump capture filtering for nv-bridge traffic on port 50052.

        Delegates to ``PacketCaptureTool.start_filtered_capture``.
        """
        capture_file = capture_file or ControlPlaneTrafficTools.CP_CAPTURE_FILE
        port = ControlPlaneTrafficTools.NV_BRIDGE_PORT
        ip_filter = "ip6" if ipv6 else "ip"
        capture_filter = f"{ip_filter} and tcp port {port}"

        return PacketCaptureTool.start_filtered_capture(
            engine, interface, capture_filter=capture_filter,
            capture_file=capture_file, duration_seconds=duration_seconds,
        )

    @staticmethod
    def trigger_cluster_operations(engine, cluster: Cluster) -> int:
        """Trigger CLI commands that generate inter-node traffic.

        Uses CLI directly because REST API GET requests do NOT generate inter-node traffic.
        """
        success_count = 0
        cli_commands = DscpMarkingConstants.TRAFFIC_TRIGGER_COMMANDS

        for cmd in cli_commands:
            try:
                result = engine.run_cmd(cmd, validate=False)
                if result is not None:
                    success_count += 1
                time.sleep(DscpMarkingConstants.CLUSTER_OPERATION_DELAY_SECONDS)
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"Connection error for '{cmd}' on {engine.ip}: {e}")
            except RuntimeError as e:
                logger.warning(f"Runtime error for '{cmd}' on {engine.ip}: {e}")

        logger.info(f"Traffic trigger on {engine.ip}: {success_count}/{len(cli_commands)} commands succeeded")
        return success_count

    @staticmethod
    def _verify_node_config_removed(engine, cluster: Cluster) -> bool:
        """Verify that cluster node configuration was removed.

        Uses if_returned_value=False to inspect .returned_value directly.
        """
        try:
            result_obj = cluster.show(dut_engine=engine, if_returned_value=False,
                                      output_format=OutputFormat.json)
            result_obj.ignore_result()

            if not result_obj.result:
                # Show failed — likely no config present (already removed)
                logger.info(f"Cluster show returned no data on {engine.ip}, treating as removed")
                return True

            output = result_obj.returned_value
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except (json.JSONDecodeError, TypeError):
                    pass

            if isinstance(output, dict):
                node_config = output.get('node', {})
                if node_config:
                    primary = node_config.get('primary', {})
                    servers = primary.get('server', {})
                    if servers:
                        logger.warning(f"Node servers still configured on {engine.ip}: {list(servers.keys())}")
                        return False
                logger.info(f"Node config verified removed on {engine.ip}")
                return True

            # Non-dict output (e.g. empty string) means no config present
            logger.info(f"No cluster config output on {engine.ip}, treating as removed")
            return True
        except AssertionError as e:
            logger.warning(f"Cluster show assertion on {engine.ip}: {e}")
        except (ConnectionError, TimeoutError, OSError) as e:
            logger.warning(f"Connection error verifying node config on {engine.ip}: {e}")
        except (AttributeError, KeyError) as e:
            logger.warning(f"Data error verifying node config on {engine.ip}: {e}")
        except RuntimeError as e:
            logger.warning(f"Runtime error verifying node config on {engine.ip}: {e}")

        # If we can't verify, assume it's okay to proceed
        return True

    @staticmethod
    def cleanup_cluster_config_on_all_nodes(engines_list: List, cluster: Cluster,
                                            apply: bool = True) -> None:
        """Cleanup cluster config on all nodes.

        Order matters: nodes -> state -> dscp-marking (cannot disable state while nodes exist).
        """
        cleanup_files = " ".join(ControlPlaneTrafficTools.CLEANUP_PATTERNS)
        for engine in engines_list:
            try:
                PacketCaptureTool.stop_capture(
                    engine, kill_pattern=ControlPlaneTrafficTools.DSCP_TCPDUMP_KILL_PATTERN,
                )
                engine.run_cmd(f"sudo rm -f {cleanup_files}", validate=False)
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"Connection error cleaning tcpdump/files on {engine.ip}: {e}")
            except RuntimeError as e:
                logger.warning(f"Runtime error cleaning tcpdump/files on {engine.ip}: {e}")

            OpenApiRequest.clear_changeset_and_payload()

            # Step 1: Unset cluster node
            try:
                result = ClusterConfigHelper.unset_cluster_node(cluster, apply=apply, dut_engine=engine)
                if result and hasattr(result, 'ignore_result'):
                    result.ignore_result()
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"Connection error on unset_cluster_node for {engine.ip}: {e}")
            except RuntimeError as e:
                logger.warning(f"Runtime error on unset_cluster_node for {engine.ip}: {e}")

            # Validate node config was removed before proceeding
            node_removed = ControlPlaneTrafficTools._verify_node_config_removed(engine, cluster)
            if not node_removed:
                logger.warning(f"Node config still present on {engine.ip} after unset, retrying...")
                # Clear changeset and retry
                OpenApiRequest.clear_changeset_and_payload()
                try:
                    result = ClusterConfigHelper.unset_cluster_node(cluster, apply=apply, dut_engine=engine)
                    if result and hasattr(result, 'ignore_result'):
                        result.ignore_result()
                except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
                    logger.warning(f"Retry unset_cluster_node failed on {engine.ip}: {e}")
                # Re-verify after retry
                node_removed = ControlPlaneTrafficTools._verify_node_config_removed(engine, cluster)

            # Step 2: Unset cluster state (only if nodes were removed)
            if not node_removed:
                logger.error(
                    f"Skipping unset_cluster_state on {engine.ip}: node config still present. "
                    f"Manual cleanup may be required."
                )
            else:
                try:
                    result = ClusterConfigHelper.unset_cluster_state(cluster, apply=apply, dut_engine=engine)
                    if result and hasattr(result, 'ignore_result'):
                        result.ignore_result()
                except (ConnectionError, TimeoutError, OSError) as e:
                    logger.warning(f"Connection error on unset_cluster_state for {engine.ip}: {e}")
                except RuntimeError as e:
                    logger.warning(f"Runtime error on unset_cluster_state for {engine.ip}: {e}")

            # Step 3: Unset dscp-marking
            try:
                result = ClusterConfigHelper.unset_dscp_marking(cluster, apply=apply, dut_engine=engine)
                if result and hasattr(result, 'ignore_result'):
                    result.ignore_result()
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"Connection error on unset_dscp_marking for {engine.ip}: {e}")
            except RuntimeError as e:
                logger.warning(f"Runtime error on unset_dscp_marking for {engine.ip}: {e}")


class TcConfigVerifier:
    """Verifies traffic control configuration (qdisc and filters)."""

    def __init__(self, engines):
        self._engines = engines

    def verify_qdisc_has_prio(self, interface: str) -> bool:
        """Verify interface has prio qdisc."""
        assert NetworkInterfaceUtils.interface_exists(self._engines.dut, interface), \
            f"Interface '{interface}' does not exist - cannot verify qdisc"
        output = self._engines.dut.run_cmd(f"sudo tc qdisc show dev {interface}")
        return 'prio' in output.lower()

    def verify_filter_matches_dscp(self, interface: str, dscp_value: int) -> bool:
        """Verify tc filter matches expected DSCP value (checks TOS = DSCP << 2)."""
        assert NetworkInterfaceUtils.interface_exists(self._engines.dut, interface), \
            f"Interface '{interface}' does not exist - cannot verify filter"
        output = self._engines.dut.run_cmd(f"sudo tc filter show dev {interface}")
        tos_value = dscp_value << 2
        return (f"dsfield {tos_value:02x}" in output.lower() or
                f"dsfield {tos_value}" in output)


class DscpMarkingTestFacade:
    """Facade providing unified interface for DSCP marking test operations."""

    def __init__(self, cluster: Cluster, engines, devices,
                 output_format: OutputFormat = OutputFormat.json):
        self._dut_engine = engines.dut
        self._devices = devices
        self._reader = DscpMarkingReader(cluster, output_format)
        self._writer = DscpMarkingWriter(cluster)
        self._verifier = DscpMarkingVerifier(self._reader)
        self._tc_reader = TcFilterReader(engines)
        self._tc_verifier = TcConfigVerifier(engines)

    def get_dscp_value(self) -> Any:
        """Get current DSCP marking value."""
        return self._reader.get_value()

    def verify_dscp_value(self, expected_value: Any) -> None:
        """Verify DSCP marking matches expected value."""
        self._verifier.verify_value(expected_value)

    def get_tc_filter(self, interface: str) -> str:
        """Get tc filter output for interface."""
        return self._tc_reader.get_tc_filter(interface)

    def get_mgmt_ports(self) -> List[str]:
        """Get management port names from device."""
        return self._devices.dut.get_mgmt_ports()

    def interface_exists(self, interface: str) -> bool:
        """Check if network interface exists."""
        return NetworkInterfaceUtils.interface_exists(self._dut_engine, interface)

    def verify_qdisc_prio(self, interface: str) -> bool:
        """Verify interface has prio qdisc."""
        return self._tc_verifier.verify_qdisc_has_prio(interface)

    def cleanup(self) -> None:
        """Cleanup DSCP configuration and capture files."""
        try:
            self._writer.unset_value()
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            logger.warning(f"Error during DSCP cleanup: {e}")

        try:
            PacketCaptureTool.stop_capture(
                self._dut_engine,
                kill_pattern=ControlPlaneTrafficTools.DSCP_TCPDUMP_KILL_PATTERN,
            )
            PacketCaptureTool.cleanup_capture_file(
                self._dut_engine, ControlPlaneTrafficTools.DEFAULT_DSCP_CAPTURE_FILE,
            )
            PacketCaptureTool.cleanup_capture_file(
                self._dut_engine, ControlPlaneTrafficTools.IPV6_DSCP_CAPTURE_FILE,
            )
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            logger.warning(f"Error during capture cleanup: {e}")

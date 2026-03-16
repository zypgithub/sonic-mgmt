"""
Packet Capture Tool

Reusable utilities for network interface operations and packet capture using
tcpdump on remote engines. Designed for use across different test scenarios
(DSCP verification, QoS tests, general traffic inspection, etc.).

All public methods are static and accept an engine parameter so they
work with any remote engine without requiring instance state.

Design principles (SOLID):
- Single Responsibility: each class handles one concern
  (interface info vs. packet capture).
- Open/Closed: callers can extend behaviour via parameters
  (custom filters, kill patterns) rather than modifying this module.
- Dependency Inversion: no dependency on test-specific constants;
  defaults live in PacketCaptureDefaults.
"""
import logging
import time
from typing import List, Optional, Tuple

logger = logging.getLogger()


class PacketCaptureDefaults:
    """Sensible defaults for packet capture operations.

    Override at call-site when test-specific values are needed.
    """

    DEFAULT_CAPTURE_FILE = "/tmp/packet_capture.pcap"
    TCPDUMP_STARTUP_DELAY: float = 0.5


class NetworkInterfaceUtils:
    """Reusable static utilities for querying network interfaces on remote engines."""

    @staticmethod
    def interface_exists(engine, interface: str) -> bool:
        """Check whether interface exists on engine.

        Args:
            engine: Remote engine with a run_cmd method.
            interface: Interface name (e.g. eth0).

        Returns:
            True if the interface is present, False otherwise.
        """
        cmd = f"ip link show {interface} 2>/dev/null"
        output = engine.run_cmd(cmd, validate=False)
        return bool(output and interface in output and "does not exist" not in output)

    @staticmethod
    def get_interface_ipv6(engine, interface: str) -> Optional[str]:
        """Return the first global (non link-local) IPv6 address on interface, or None.

        Args:
            engine: Remote engine with a run_cmd method.
            interface: Interface name.
        """
        cmd = (
            f"ip -6 addr show {interface} | grep 'inet6' | grep -v 'fe80' | "
            f"awk '{{print $2}}' | cut -d'/' -f1 | head -1"
        )
        output = engine.run_cmd(cmd, validate=False).strip()
        return output if output else None


class PacketCaptureTool:
    """Static-method tool for tcpdump packet capture on remote engines.

    Every method accepts an engine parameter and an optional
    capture_file (defaults to PacketCaptureDefaults.DEFAULT_CAPTURE_FILE).
    """

    @staticmethod
    def start_filtered_capture(
        engine,
        interface: str,
        capture_filter: str,
        capture_file: str = None,
        duration_seconds: int = 30,
        verbosity: str = "-vv",
    ) -> str:
        """Start a tcpdump capture with a custom BPF filter and a timeout.

        Runs in background automatically.

        Args:
            engine: Remote engine.
            interface: Network interface.
            capture_filter: BPF filter expression (e.g. 'ip and tcp port 50052').
            capture_file: Path for the pcap file.
            duration_seconds: Timeout value in seconds.
            verbosity: tcpdump verbosity flag(s).

        Returns:
            Raw command output.
        """
        capture_file = capture_file or PacketCaptureDefaults.DEFAULT_CAPTURE_FILE
        cmd = (
            f"sudo timeout {duration_seconds} tcpdump -i {interface} {verbosity} "
            f"'{capture_filter}' -w {capture_file} 2>/dev/null &"
        )
        result = engine.run_cmd(cmd, validate=False)
        time.sleep(PacketCaptureDefaults.TCPDUMP_STARTUP_DELAY)
        return result

    @staticmethod
    def stop_capture(
        engine,
        capture_file: str = None,
        kill_pattern: str = None,
    ) -> str:
        """Stop a running tcpdump process.

        Uses kill_pattern if provided, otherwise kills tcpdump matching
        capture_file.

        Args:
            engine: Remote engine.
            capture_file: The pcap file path used to identify the process.
            kill_pattern: Regex pattern for pkill -f (takes precedence).

        Returns:
            Raw command output.
        """
        if kill_pattern:
            return engine.run_cmd(
                f"sudo pkill -f '{kill_pattern}' || true", validate=False
            )
        capture_file = capture_file or PacketCaptureDefaults.DEFAULT_CAPTURE_FILE
        return engine.run_cmd(
            f"sudo pkill -f 'tcpdump.*{capture_file}' || true", validate=False
        )

    # ------------------------------------------------------------------
    # Capture analysis
    # ------------------------------------------------------------------

    @staticmethod
    def analyze_capture(engine, capture_file: str = None) -> str:
        """Read and display captured packets (tcpdump -r).

        Args:
            engine: Remote engine.
            capture_file: Path to pcap file.

        Returns:
            Human-readable tcpdump output, or 'No packets captured'.
        """
        capture_file = capture_file or PacketCaptureDefaults.DEFAULT_CAPTURE_FILE
        cmd = f"sudo tcpdump -r {capture_file} -vvv 2>/dev/null || echo 'No packets captured'"
        return engine.run_cmd(cmd, validate=False)

    @staticmethod
    def get_packet_count(engine, capture_file: str = None) -> int:
        """Return the number of packets in a capture file.

        Args:
            engine: Remote engine.
            capture_file: Path to pcap file.

        Returns:
            Packet count (0 on error or empty capture).
        """
        capture_file = capture_file or PacketCaptureDefaults.DEFAULT_CAPTURE_FILE
        count_cmd = f"sudo tcpdump -r {capture_file} 2>/dev/null | wc -l"
        count_output = engine.run_cmd(count_cmd, validate=False).strip()
        try:
            return int(count_output)
        except (ValueError, TypeError):
            return 0

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    @staticmethod
    def cleanup_capture_file(engine, capture_file: str = None) -> str:
        """Remove a capture file from engine.

        Args:
            engine: Remote engine.
            capture_file: Path to remove.

        Returns:
            Raw command output.
        """
        capture_file = capture_file or PacketCaptureDefaults.DEFAULT_CAPTURE_FILE
        return engine.run_cmd(f"sudo rm -f {capture_file}", validate=False)

    # ------------------------------------------------------------------
    # Multi-engine helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_switch_pairs(engine_dict: dict) -> List[Tuple]:
        """Build circular (source, target) pairs from a dict of engines.

        Useful for cross-switch traffic testing where each engine sends to
        the next one.

        Args:
            engine_dict: Mapping of engine name/key to engine object
                         (e.g. dut_engines).

        Returns:
            List of (source_engine, target_engine) tuples.
            Empty list if fewer than 2 engines.
        """
        engines_list = list(engine_dict.values())
        if len(engines_list) < 2:
            return []

        pairs = []
        for i in range(len(engines_list)):
            source = engines_list[i]
            target = engines_list[(i + 1) % len(engines_list)]
            if source != target:
                pairs.append((source, target))
        return pairs

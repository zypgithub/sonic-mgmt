import shlex
from typing import List, Optional, Union


class TcpdumpCmdBuilder:
    """
    A builder class for constructing Linux 'tcpdump' commands.

    Supports building commands like:
        - tcpdump -i eth0
        - tcpdump -i eth0 -c 10 -w capture.pcap
        - sudo tcpdump -i any port 80

    Example usage:
        cmd = TcpdumpCmdBuilder().interface("eth0").build()
        # Result: "tcpdump -i eth0"

        cmd = TcpdumpCmdBuilder().sudo().interface("eth0").count(10).build()
        # Result: "sudo tcpdump -i eth0 -c 10"
    """

    def __init__(self) -> None:
        self._command: List[str] = ["tcpdump"]
        self._use_sudo: bool = False
        self._filter_expressions: List[str] = []

    # --- Sudo Option ---

    def sudo(self) -> 'TcpdumpCmdBuilder':
        """Add 'sudo' to the command."""
        self._use_sudo = True
        return self

    # --- Interface Options ---

    def interface(self, iface: str) -> 'TcpdumpCmdBuilder':
        """
        Adds the '-i' option to specify the interface to capture on.

        Args:
            iface: Interface name (e.g., 'eth0', 'any')
        """
        self._command.extend(["-i", iface])
        return self

    def any_interface(self) -> 'TcpdumpCmdBuilder':
        """Captures on all interfaces using '-i any'."""
        return self.interface("any")

    # --- Capture Control Options ---

    def count(self, num_packets: int) -> 'TcpdumpCmdBuilder':
        """
        Adds the '-c' option to capture a specific number of packets.

        Args:
            num_packets: Number of packets to capture before stopping
        """
        self._command.extend(["-c", str(num_packets)])
        return self

    def snapshot_length(self, length: int) -> 'TcpdumpCmdBuilder':
        """
        Adds the '-s' option to set the snapshot length.

        Args:
            length: Number of bytes to capture per packet (0 = entire packet)
        """
        self._command.extend(["-s", str(length)])
        return self

    def timeout(self, seconds: int) -> 'TcpdumpCmdBuilder':
        """
        Adds the '--time-stamp-precision' is not timeout, using '-G' for rotation.
        For actual timeout, we use shell timeout wrapper or -c with time limit.

        Note: tcpdump doesn't have a built-in timeout. Consider using count() instead
        or wrapping with shell timeout command.

        Args:
            seconds: Duration in seconds (uses -G for file rotation interval)
        """
        self._command.extend(["-G", str(seconds)])
        return self

    # --- Output Options ---

    def write_file(self, filepath: str) -> 'TcpdumpCmdBuilder':
        """
        Adds the '-w' option to write packets to a file.

        Args:
            filepath: Path to the output pcap file
        """
        self._command.extend(["-w", filepath])
        return self

    def read_file(self, filepath: str) -> 'TcpdumpCmdBuilder':
        """
        Adds the '-r' option to read packets from a file.

        Args:
            filepath: Path to the input pcap file
        """
        self._command.extend(["-r", filepath])
        return self

    def verbose(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-v' flag for verbose output."""
        self._command.append("-v")
        return self

    def very_verbose(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-vv' flag for very verbose output."""
        self._command.append("-vv")
        return self

    def extra_verbose(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-vvv' flag for extra verbose output."""
        self._command.append("-vvv")
        return self

    def quiet(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-q' flag for quiet output (less protocol info)."""
        self._command.append("-q")
        return self

    def no_resolve_hosts(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-n' flag to not resolve hostnames."""
        self._command.append("-n")
        return self

    def no_resolve_ports(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-nn' flag to not resolve hostnames or port names."""
        self._command.append("-nn")
        return self

    def print_absolute_seq(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-S' flag to print absolute TCP sequence numbers."""
        self._command.append("-S")
        return self

    def print_hex(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-x' flag to print packet data in hex."""
        self._command.append("-x")
        return self

    def print_hex_ascii(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-X' flag to print packet data in hex and ASCII."""
        self._command.append("-X")
        return self

    def print_ethernet(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-e' flag to print link-level header."""
        self._command.append("-e")
        return self

    def timestamp_precision(self, precision: str) -> 'TcpdumpCmdBuilder':
        """
        Adds the '--time-stamp-precision' option.

        Args:
            precision: Timestamp precision ('micro' or 'nano')
        """
        self._command.extend(["--time-stamp-precision", precision])
        return self

    def line_buffered(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-l' flag for line-buffered output."""
        self._command.append("-l")
        return self

    def packet_buffered(self) -> 'TcpdumpCmdBuilder':
        """Adds the '-U' flag for packet-buffered output when writing to a file."""
        self._command.append("-U")
        return self

    # --- Generic Option Method ---

    def option(self, key: str, value: Optional[Union[str, int]] = None) -> 'TcpdumpCmdBuilder':
        """
        Adds a generic option flag or key-value option.
        Prefer specific methods where available.

        Args:
            key: Option key (without leading dash)
            value: Optional value for the option
        """
        self._command.append(f"-{key}")
        if value is not None:
            self._command.append(str(value))
        return self

    # --- Filter Expressions ---

    def filter(self, expression: str) -> 'TcpdumpCmdBuilder':
        """
        Adds a filter expression to the command.

        Args:
            expression: BPF filter expression (e.g., 'port 80', 'host 192.168.1.1')
        """
        self._filter_expressions.append(expression)
        return self

    def host(self, address: str) -> 'TcpdumpCmdBuilder':
        """
        Adds a host filter.

        Args:
            address: IP address or hostname to filter
        """
        self._filter_expressions.append(f"host {address}")
        return self

    def src_host(self, address: str) -> 'TcpdumpCmdBuilder':
        """
        Adds a source host filter.

        Args:
            address: Source IP address or hostname
        """
        self._filter_expressions.append(f"src host {address}")
        return self

    def dst_host(self, address: str) -> 'TcpdumpCmdBuilder':
        """
        Adds a destination host filter.

        Args:
            address: Destination IP address or hostname
        """
        self._filter_expressions.append(f"dst host {address}")
        return self

    def port(self, port_num: Union[str, int]) -> 'TcpdumpCmdBuilder':
        """
        Adds a port filter.

        Args:
            port_num: Port number to filter
        """
        self._filter_expressions.append(f"port {port_num}")
        return self

    def ports(self, *port_nums: Union[str, int]) -> 'TcpdumpCmdBuilder':
        """
        Adds a filter for multiple ports joined with 'or'.

        Example:
            builder.ports(67, 68) produces: port 67 or port 68

        Args:
            port_nums: Variable number of port numbers to filter
        """
        if not port_nums:
            return self
        if len(port_nums) == 1:
            return self.port(port_nums[0])

        port_filter: str = " or ".join(f"port {p}" for p in port_nums)
        self._filter_expressions.append(f"( {port_filter} )")
        return self

    def src_port(self, port_num: Union[str, int]) -> 'TcpdumpCmdBuilder':
        """
        Adds a source port filter.

        Args:
            port_num: Source port number
        """
        self._filter_expressions.append(f"src port {port_num}")
        return self

    def dst_port(self, port_num: Union[str, int]) -> 'TcpdumpCmdBuilder':
        """
        Adds a destination port filter.

        Args:
            port_num: Destination port number
        """
        self._filter_expressions.append(f"dst port {port_num}")
        return self

    def net(self, network: str) -> 'TcpdumpCmdBuilder':
        """
        Adds a network filter.

        Args:
            network: Network address (e.g., '192.168.1.0/24')
        """
        self._filter_expressions.append(f"net {network}")
        return self

    def protocol(self, proto: str) -> 'TcpdumpCmdBuilder':
        """
        Adds a protocol filter.

        Args:
            proto: Protocol name (e.g., 'tcp', 'udp', 'icmp', 'arp')
        """
        self._filter_expressions.append(proto)
        return self

    def tcp(self) -> 'TcpdumpCmdBuilder':
        """Adds TCP protocol filter."""
        return self.protocol("tcp")

    def udp(self) -> 'TcpdumpCmdBuilder':
        """Adds UDP protocol filter."""
        return self.protocol("udp")

    def icmp(self) -> 'TcpdumpCmdBuilder':
        """Adds ICMP protocol filter."""
        return self.protocol("icmp")

    def arp(self) -> 'TcpdumpCmdBuilder':
        """Adds ARP protocol filter."""
        return self.protocol("arp")

    def filter_and(self) -> 'TcpdumpCmdBuilder':
        """Adds 'and' operator between filter expressions."""
        self._filter_expressions.append("and")
        return self

    def filter_or(self) -> 'TcpdumpCmdBuilder':
        """Adds 'or' operator between filter expressions."""
        self._filter_expressions.append("or")
        return self

    def filter_not(self) -> 'TcpdumpCmdBuilder':
        """Adds 'not' operator before next filter expression."""
        self._filter_expressions.append("not")
        return self

    # --- Build Methods ---

    def build(self, as_string: bool = True) -> Union[str, List[str]]:
        """
        Constructs the final command.

        Args:
            as_string: If True (default), returns the command as a single, shell-quoted string.
                       If False, returns a list of command parts.

        Returns:
            The constructed command string or list.
        """
        cmd: List[str] = []

        if self._use_sudo:
            cmd.append("sudo")

        cmd.extend(self._command)

        if self._filter_expressions:
            cmd.extend(self._filter_expressions)

        if as_string:
            return " ".join(shlex.quote(part) for part in cmd)
        else:
            return list(cmd)

    def get_command_list(self) -> List[str]:
        """Builds the command and returns it as a list of arguments."""
        result: Union[str, List[str]] = self.build(as_string=False)
        return result  # type: ignore

    def get_command_string(self) -> str:
        """Builds the command and returns it as a shell-quoted string."""
        result: Union[str, List[str]] = self.build(as_string=True)
        return result  # type: ignore

    def get_sudo_command_string(self) -> str:
        """Builds the command with sudo prefix and returns it as a shell-quoted string."""
        self._use_sudo = True
        return self.get_command_string()

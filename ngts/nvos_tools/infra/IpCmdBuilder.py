import shlex
from typing import List, Optional, Union


class IpCmdBuilder:
    """
    A builder class for constructing Linux 'ip' commands.

    Supports building commands like:
        - ip rule show
        - ip -4 rule show
        - ip -6 rule show
        - ip rule show table main

    Example usage:
        cmd = IpCmdBuilder().rule().show().build()
        # Result: "ip rule show"

        cmd = IpCmdBuilder().ipv4().rule().show().build()
        # Result: "ip -4 rule show"
    """

    def __init__(self) -> None:
        self._command: List[str] = ["ip"]
        self._subcommand: Optional[str] = None
        self._action: Optional[str] = None

    # --- Protocol Family Options ---

    def ipv4(self) -> 'IpCmdBuilder':
        """Adds the '-4' flag to use IPv4 protocol family."""
        self._command.append("-4")
        return self

    def ipv6(self) -> 'IpCmdBuilder':
        """Adds the '-6' flag to use IPv6 protocol family."""
        self._command.append("-6")
        return self

    def family(self, family_name: str) -> 'IpCmdBuilder':
        """
        Adds the '-f' or '-family' option with specified family.

        Args:
            family_name: Protocol family (inet, inet6, link, mpls, bridge, etc.)
        """
        self._command.extend(["-f", family_name])
        return self

    # --- Output Format Options ---

    def json_output(self) -> 'IpCmdBuilder':
        """Adds the '-j' flag for JSON output format."""
        self._command.append("-j")
        return self

    def brief(self) -> 'IpCmdBuilder':
        """Adds the '-br' flag for brief output."""
        self._command.append("-br")
        return self

    def details(self) -> 'IpCmdBuilder':
        """Adds the '-d' flag for detailed output."""
        self._command.append("-d")
        return self

    def oneline(self) -> 'IpCmdBuilder':
        """Adds the '-o' flag for single-line output."""
        self._command.append("-o")
        return self

    def pretty(self) -> 'IpCmdBuilder':
        """Adds the '-p' flag for pretty (human-readable) output."""
        self._command.append("-p")
        return self

    # --- Generic Option Method ---

    def option(self, key: str, value: Optional[Union[str, int]] = None) -> 'IpCmdBuilder':
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

    # --- Subcommands ---

    def rule(self) -> 'IpCmdBuilder':
        """Sets 'rule' as the subcommand for routing policy database management."""
        if self._subcommand:
            raise ValueError(f"Subcommand already set to '{self._subcommand}'")
        self._subcommand = "rule"
        self._command.append("rule")
        return self

    def address(self) -> 'IpCmdBuilder':
        """Sets 'address' as the subcommand for protocol address management."""
        if self._subcommand:
            raise ValueError(f"Subcommand already set to '{self._subcommand}'")
        self._subcommand = "address"
        self._command.append("address")
        return self

    def route(self) -> 'IpCmdBuilder':
        """Sets 'route' as the subcommand for routing table management."""
        if self._subcommand:
            raise ValueError(f"Subcommand already set to '{self._subcommand}'")
        self._subcommand = "route"
        self._command.append("route")
        return self

    def link(self) -> 'IpCmdBuilder':
        """Sets 'link' as the subcommand for network device configuration."""
        if self._subcommand:
            raise ValueError(f"Subcommand already set to '{self._subcommand}'")
        self._subcommand = "link"
        self._command.append("link")
        return self

    def netns(self) -> 'IpCmdBuilder':
        """Sets 'netns' as the subcommand for network namespace management."""
        if self._subcommand:
            raise ValueError(f"Subcommand already set to '{self._subcommand}'")
        self._subcommand = "netns"
        self._command.append("netns")
        return self

    # --- Actions ---

    def show(self) -> 'IpCmdBuilder':
        """Adds 'show' action to display current configuration."""
        if self._action:
            raise ValueError(f"Action already set to '{self._action}'")
        self._action = "show"
        self._command.append("show")
        return self

    def list(self) -> 'IpCmdBuilder':
        """Adds 'list' action (alias for show)."""
        if self._action:
            raise ValueError(f"Action already set to '{self._action}'")
        self._action = "list"
        self._command.append("list")
        return self

    def add(self) -> 'IpCmdBuilder':
        """Adds 'add' action to create new entry."""
        if self._action:
            raise ValueError(f"Action already set to '{self._action}'")
        self._action = "add"
        self._command.append("add")
        return self

    def delete(self) -> 'IpCmdBuilder':
        """Adds 'delete' action to remove entry."""
        if self._action:
            raise ValueError(f"Action already set to '{self._action}'")
        self._action = "delete"
        self._command.append("delete")
        return self

    def flush(self) -> 'IpCmdBuilder':
        """Adds 'flush' action to remove all entries."""
        if self._action:
            raise ValueError(f"Action already set to '{self._action}'")
        self._action = "flush"
        self._command.append("flush")
        return self

    # --- Rule-specific Options ---

    def table(self, table_name: str) -> 'IpCmdBuilder':
        """
        Adds 'table' selector for routing table.

        Args:
            table_name: Routing table name or ID (main, local, default, or numeric)
        """
        self._command.extend(["table", table_name])
        return self

    def priority(self, prio: Union[str, int]) -> 'IpCmdBuilder':
        """
        Adds 'priority' (or 'pref') option for rule priority.

        Args:
            prio: Priority value (lower number = higher priority)
        """
        self._command.extend(["priority", str(prio)])
        return self

    def from_addr(self, address: str) -> 'IpCmdBuilder':
        """
        Adds 'from' selector for source address matching.

        Args:
            address: Source address prefix (e.g., '192.168.1.0/24' or 'all')
        """
        self._command.extend(["from", address])
        return self

    def to_addr(self, address: str) -> 'IpCmdBuilder':
        """
        Adds 'to' selector for destination address matching.

        Args:
            address: Destination address prefix (e.g., '10.0.0.0/8' or 'all')
        """
        self._command.extend(["to", address])
        return self

    def iif(self, interface: str) -> 'IpCmdBuilder':
        """
        Adds 'iif' selector for incoming interface matching.

        Args:
            interface: Input interface name
        """
        self._command.extend(["iif", interface])
        return self

    def oif(self, interface: str) -> 'IpCmdBuilder':
        """
        Adds 'oif' selector for outgoing interface matching.

        Args:
            interface: Output interface name
        """
        self._command.extend(["oif", interface])
        return self

    def fwmark(self, mark: Union[str, int], mask: Optional[Union[str, int]] = None) -> 'IpCmdBuilder':
        """
        Adds 'fwmark' selector for firewall mark matching.

        Args:
            mark: Firewall mark value
            mask: Optional mask for the mark
        """
        mark_str: str = str(mark)
        if mask is not None:
            mark_str = f"{mark}/{mask}"
        self._command.extend(["fwmark", mark_str])
        return self

    def lookup(self, table_name: str) -> 'IpCmdBuilder':
        """
        Adds 'lookup' action to specify routing table for lookup.

        Args:
            table_name: Routing table name or ID
        """
        self._command.extend(["lookup", table_name])
        return self

    # --- Positional Arguments ---

    def positional_arg(self, value: Union[str, int]) -> 'IpCmdBuilder':
        """
        Adds a positional argument to the command.

        Args:
            value: The positional argument value
        """
        self._command.append(str(value))
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
        if as_string:
            return " ".join(shlex.quote(part) for part in self._command)
        else:
            return list(self._command)

    def get_command_list(self) -> List[str]:
        """Builds the command and returns it as a list of arguments."""
        result: Union[str, List[str]] = self.build(as_string=False)
        return result  # type: ignore

    def get_command_string(self) -> str:
        """Builds the command and returns it as a shell-quoted string."""
        result: Union[str, List[str]] = self.build(as_string=True)
        return result  # type: ignore

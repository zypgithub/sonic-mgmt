import shlex
from typing import List, Optional, Union


class SmartctlCmdBuilder:
    """
    A builder class for constructing smartctl (SMART disk utility) commands.
    Note: Commands are always prefixed with sudo as smartctl requires root privileges.

    Examples:
        # Print all SMART information for a device
        cmd = SmartctlCmdBuilder().all().device('/dev/sda').build()
        # Result: sudo smartctl /dev/sda -a

        # With grep filter
        cmd = SmartctlCmdBuilder().all().device('/dev/nvme0n1').grep('Model Number').build()
        # Result: sudo smartctl /dev/nvme0n1 -a | grep 'Model Number'
    """

    def __init__(self) -> None:
        """Initialize the smartctl command builder. Commands always use sudo."""
        self._command: List[str] = []
        self._device_path: Optional[str] = None
        self._grep_pattern: Optional[str] = None
        self._grep_options: List[str] = []

    def all(self) -> 'SmartctlCmdBuilder':
        """
        Add -a flag to print all SMART information about the device.
        This is the most comprehensive smartctl option.

        Returns:
            Self for method chaining.
        """
        self._command.append('-a')
        return self

    def device(self, device_path: str) -> 'SmartctlCmdBuilder':
        """
        Specify the device path for smartctl to query.

        Args:
            device_path: Path to the device (e.g., '/dev/sda', '/dev/nvme0n1').

        Returns:
            Self for method chaining.
        """
        self._device_path = device_path
        return self

    def option(self, key: str, value: Optional[Union[str, int]] = None) -> 'SmartctlCmdBuilder':
        """
        Add a generic option flag or key-value option.

        Args:
            key: The option name (without leading dash).
            value: Optional value for the option.

        Returns:
            Self for method chaining.
        """
        self._command.append(f'-{key}')
        if value is not None:
            self._command.append(str(value))
        return self

    def grep(self, pattern: str, case_insensitive: bool = False,
             invert_match: bool = False, extended_regexp: bool = False) -> 'SmartctlCmdBuilder':
        """
        Add a grep filter to the command pipeline.

        Args:
            pattern: The pattern to search for.
            case_insensitive: If True, adds -i flag for case-insensitive matching.
            invert_match: If True, adds -v flag to invert match (select non-matching lines).
            extended_regexp: If True, adds -E flag for extended regular expressions.

        Returns:
            Self for method chaining.
        """
        self._grep_pattern = pattern
        self._grep_options = []

        if case_insensitive:
            self._grep_options.append('-i')
        if invert_match:
            self._grep_options.append('-v')
        if extended_regexp:
            self._grep_options.append('-E')

        return self

    def build(self, as_string: bool = True) -> Union[str, List[str]]:
        """
        Construct the final command.

        Args:
            as_string: If True (default), returns the command as a single shell-quoted string.
                      If False, returns a list of command parts.

        Returns:
            The constructed command string or list.

        Raises:
            ValueError: If device path is not specified.

        Example:
            cmd = SmartctlCmdBuilder().all().device('/dev/sda').build()
            # Returns: "sudo smartctl /dev/sda -a"
        """
        if not self._device_path:
            raise ValueError("Device path must be specified using device() method")

        full_command: List[str] = []

        # Always add sudo (smartctl requires root privileges)
        full_command.append('sudo')

        # Add smartctl
        full_command.append('smartctl')

        # Add device path first
        full_command.append(self._device_path)

        # Add options after device (e.g., -a)
        full_command.extend(self._command)

        # Add grep pipeline if specified
        if self._grep_pattern:
            if as_string:
                smartctl_part: str = " ".join(shlex.quote(part) for part in full_command)
                grep_cmd_parts: List[str] = ["grep"] + self._grep_options + [self._grep_pattern]
                grep_part: str = " ".join(shlex.quote(part) for part in grep_cmd_parts)
                return f"{smartctl_part} | {grep_part}"
            else:
                # For list format, we can't easily represent pipes, so return the combined command as string
                raise ValueError("Grep pipeline requires as_string=True format")

        if as_string:
            return " ".join(shlex.quote(part) for part in full_command)
        else:
            return full_command

    def get_command_list(self) -> List[str]:
        """
        Build the command and return it as a list of arguments.
        Note: This will raise ValueError if grep is used, as pipes can't be represented as list.

        Returns:
            Command as a list of strings.
        """
        return self.build(as_string=False)  # type: ignore

    def get_command_string(self) -> str:
        """
        Build the command and return it as a shell-quoted string.

        Returns:
            Command as a shell-safe string.
        """
        return self.build(as_string=True)  # type: ignore

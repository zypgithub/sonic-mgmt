import shlex
from typing import List, Optional, Union


class LsblkCmdBuilder:
    """
    A builder class for constructing lsblk (list block devices) commands.

    Examples:
        # List specific columns with grep filter
        cmd = LsblkCmdBuilder().output_columns(['NAME', 'SIZE', 'TYPE', 'MOUNTPOINT']).grep('nvme').build()
        # Result: lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | grep nvme

        # Filesystem info with filter
        cmd = LsblkCmdBuilder().filesystem().grep('nvme').build()
        # Result: lsblk -f | grep nvme

        # No dependents, no headings with specific columns
        cmd = LsblkCmdBuilder().nodeps().no_headings().output_columns(['NAME', 'SIZE']).grep('nvme').build()
        # Result: lsblk -dn -o NAME,SIZE | grep nvme
    """

    def __init__(self) -> None:
        """Initialize the lsblk command builder."""
        self._command: List[str] = ["lsblk"]
        self._grep_pattern: Optional[str] = None
        self._grep_options: List[str] = []

    def output_columns(self, columns: Union[List[str], str]) -> 'LsblkCmdBuilder':
        """
        Specify output columns with -o option.

        Args:
            columns: Either a list of column names or a comma-separated string.
                    Common columns: NAME, SIZE, TYPE, MOUNTPOINT, FSTYPE, UUID, MODEL, etc.

        Returns:
            Self for method chaining.

        Example:
            builder.output_columns(['NAME', 'SIZE', 'TYPE'])
            builder.output_columns('NAME,SIZE,TYPE')
        """
        if isinstance(columns, list):
            columns_str: str = ','.join(columns)
        else:
            columns_str = columns

        self._command.append('-o')
        self._command.append(columns_str)
        return self

    def filesystem(self) -> 'LsblkCmdBuilder':
        """
        Add -f flag to output info about filesystems.

        Returns:
            Self for method chaining.
        """
        self._command.append('-f')
        return self

    def nodeps(self) -> 'LsblkCmdBuilder':
        """
        Add -d flag to not print holder devices or slaves (no dependents).

        Returns:
            Self for method chaining.
        """
        self._command.append('-d')
        return self

    def no_headings(self) -> 'LsblkCmdBuilder':
        """
        Add -n flag to not print column headings.

        Returns:
            Self for method chaining.
        """
        self._command.append('-n')
        return self

    def pairs(self) -> 'LsblkCmdBuilder':
        """
        Add -P flag to produce output in key="value" pairs format.

        Returns:
            Self for method chaining.
        """
        self._command.append('-P')
        return self

    def raw(self) -> 'LsblkCmdBuilder':
        """
        Add -r flag to produce output in raw format (no tree formatting).

        Returns:
            Self for method chaining.
        """
        self._command.append('-r')
        return self

    def bytes(self) -> 'LsblkCmdBuilder':
        """
        Add -b flag to print SIZE in bytes rather than human-readable format.

        Returns:
            Self for method chaining.
        """
        self._command.append('-b')
        return self

    def paths(self) -> 'LsblkCmdBuilder':
        """
        Add -p flag to print full device paths.

        Returns:
            Self for method chaining.
        """
        self._command.append('-p')
        return self

    def all(self) -> 'LsblkCmdBuilder':
        """
        Add -a flag to print all devices including empty ones.

        Returns:
            Self for method chaining.
        """
        self._command.append('-a')
        return self

    def ascii(self) -> 'LsblkCmdBuilder':
        """
        Add -i flag to use ASCII characters for tree formatting.

        Returns:
            Self for method chaining.
        """
        self._command.append('-i')
        return self

    def json(self) -> 'LsblkCmdBuilder':
        """
        Add -J flag to use JSON output format.

        Returns:
            Self for method chaining.
        """
        self._command.append('-J')
        return self

    def perms(self) -> 'LsblkCmdBuilder':
        """
        Add -m flag to output info about device owner, group and mode.

        Returns:
            Self for method chaining.
        """
        self._command.append('-m')
        return self

    def scsi(self) -> 'LsblkCmdBuilder':
        """
        Add -S flag to output info about SCSI devices only.

        Returns:
            Self for method chaining.
        """
        self._command.append('-S')
        return self

    def topology(self) -> 'LsblkCmdBuilder':
        """
        Add -t flag to output info about block device topology.

        Returns:
            Self for method chaining.
        """
        self._command.append('-t')
        return self

    def option(self, key: str, value: Optional[Union[str, int]] = None) -> 'LsblkCmdBuilder':
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

    def device(self, device_path: str) -> 'LsblkCmdBuilder':
        """
        Add a specific device path as positional argument.

        Args:
            device_path: Path to the device (e.g., '/dev/sda', '/dev/nvme0n1').

        Returns:
            Self for method chaining.
        """
        self._command.append(device_path)
        return self

    def grep(self, pattern: str, case_insensitive: bool = False,
             invert_match: bool = False, extended_regexp: bool = False) -> 'LsblkCmdBuilder':
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

        Example:
            cmd = builder.output_columns(['NAME', 'SIZE']).grep('nvme').build()
            # Returns: "lsblk -o NAME,SIZE | grep nvme"
        """
        full_command: List[str] = self._command.copy()

        # Add grep pipeline if specified
        if self._grep_pattern:
            # First, build the lsblk portion as a string
            if as_string:
                lsblk_part: str = " ".join(shlex.quote(part) for part in full_command)
                grep_cmd_parts: List[str] = ["grep"] + self._grep_options + [self._grep_pattern]
                grep_part: str = " ".join(shlex.quote(part) for part in grep_cmd_parts)
                return f"{lsblk_part} | {grep_part}"
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

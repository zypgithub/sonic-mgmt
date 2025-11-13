import shlex
from typing import List, Optional, Union


class DfCmdBuilder:
    """
    A builder class for constructing df (disk free) commands.

    Examples:
        # Basic human-readable output
        cmd = DfCmdBuilder().human_readable().build()
        # Result: df -h

        # SI units with specific path
        cmd = DfCmdBuilder().si_units().path('/').build()
        # Result: df -H /

        # Show inodes with grep filter
        cmd = DfCmdBuilder().inodes().grep('/dev/sda').build()
        # Result: df -i | grep /dev/sda

        # Specific filesystem type with totals
        cmd = DfCmdBuilder().human_readable().filesystem_type('ext4').show_total().build()
        # Result: df -h -t ext4 --total

        # Custom output columns
        cmd = DfCmdBuilder().output_columns(['source', 'size', 'used', 'avail', 'pcent', 'target']).build()
        # Result: df --output=source,size,used,avail,pcent,target

        # Local filesystems only with grep
        cmd = DfCmdBuilder().human_readable().local_only().grep('/$').build()
        # Result: df -h -l | grep '/$'
    """

    def __init__(self) -> None:
        """Initialize the df command builder."""
        self._command: List[str] = ["df"]
        self._paths: List[str] = []
        self._grep_pattern: Optional[str] = None
        self._grep_options: List[str] = []

    def human_readable(self) -> 'DfCmdBuilder':
        """
        Add -h flag to print sizes in human-readable format (e.g., 1K, 234M, 2G).
        Uses powers of 1024.

        Returns:
            Self for method chaining.
        """
        self._command.append('-h')
        return self

    def si_units(self) -> 'DfCmdBuilder':
        """
        Add -H flag to print sizes in human-readable format using powers of 1000 (SI units).

        Returns:
            Self for method chaining.
        """
        self._command.append('-H')
        return self

    def all_filesystems(self) -> 'DfCmdBuilder':
        """
        Add -a flag to include pseudo, duplicate, and inaccessible file systems.

        Returns:
            Self for method chaining.
        """
        self._command.append('-a')
        return self

    def inodes(self) -> 'DfCmdBuilder':
        """
        Add -i flag to list inode information instead of block usage.

        Returns:
            Self for method chaining.
        """
        self._command.append('-i')
        return self

    def show_type(self) -> 'DfCmdBuilder':
        """
        Add -T flag to print filesystem type.

        Returns:
            Self for method chaining.
        """
        self._command.append('-T')
        return self

    def filesystem_type(self, fs_type: str) -> 'DfCmdBuilder':
        """
        Add -t option to limit listing to specified filesystem type.

        Args:
            fs_type: Filesystem type (e.g., 'ext4', 'xfs', 'tmpfs', 'nfs').

        Returns:
            Self for method chaining.

        Example:
            builder.filesystem_type('ext4')
        """
        self._command.append('-t')
        self._command.append(fs_type)
        return self

    def exclude_type(self, fs_type: str) -> 'DfCmdBuilder':
        """
        Add -x option to exclude specified filesystem type from listing.

        Args:
            fs_type: Filesystem type to exclude (e.g., 'tmpfs', 'devtmpfs').

        Returns:
            Self for method chaining.

        Example:
            builder.exclude_type('tmpfs')
        """
        self._command.append('-x')
        self._command.append(fs_type)
        return self

    def local_only(self) -> 'DfCmdBuilder':
        """
        Add -l flag to limit listing to local file systems only.

        Returns:
            Self for method chaining.
        """
        self._command.append('-l')
        return self

    def show_total(self) -> 'DfCmdBuilder':
        """
        Add --total flag to produce a grand total at the end.

        Returns:
            Self for method chaining.
        """
        self._command.append('--total')
        return self

    def portability(self) -> 'DfCmdBuilder':
        """
        Add -P flag to use POSIX output format (portable format).

        Returns:
            Self for method chaining.
        """
        self._command.append('-P')
        return self

    def block_size(self, size: Union[str, int]) -> 'DfCmdBuilder':
        """
        Add -B option to specify block size.

        Args:
            size: Block size (e.g., '1K', '1M', '1G', or integer).

        Returns:
            Self for method chaining.

        Example:
            builder.block_size('1M')
            builder.block_size(1024)
        """
        self._command.append('-B')
        self._command.append(str(size))
        return self

    def output_columns(self, columns: Union[List[str], str]) -> 'DfCmdBuilder':
        """
        Specify output columns with --output option.

        Args:
            columns: Either a list of column names or a comma-separated string.
                    Common columns: source, fstype, itotal, iused, iavail, ipcent,
                                  size, used, avail, pcent, file, target

        Returns:
            Self for method chaining.

        Example:
            builder.output_columns(['source', 'size', 'used', 'avail', 'pcent', 'target'])
            builder.output_columns('source,size,used,avail,pcent,target')
        """
        if isinstance(columns, list):
            columns_str: str = ','.join(columns)
        else:
            columns_str = columns

        self._command.append(f'--output={columns_str}')
        return self

    def sync(self) -> 'DfCmdBuilder':
        """
        Add --sync flag to invoke sync before getting usage info.

        Returns:
            Self for method chaining.
        """
        self._command.append('--sync')
        return self

    def no_sync(self) -> 'DfCmdBuilder':
        """
        Add --no-sync flag to not invoke sync before getting usage info (default).

        Returns:
            Self for method chaining.
        """
        self._command.append('--no-sync')
        return self

    def print_type(self) -> 'DfCmdBuilder':
        """
        Add --print-type flag to print filesystem type (alias for -T).

        Returns:
            Self for method chaining.
        """
        self._command.append('--print-type')
        return self

    def option(self, key: str, value: Optional[Union[str, int]] = None) -> 'DfCmdBuilder':
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

    def path(self, path: str) -> 'DfCmdBuilder':
        """
        Add a specific filesystem path to check.

        Args:
            path: Path to the filesystem or mount point (e.g., '/', '/home', '/dev/sda1').

        Returns:
            Self for method chaining.

        Example:
            builder.path('/')
            builder.path('/home')
        """
        self._paths.append(path)
        return self

    def paths(self, paths: List[str]) -> 'DfCmdBuilder':
        """
        Add multiple filesystem paths to check.

        Args:
            paths: List of paths to the filesystems or mount points.

        Returns:
            Self for method chaining.

        Example:
            builder.paths(['/', '/home', '/var'])
        """
        self._paths.extend(paths)
        return self

    def grep(self, pattern: str, case_insensitive: bool = False,
             invert_match: bool = False, extended_regexp: bool = False) -> 'DfCmdBuilder':
        """
        Add a grep filter to the command pipeline.

        Args:
            pattern: The pattern to search for.
            case_insensitive: If True, adds -i flag for case-insensitive matching.
            invert_match: If True, adds -v flag to invert match (select non-matching lines).
            extended_regexp: If True, adds -E flag for extended regular expressions.

        Returns:
            Self for method chaining.

        Example:
            builder.human_readable().grep('/dev/sda')
            builder.human_readable().grep('/$', case_insensitive=True)
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
            cmd = builder.human_readable().path('/').grep('/$').build()
            # Returns: "df -h / | grep '/$'"
        """
        full_command: List[str] = self._command.copy()

        # Add paths at the end (positional arguments)
        if self._paths:
            full_command.extend(self._paths)

        # Add grep pipeline if specified
        if self._grep_pattern:
            if as_string:
                df_part: str = " ".join(shlex.quote(part) for part in full_command)
                grep_cmd_parts: List[str] = ["grep"] + self._grep_options + [self._grep_pattern]
                grep_part: str = " ".join(shlex.quote(part) for part in grep_cmd_parts)
                return f"{df_part} | {grep_part}"
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

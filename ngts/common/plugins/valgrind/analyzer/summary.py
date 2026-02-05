from __future__ import annotations

from io import TextIOWrapper
from typing import Self
import dataclasses
import logging

from .enums import BugHandlerScope, LeakKind
from .trace_id import TraceIdComputer
from .records import LeakRecord
from . import _text

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class DecisionConfig:
    """ DecisionConfig is a dataclass that encapsulates the decision configuration for a Valgrind summary. """

    definitely_threshold: int = dataclasses.field(default=0, metadata={"name": "Definitely Lost Threshold", "fmt": _text.to_readable})
    indirectly_threshold: int = dataclasses.field(default=0, metadata={"name": "Indirectly Lost Threshold", "fmt": _text.to_readable})
    possibly_threshold: int = dataclasses.field(default=0, metadata={"name": "Possibly Lost Threshold", "fmt": _text.to_readable})
    fail_on_warnings: bool = dataclasses.field(default=False, metadata={"name": "Fail On Warnings Flag"})
    bug_handler_scope: BugHandlerScope = dataclasses.field(default=BugHandlerScope.SUB_SERVICE, metadata={"name": "Bug Handler Scope"})

    def __str__(self) -> str:
        result = ""
        for field in dataclasses.fields(self):
            if field.metadata.get('name'):
                value = getattr(self, field.name)
                if formatter := field.metadata.get('fmt'):
                    value = formatter(value)
                result += f"{field.metadata['name']:<{_text.T_SPACE}}: {value}\n"
        return result.rstrip()

    @property
    def is_default_config(self) -> bool:
        for field in dataclasses.fields(self):
            if field.default != getattr(self, field.name):
                return False
        return True


@dataclasses.dataclass(eq=False)
class Counters:
    """ Counters is a dataclass that encapsulates the counters for a Valgrind summary. """

    definitely_lost: int = 0
    indirectly_lost: int = 0
    possibly_lost: int = 0
    still_reachable: int = 0

    ignored_definitely_lost: int = dataclasses.field(default=0, repr=False)
    ignored_indirectly_lost: int = dataclasses.field(default=0, repr=False)
    ignored_possibly_lost: int = dataclasses.field(default=0, repr=False)
    ignored_still_reachable: int = dataclasses.field(default=0, repr=False)

    def __str__(self) -> str:

        string = ""
        string += f"{'Definitely Lost':<{_text.T_SPACE}}: {_text.to_readable(self.definitely_lost):<9} "
        string += f"({_text.to_readable(self.ignored_definitely_lost)} ignored)\n"

        string += f"{'Indirectly Lost':<{_text.T_SPACE}}: {_text.to_readable(self.indirectly_lost):<9} "
        string += f"({_text.to_readable(self.ignored_indirectly_lost)} ignored)\n"

        string += f"{'Possibly Lost':<{_text.T_SPACE}}: {_text.to_readable(self.possibly_lost):<9} "
        string += f"({_text.to_readable(self.ignored_possibly_lost)} ignored)\n"

        string += f"{'Still Reachable':<{_text.T_SPACE}}: {_text.to_readable(self.still_reachable):<9} "
        string += f"({_text.to_readable(self.ignored_still_reachable)} ignored)\n"
        return string.rstrip()

    # arithmetic
    def __add__(self, other: Self) -> Self:
        return Counters(
            self.definitely_lost + other.definitely_lost,
            self.indirectly_lost + other.indirectly_lost,
            self.possibly_lost + other.possibly_lost,
            self.still_reachable + other.still_reachable,
            self.ignored_definitely_lost + other.ignored_definitely_lost,
            self.ignored_indirectly_lost + other.ignored_indirectly_lost,
            self.ignored_possibly_lost + other.ignored_possibly_lost,
            self.ignored_still_reachable + other.ignored_still_reachable,
        )

    def __iadd__(self, other: Self) -> Self:
        self.definitely_lost += other.definitely_lost
        self.indirectly_lost += other.indirectly_lost
        self.possibly_lost += other.possibly_lost
        self.still_reachable += other.still_reachable
        self.ignored_definitely_lost += other.ignored_definitely_lost
        self.ignored_indirectly_lost += other.ignored_indirectly_lost
        self.ignored_possibly_lost += other.ignored_possibly_lost
        self.ignored_still_reachable += other.ignored_still_reachable
        return self

    # ordering (severity: definitely > indirectly > possibly > still)
    def _key(self) -> tuple[int, int, int, int]:
        return (self.definitely_lost, self.indirectly_lost, self.possibly_lost, self.still_reachable)

    def __lt__(self, other: Self) -> bool: return self._key() < other._key()  # noqa: E704
    def __le__(self, other: Self) -> bool: return self._key() <= other._key()  # noqa: E704
    def __gt__(self, other: Self) -> bool: return self._key() > other._key()  # noqa: E704
    def __ge__(self, other: Self) -> bool: return self._key() >= other._key()  # noqa: E704
    def __eq__(self, other: object) -> bool: return isinstance(other, Counters) and self._key() == other._key()  # noqa: E704


@dataclasses.dataclass(frozen=True)
class RecordPolicy:
    """
    RecordPolicy is a dataclass that encapsulates the policy for recording Valgrind summary records.
    It holds information about the ignore ids and the count still flag.
    """

    ignore_ids: set[str] = dataclasses.field(default_factory=set)
    count_still: bool = False


@dataclasses.dataclass
class ValgrindSummary:
    """
    ValgrindSummary is a dataclass that encapsulates the summary of a Valgrind analysis report for a given service (and optionally, subservice).
    It holds information about various core memory counters (definitely lost, indirectly lost, possibly lost, still reachable, plus their ignored counterparts),
    error counts, warnings, and flags indicating hard errors such as invalid reads/writes, among other statistics captured from the Valgrind tool's output.

    The class provides a custom string representation for pretty-printing as a report, and implements __bool__ to allow quick checking
    if there are any definite, indirect, or possible memory losses.
    """

    # identity
    service: str
    subservice: str | None = dataclasses.field(default=None, metadata={"name": "Sub Service", 'no-none-print': True})

    # core numbers
    counters: Counters = dataclasses.field(default_factory=Counters, metadata={'no-key-print': True})
    errors: int = dataclasses.field(default=0, metadata={"name": "Errors", 'fmt': '{:,}'})

    # signals (hard errors)
    invalid_read: bool = dataclasses.field(default=False)
    invalid_write: bool = dataclasses.field(default=False)
    uninitialised: bool = dataclasses.field(default=False)
    invalid_free: bool = dataclasses.field(default=False)

    # warnings
    invalid_fd_close_count: int = dataclasses.field(default=0, metadata={"name": "Invalid FD Close", 'fmt': '{:,}'})
    invalid_fd_syscalls: dict[str, int] = dataclasses.field(default_factory=dict, metadata={"name": "Invalid FD Close Syscalls"})  # e.g., {"close": 12, "dup2": 3}  # noqa: E501
    generic_warning_count: int = dataclasses.field(default=0, metadata={"name": "Generic Warning"})

    # stacks
    leak_trace_count: int = dataclasses.field(default=0, metadata={"name": "Leak Trace", 'fmt': '{:,}'})
    # leak_groups: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict, repr=False, metadata={"exclude": True})  # if not to be used, remove it
    capped_summary: str = dataclasses.field(default="", repr=False, metadata={"exclude": True})

    def __str__(self) -> str:
        string = ""
        for field in dataclasses.fields(self):
            if field.metadata.get('exclude'):
                continue
            if field.metadata.get('no-key-print'):
                string += f"{getattr(self, field.name)}\n"
            elif field.metadata.get('name'):
                value = getattr(self, field.name)
                if field.metadata.get('no-none-print') and value is None:
                    continue
                if field.metadata.get('fmt'):
                    value = field.metadata['fmt'].format(value)
                string += f"{field.metadata['name']:<{_text.T_SPACE}}: {value}\n"
            elif field.metadata.get('tr'):
                string += "=" * 80 + "\n"
                string += f"{field.name:<{_text.T_SPACE}}: {getattr(self, field.name)}\n"
            else:
                key = field.name.replace("_", " ").title()
                string += f"{key:<{_text.T_SPACE}}: {getattr(self, field.name)}\n"
        return string.rstrip()

    def __bool__(self) -> bool:
        return self.counters.definitely_lost > 0 \
            or self.counters.indirectly_lost > 0 \
            or self.counters.possibly_lost > 0 \
            or self.errors > 0 \
            or self.invalid_read \
            or self.invalid_write \
            or self.uninitialised \
            or self.invalid_free \
            or self.generic_warning_count > 0 \
            or self.invalid_fd_close_count > 0 \
            or self.leak_trace_count > 0

    def __iadd__(self, other: Self) -> Self:
        self.counters += other.counters
        self.errors += other.errors
        self.invalid_read |= other.invalid_read
        self.invalid_write |= other.invalid_write
        self.uninitialised |= other.uninitialised
        self.invalid_free |= other.invalid_free
        self.invalid_fd_close_count += other.invalid_fd_close_count

        for syscall, count in other.invalid_fd_syscalls.items():
            self.invalid_fd_syscalls[syscall] = self.invalid_fd_syscalls.get(syscall, 0) + count

        self.generic_warning_count += other.generic_warning_count
        self.leak_trace_count += other.leak_trace_count

        if other.capped_summary:
            if self.capped_summary:
                self.capped_summary += f"\n{other.capped_summary}"
            else:
                self.capped_summary = other.capped_summary

        return self

    @staticmethod
    def _to_int_bytes(s: str) -> int:
        '''
        Convert the string to an integer bytes.

        :param s: The string to convert.
        :return: The integer bytes.
        '''
        m = _text.BYTES_RE.search(s)
        return int(m.group(1).replace(",", "")) if m else 0

    @classmethod
    def parse_from_io(
        cls,
        service: str,
        subservice: str | None,
        file: TextIOWrapper,
        policy: RecordPolicy = RecordPolicy(),
        trace_id_computer: TraceIdComputer | None = None,
    ) -> Self:
        """
        Parse the Valgrind summary from the IO.

        :param service: The service of the summary.
        :param subservice: The subservice of the summary.
        :param file: The file to parse the summary from.
        :param policy: The policy to use for the summary.
        :param trace_id_computer: The trace id computer to use for the summary.
        :return: The Valgrind summary.
        """
        summary = cls(service=service, subservice=subservice)

        capped_summary_lines = 0

        while line := file.readline():
            ls = _text.strip_pid_prefix(line := line.rstrip())
            if (tmp := summary.capped_summary.count('\n')) != capped_summary_lines:
                capped_summary_lines = tmp

            if ls.startswith('Process terminating with default action of signal'):
                while sk := file.readline():
                    if not _text.strip_pid_prefix(sk).strip():
                        break
                continue

            # --- leak record header -> delegate to _consume_leak_record_block (inner loop consumes the block) ---
            elif (m := _text.LEAK_RECORD_RE.match(ls)):
                rec = LeakRecord.from_io(m, file, trace_id_computer=trace_id_computer)

                ignored = rec.trace_id in policy.ignore_ids

                if ignored:
                    if rec.kind is LeakKind.DEFINITE:
                        summary.counters.ignored_definitely_lost += rec.bytes
                    elif rec.kind is LeakKind.INDIRECT:
                        summary.counters.ignored_indirectly_lost += rec.bytes
                    elif rec.kind is LeakKind.POSSIBLE:
                        summary.counters.ignored_possibly_lost += rec.bytes
                    continue
                else:
                    # accumulate by kind
                    if rec.kind is LeakKind.DEFINITE:
                        summary.counters.definitely_lost += rec.bytes
                    elif rec.kind is LeakKind.INDIRECT:
                        summary.counters.indirectly_lost += rec.bytes
                    elif rec.kind is LeakKind.POSSIBLE:
                        summary.counters.possibly_lost += rec.bytes
                    elif policy.count_still:  # STILL reachable -> usually noise; count only if you want to track it
                        summary.counters.still_reachable += rec.bytes

                summary.leak_trace_count += 1

            # --- warnings (keep original text, count invalid-fd precisely) ---
            elif ls.startswith("Warning:"):
                summary.capped_summary += line + "\n"
                if (wm := _text.INV_FD_RE.match(ls)):
                    summary.invalid_fd_close_count += 1
                    syscall = wm.group(2).lower()
                    summary.invalid_fd_syscalls[syscall] = summary.invalid_fd_syscalls.get(syscall, 0) + 1
                else:
                    summary.generic_warning_count += 1

            # --- signals (cheap substring checks; not used for math) ---
            # TODO: check if we need to consider them as warnings and count them as generic warnings
            elif (not summary.invalid_read) and ("Invalid read of size" in ls):
                summary.invalid_read = True
            elif (not summary.invalid_write) and ("Invalid write of size" in ls):
                summary.invalid_write = True
            elif (not summary.uninitialised) and ("uninitialised value" in ls or "depends on uninitialised value" in ls):
                summary.uninitialised = True
            elif (not summary.invalid_free) and ("Invalid free" in ls or "Mismatched free/delete" in ls):
                summary.invalid_free = True

            # --- heap summary ---
            elif ls.startswith("HEAP SUMMARY"):
                if summary.capped_summary and (m := _text.PID_PREFIX_RE.search(summary.capped_summary)):
                    summary.capped_summary += (m.group(0) + "\n")

                summary.capped_summary += f'{line}\n'
                while line := file.readline().rstrip():
                    if not _text.strip_pid_prefix(line).strip():
                        break
                    summary.capped_summary += line

            # leak summary
            elif ls.startswith("LEAK SUMMARY"):
                if not (leak_summary := file.read().rstrip()).strip():
                    continue

                if summary.capped_summary:
                    summary.capped_summary += (_text.PID_PREFIX_RE.search(summary.capped_summary).group(0) + "\n")
                summary.capped_summary += f'{line}\n{leak_summary}'

                if m := _text.ERR_SUM_RE.search(leak_summary):
                    summary.errors = int(m.group(1))
                break

        return summary

    def primary_leak_signature(self, cnf: DecisionConfig | None = None) -> str | None:
        """Pick the leak-kind signature for bug titles (no log parsing).

        This relies on the structured counters already computed by the analyzer (and optionally the configured thresholds),
        rather than matching raw log substrings like "indirectly lost" which appear even when the counter is `0`.
        """
        counters = self.counters

        if cnf is not None:
            if counters.definitely_lost > cnf.definitely_threshold:
                return "definitely lost"
            if counters.indirectly_lost > cnf.indirectly_threshold:
                return "indirectly lost"
            if counters.possibly_lost > cnf.possibly_threshold:
                return "possibly lost"

        if counters.definitely_lost:
            return "definitely lost"
        if counters.indirectly_lost:
            return "indirectly lost"
        if counters.possibly_lost:
            return "possibly lost"
        return None

    def has_issues(self, cnf: DecisionConfig) -> bool:
        """
        Check if the summary has issues.

        :param cnf: The decision configuration.
        :return: True if the summary has issues, False otherwise.
        """
        # Hard Memcheck findings and explicit error counts are always issues (independent of leak thresholds).
        if self.invalid_read or self.invalid_write or self.uninitialised or self.invalid_free:
            return True
        if self.errors > 0:
            return True

        if self.counters.definitely_lost > cnf.definitely_threshold:
            return True
        if self.counters.indirectly_lost > cnf.indirectly_threshold:
            return True
        if self.counters.possibly_lost > cnf.possibly_threshold:
            return True

        if cnf.fail_on_warnings and (self.generic_warning_count + self.invalid_fd_close_count > 0):
            return True
        return False

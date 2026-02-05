from __future__ import annotations

from pathlib import Path
import logging

from .trace_id import TraceIdComputer
from .records import LeakRecord
from . import _text

logger = logging.getLogger(__name__)


class IgnoreRegistry:
    """Load and cache trace IDs to ignore, by scope (global/service/sub-service).

    Ignore file resolution (hierarchical):
    - ignore.global.txt
    - ignore.{service}.txt
    - ignore.{service}.{subservice}.txt  (only when subservice is not None)

    File format:
    - Either raw Valgrind leak record blocks, or explicit trace-id tokens (hex).
    """

    def __init__(self, *, ignore_dir: Path, trace_id_computer: TraceIdComputer | None = None):
        self._log = logger.getChild(self.__class__.__name__)
        self._ignore_dir = ignore_dir
        self._trace_id_computer = trace_id_computer or TraceIdComputer()
        self._cache: dict[Path, tuple[float, set[str]]] = {}

    @property
    def ignore_dir(self) -> Path:
        """ Get the ignore directory. """
        return self._ignore_dir

    @property
    def trace_id_computer(self) -> TraceIdComputer:
        """ Get the trace id computer. """
        return self._trace_id_computer

    def get_ignore_ids(self, *, service: str, subservice: str | None) -> set[str]:
        """
        Get the ignore ids.

        :param service: The service of the ignore ids.
        :param subservice: The subservice of the ignore ids.
        :return: The ignore ids.
        """
        ignore_ids: set[str] = set()
        paths = self._resolve_files(service=service, subservice=subservice)

        for path in paths:
            ignore_ids.update(self._load_ids(path))
        return ignore_ids

    def any_ignores_exist(self, *, service: str, subservice: str | None) -> bool:
        """
        Check if any ignores exist.

        :param service: The service of the ignores.
        :param subservice: The subservice of the ignores.
        :return: True if any ignores exist, False otherwise.
        """
        return any(path.exists() for path in self._resolve_files(service=service, subservice=subservice))

    def _resolve_files(self, *, service: str, subservice: str | None) -> tuple[Path, ...]:
        '''
        Resolve the files.

        :param service: The service of the files.
        :param subservice: The subservice of the files.
        :return: The files.
        '''
        base = self._ignore_dir
        files: list[Path] = [
            base / "ignore.global.txt",
            base / f"ignore.{service}.txt",
        ]
        if subservice:
            files.append(base / f"ignore.{service}.{subservice}.txt")
        return tuple(files)

    def _load_ids(self, path: Path) -> set[str]:
        '''
        Load the ids.

        :param path: The path to the ignore file.
        :return: The ids.
        '''
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return set()

        cached = self._cache.get(path)
        if cached and cached[0] == mtime:
            return set(cached[1])

        ids = self._parse_ignore_file(path)
        self._cache[path] = (mtime, ids)
        return set(ids)

    def _parse_ignore_file(self, path: Path) -> set[str]:
        '''
        Parse the ignore file.

        :param path: The path to the ignore file.
        :return: The ignore ids.
        '''
        if not path.exists():
            return set()

        ignore_ids: set[str] = set()
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                while True:
                    line = f.readline()
                    if not line:
                        break

                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue

                    # explicit trace-id token (allow trailing comments)
                    no_comment = stripped.split("#", 1)[0].strip()
                    if no_comment:
                        token = no_comment.split()[0]
                        if _text.TRACE_ID_TOKEN_RE.match(token):
                            ignore_ids.add(token.lower())
                            continue

                    # raw valgrind leak record block
                    if (m := _text.LEAK_RECORD_RE.match(_text.strip_pid_prefix(stripped))):
                        rec = LeakRecord.from_io(m, f, trace_id_computer=self._trace_id_computer)
                        ignore_ids.add(rec.trace_id)
        except OSError as exc:
            self._log.warning("Failed to read ignore file %s: %s", path, exc)
            return set()

        return ignore_ids

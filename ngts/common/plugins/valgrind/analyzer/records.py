from __future__ import annotations

from io import TextIOWrapper
from typing import Self
import dataclasses
import logging
import re

from . import _text
from .enums import LeakKind
from .trace_id import TraceIdComputer

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class LeakRecord:
    """
    Represents a single Valgrind memory leak record.

    Attributes:
        kind (LeakKind): The type of leak (definite, indirect, possible, or still reachable).
        bytes (int): The number of bytes leaked.
        blocks (int): The number of blocks involved in the leak.
        top_frame (str): The normalized top stack frame associated with the leak (derived from the first 'at/by' line).
        trace_id (str): A computed unique/stable identifier used for grouping or ignoring similar leak traces.

    Provides methods for parsing a leak record from text, normalizing stack frames, and identifying leak kinds from textual descriptors.
    """

    kind: LeakKind
    bytes: int
    blocks: int
    top_frame: str  # first 'at/by ' line (normalized to your liking)
    trace_id: str  # stable id for ignore-set membership

    @staticmethod
    def _normalize_frame(frame: str) -> str:
        ''' Normalize the frame. '''
        f = frame.strip().lower()
        f = _text.ADDR_NOISE_RE.sub('', f)  # strip addresses/offsets/linenos
        f = ' '.join(f.split())  # collapse whitespace
        return f

    @staticmethod
    def _to_int(s: str) -> int:
        ''' Convert the string to an integer. '''
        return int(s.replace(',', ''))

    @staticmethod
    def _kind_from_str(tok: str) -> LeakKind:
        ''' Convert the string to the leak kind. '''
        tok = tok.lower()
        if tok.startswith('definitely'):
            return LeakKind.DEFINITE
        elif tok.startswith('indirectly'):
            return LeakKind.INDIRECT
        elif tok.startswith('possibly'):
            return LeakKind.POSSIBLE
        else:
            return LeakKind.STILL  # "still reachable"

    @classmethod
    def from_io(
        cls,
        header_match: re.Match,
        file: TextIOWrapper,
        trace_id_computer: TraceIdComputer | None = None,
    ) -> Self:
        """
        Parse the leak record from the IO.

        :param header_match: The header match.
        :param file: The file to parse.
        :param trace_id_computer: The trace id computer.
        :return: The leak record.
        """
        bytes, blocks, kind = (
            cls._to_int(header_match.group(1)),
            cls._to_int(header_match.group(2)),
            cls._kind_from_str(header_match.group(3))
        )

        top_norm: str | None = None
        frames: list[str] = []

        while True:
            pos = file.tell()
            fr_raw = file.readline()
            if not fr_raw:
                break
            fr_raw = fr_raw.rstrip()

            fr = _text.strip_pid_prefix(fr_raw).lstrip()
            if not fr:
                break

            if fr.startswith("at ") or fr.startswith("by "):
                norm = cls._normalize_frame(fr)
                if top_norm is None:
                    top_norm = norm
                frames.append(norm)
                continue

            # We consumed a non-frame line (often next record header); rewind so the outer loop can process it.
            file.seek(pos)
            break

        if top_norm is None:
            top_norm = "noframe"

        computer = trace_id_computer or TraceIdComputer()
        selected = computer.select_frames(frames)
        top_frame = selected[0] if selected else top_norm
        trace_id = computer.compute(kind=kind, frames=frames)

        return cls(kind=kind, bytes=bytes, blocks=blocks, top_frame=top_frame, trace_id=trace_id)

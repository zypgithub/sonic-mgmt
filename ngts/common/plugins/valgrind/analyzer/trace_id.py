from __future__ import annotations

from typing import Sequence
import dataclasses
import logging
import hashlib

from .enums import TraceIdStrategy, LeakKind

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class TraceIdComputer:
    """Compute trace-id from a Valgrind leak stack block.

    Notes:
    - We prefer `by` frames (callers) over the first `at` frame (often malloc/realloc noise).
    - Output is a short hex digest to keep ignore files compact.
    """

    strategy: TraceIdStrategy = TraceIdStrategy.BY3
    digest_len: int = 16

    def compute(self, *, kind: LeakKind, frames: Sequence[str]) -> str:
        """ Compute the trace-id from the leak stack block. """
        selected = self.select_frames(frames)
        if not selected:
            selected = ("noframe",)
        material = f"{kind.name}|{'|'.join(selected)}"
        return hashlib.sha1(material.encode("utf-8")).hexdigest()[: self.digest_len]

    def select_frames(self, frames: Sequence[str]) -> tuple[str, ...]:
        """ Select the frames for the trace-id. """
        cleaned = [f for f in frames if not self._is_noise_frame(f)]
        if not cleaned:
            return ()

        if self.strategy is TraceIdStrategy.FULL_STACK:
            return tuple(cleaned)

        by_frames = [f for f in cleaned if f.startswith("by ")]
        if self.strategy is TraceIdStrategy.BY1:
            return tuple(by_frames[:1] or cleaned[:1])
        # default: BY3
        return tuple(by_frames[:3] or cleaned[:3])

    @staticmethod
    def _is_noise_frame(frame: str) -> bool:
        ''' Check if the frame is noise. '''
        f = frame.lower()
        if "vgpreload_memcheck" in f or "vgpreload_core" in f:
            return True
        # The first frame is often "at malloc/realloc/calloc/free ..." which isn't useful for stable ids.
        if f.startswith("at ") and any(
            tok in f for tok in (" malloc", " realloc", " calloc", " free", "operator new", "operator delete")
        ):
            return True
        return False

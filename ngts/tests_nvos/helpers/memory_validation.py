from dataclasses import dataclass
from typing import Protocol, Tuple

from ngts.nvos_constants.constants_nvos import SystemConsts


UTILIZATION_EPSILON = 1e-6


@dataclass(frozen=True)
class MemoryStats:
    """
    Immutable representation of memory statistics.

    Expected keys in the source JSON:
      - total, free, used, utilization
      - optionally: buffer, cache
    """

    total: int
    free: int
    used: int
    utilization: float
    buffer: int = 0
    cache: int = 0

    def __post_init__(self) -> None:
        """
        Normalize incoming JSON values (which may be strings) to numeric types.
        """
        object.__setattr__(self, "total", int(self.total))
        object.__setattr__(self, "free", int(self.free))
        object.__setattr__(self, "used", int(self.used))
        object.__setattr__(self, "buffer", int(self.buffer))
        object.__setattr__(self, "cache", int(self.cache))
        object.__setattr__(self, "utilization", float(self.utilization))

    def validate_basic_ranges(self, name: str) -> None:
        """Validate that basic numeric ranges are sane."""
        assert self.total >= 0, f"{name}: total must be non-negative, got {self.total}"
        assert 0 <= self.free <= self.total, f"{name}: free out of range ({self.free} / {self.total})"
        assert 0 <= self.used <= self.total, f"{name}: used out of range ({self.used} / {self.total})"

    def validate_total_consistency(self, name: str) -> None:
        """Validate that total == free + used."""
        assert self.total == self.free + self.used, (
            f"{name}: total ({self.total}) != free + used ({self.free + self.used})"
        )

    def calculated_utilization(self) -> float:
        """Return utilization percentage based on used/total."""
        return 0.0 if self.total == 0 else (self.used / self.total) * 100.0

    def validate_utilization(self, name: str) -> None:
        """Validate that reported utilization matches the calculated value."""
        calc = self.calculated_utilization()
        assert abs(self.utilization - calc) < UTILIZATION_EPSILON, (
            f"{name}: utilization mismatch: reported={self.utilization} vs calculated={calc}"
        )

    def validate_all(self, name: str) -> None:
        """Run all internal consistency checks."""
        self.validate_basic_ranges(name)
        self.validate_total_consistency(name)
        self.validate_utilization(name)


class BaseMemoryValidator(Protocol):
    """Strategy interface for memory validation per device type."""

    def validate(self, physical: MemoryStats, swap: MemoryStats) -> None:
        ...


class EthMemoryValidator:
    """Validation rules for Ethernet devices."""

    def validate(self, physical: MemoryStats, swap: MemoryStats) -> None:
        # Physical memory checks
        assert physical.total > 0, "Physical total must be > 0"
        physical.validate_basic_ranges("Physical")

        assert 0 <= physical.buffer <= physical.total, "Physical buffer out of range"
        assert 0 <= physical.cache <= physical.total, "Physical cache out of range"

        # Swap memory checks
        swap.validate_basic_ranges("Swap")
        swap.validate_total_consistency("Swap")


class IBMemoryValidator:
    """Validation rules for IB devices."""

    def validate(self, physical: MemoryStats, swap: MemoryStats) -> None:
        assert physical.total > 0, "Physical total must be > 0"
        physical.validate_total_consistency("Physical")


class NoOpMemoryValidator:
    """Fallback validator for unexpected device types (intentionally does nothing)."""

    def validate(self, physical: MemoryStats, swap: MemoryStats) -> None:
        return


class MemoryValidatorFactory:
    """Factory that returns the appropriate validator based on device type."""

    @staticmethod
    def get_validator(devices) -> BaseMemoryValidator:
        dut = devices.dut
        if hasattr(dut, "is_eth") and dut.is_eth():
            return EthMemoryValidator()
        if hasattr(dut, "is_ib") and dut.is_ib():
            return IBMemoryValidator()
        return NoOpMemoryValidator()


def build_memory_stats(output: dict) -> Tuple[MemoryStats, MemoryStats]:
    """
    Build MemoryStats instances from `nv show system memory` JSON output.

    The output is expected to contain at least:
      - SystemConsts.MEMORY_PHYSICAL_KEY
      - SystemConsts.MEMORY_SWAP_KEY
    """
    physical = MemoryStats(**output[SystemConsts.MEMORY_PHYSICAL_KEY])
    swap = MemoryStats(**output[SystemConsts.MEMORY_SWAP_KEY])
    return physical, swap

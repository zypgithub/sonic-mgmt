from __future__ import annotations

from typing import Self
import enum


class _BaseStrEnum(enum.IntEnum):
    """ Base string enum. """

    @property
    def key(self) -> str:
        """ Get the key. """
        return self.name.lower().replace('_', '-')

    def __str__(self) -> str:
        """ Get the string representation. """
        return self.key

    @classmethod
    def keys(cls) -> list[str]:
        """ Get the keys. """
        return [member.key for member in cls]

    @classmethod
    def from_value(cls, value: str) -> Self:
        """
        Convert CLI-style strings (e.g. "sub-service", "full-stack") into enum members.

        :param value: The value to convert.
        :return: The enum member.
        """
        if isinstance(value, cls):
            return value
        value_ = str(value).upper().replace('-', '_')
        try:
            return cls[value_]
        except KeyError as exc:
            raise ValueError(f"Unknown {cls.__name__}: {value!r}") from exc


class LeakKind(_BaseStrEnum):
    """ Leak kind enum. """

    DEFINITE = enum.auto()
    INDIRECT = enum.auto()
    POSSIBLE = enum.auto()
    STILL = enum.auto()


class BugHandlerScope(_BaseStrEnum):
    """  Bug handler scope enum. """

    FILE = enum.auto()
    SERVICE = enum.auto()
    SUB_SERVICE = enum.auto()
    TEST = enum.auto()


class TraceIdStrategy(_BaseStrEnum):
    """ Trace id strategy enum. """

    BY1 = enum.auto()
    BY3 = enum.auto()
    FULL_STACK = enum.auto()

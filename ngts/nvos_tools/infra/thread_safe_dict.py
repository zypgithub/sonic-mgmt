import contextlib
import contextvars
from collections.abc import Generator, Iterator, MutableMapping
from typing import Any


class ThreadSafeDict(MutableMapping):
    """A dict whose contents are isolated per execution context (thread / asyncio task).

    Backed by ``contextvars.ContextVar`` — each context's reads/writes go to its own dict
    bound via ``fresh_context()``. Outside of a fresh-context block, reads behave as if
    the dict is empty and writes raise ``LookupError``. Inside, instances act like a
    plain ``dict``.

    Use ``fresh_context()`` to start a new fresh dict for the duration of a ``with``-block;
    nested fresh-contexts are supported and the previous binding is restored on exit.
    """

    def __init__(self) -> None:
        self._var: contextvars.ContextVar[dict] = contextvars.ContextVar(
            f'{type(self).__name__}_{id(self)}')

    def __getitem__(self, key: Any) -> Any:
        try:
            data = self._var.get()
        except LookupError as e:
            raise KeyError(key) from e
        return data[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        self._var.get()[key] = value

    def __delitem__(self, key: Any) -> None:
        try:
            data = self._var.get()
        except LookupError as e:
            raise KeyError(key) from e
        del data[key]

    def __iter__(self) -> Iterator:
        try:
            return iter(self._var.get())
        except LookupError:
            return iter(())

    def __len__(self) -> int:
        try:
            return len(self._var.get())
        except LookupError:
            return 0

    def __contains__(self, key: Any) -> bool:
        try:
            return key in self._var.get()
        except LookupError:
            return False

    def __repr__(self) -> str:
        try:
            return f'{type(self).__name__}({self._var.get()!r})'
        except LookupError:
            return f'{type(self).__name__}(<no scope>)'

    @contextlib.contextmanager
    def fresh_context(self) -> Generator[dict, None, None]:
        """Bind a fresh empty dict for the duration of the ``with``-block.

        Yields the new dict so callers can read/write through this instance (or directly
        through the yielded dict) and inspect it after producers have populated it. On
        exit the previous binding is restored, so nested fresh-contexts don't leak.
        """
        new_dict: dict = {}
        token = self._var.set(new_dict)
        try:
            yield new_dict
        finally:
            self._var.reset(token)

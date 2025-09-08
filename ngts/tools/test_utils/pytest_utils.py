from typing import Iterator, Optional, Type, Tuple, Union
import contextlib
import logging
import pytest

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def temporary_xfail_mark(
    request: pytest.FixtureRequest,
    /, *,
    condition: bool = True,
    reason: str = '',
    raises: Optional[Union[Type[BaseException], Tuple[Type[BaseException], ...]]] = None,
    run: bool = True,
    strict: bool = False,

) -> Iterator[None]:
    """Temporarily add an xfail mark for the duration of a context.

    - Adds the xfail mark at context entry when condition is True.
    - On exception: keeps the mark so the failure is reported as XFAIL.
    - On success: removes the mark to avoid XPASS.
    - When condition is False, acts as a no-op contextmanager.

    Args:
        request: pytest.FixtureRequest - the request object

    Keyword Args:
        condition: Union[str | bool] - the condition for the xfail mark
        reason: str - the reason for the xfail mark
        raises: Union[Type[BaseException], Tuple[Type[BaseException], ...]] - the exception to raise
        run: bool - whether to run the test
        strict: bool - the strictness of the xfail mark
    """

    if not condition:
        yield
        return

    logger.debug(f"Try to add xfail mark to {request.node.name}")
    if raises is None:
        marker = pytest.mark.xfail(condition=condition, reason=reason, run=run, strict=strict)
    else:
        marker = pytest.mark.xfail(condition=condition, reason=reason, run=run, strict=strict, raises=raises)

    request.node.add_marker(marker)
    logger.debug(f"Added xfail mark to {request.node.name}")

    yield

    logger.debug(f"Try to remove xfail mark from {request.node.name}")
    item = request.node
    for m in list(item.iter_markers(name=marker.name)):
        try:
            item.own_markers.remove(m)
        except ValueError:
            pass

    # drop the keyword entry
    item.keywords.pop(marker.name, None)
    logger.debug(f"Removed xfail mark from {request.node.name}")

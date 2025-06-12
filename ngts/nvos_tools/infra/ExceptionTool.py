import logging
import traceback
from typing import List

logger = logging.getLogger()


def format_exception(exception: BaseException) -> str:
    return f"{exception.__class__.__name__}: {exception}"


def format_traceback() -> str:
    """
    Must be called inside an `except` clause. Returns a string containing the exception message and stack-trace, just
    like the message printed by Python when an exception occurs.
    """
    return traceback.format_exc()


def format_stack() -> List[str]:
    """Returns a list of strings describing the current stack."""
    return traceback.format_stack()


def log_exception(exception: BaseException, prelude='', level=logging.ERROR):
    msg = format_exception(exception)
    if prelude:
        msg = prelude + ': ' + msg
    logging.log(level, msg)


def log_traceback(level=logging.ERROR):
    """Must be called inside an `except` clause. Prints the output of format_traceback to the log."""
    logging.log(level, format_traceback())

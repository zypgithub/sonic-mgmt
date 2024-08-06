import inspect
import logging
import os
from contextlib import contextmanager

import allure
from exceptiongroup import ExceptionGroup

logger = logging.getLogger()

orig_allure = allure


_allure_step_stack = []  # push/pop items when enter/exit allure step. each item is a list of failed sub-steps.


def print_step_log_info(log_info_msg: str, lineno, filename):
    """Prints log message with a 'fake' context (file-name and line-number)."""
    formatters = {handler: handler.formatter for handler in logger.handlers}
    for handler, formatter in formatters.items():
        orig_logger_format: str = formatter._fmt
        new_logger_format = orig_logger_format.replace('%(filename)s', filename).replace('%(lineno)s', str(lineno))
        new_logger_formatter = logging.Formatter(new_logger_format)
        new_logger_formatter.datefmt = formatter.datefmt
        handler.setFormatter(new_logger_formatter)

    logging.info(log_info_msg)
    for handler, formatter in formatters.items():
        handler.setFormatter(formatter)


@contextmanager
def step(step_msg):
    """
    @summary:
        Context manager that wraps allure step context and a log with the same message
    @param step_msg: The desired step message
    """
    with _step(step_msg, independent=False):
        yield


@contextmanager
def independent_step(step_msg):
    """
    @summary:
        Like `step`, but if it fails then following steps will still run, and when the parent step finishes then an
        ExceptionGroup will be raised with all failures.
    @param step_msg: The desired step message
    """
    if not _allure_step_stack:
        raise Exception("Error calling allure.independent_step: an independent step must be placed inside a normal "
                        "allure.step, because we test for independent-step failure only when the parent step finishes")
    with _step(step_msg, independent=True):
        yield


@contextmanager
def _step(step_msg, independent=False):
    caller_frame = inspect.currentframe().f_back.f_back.f_back.f_back
    caller_file = inspect.getframeinfo(caller_frame).filename
    lineno = caller_frame.f_lineno
    filename = os.path.basename(caller_file)

    with allure.step(step_msg) as allure_step_context:
        print_step_log_info(f'Step start: {step_msg}', lineno, filename)
        error = None
        _allure_step_stack.append([])
        try:
            yield allure_step_context
        except Exception as e:
            error = e
            _allure_step_stack.pop(-1)
            if independent:
                _allure_step_stack[-1].append(e)
            else:
                raise
        else:
            errors = _allure_step_stack.pop(-1)
            if errors:
                error = ExceptionGroup(f"{len(errors)} sub-steps failed", errors)
                raise error
        finally:
            print_step_log_info(f'Step end [{"FAIL" if error else "SUCCESS"}]: {step_msg}', lineno, filename)


def attach(title: str, msg: str, attachment_type=orig_allure.attachment_type.TEXT):
    orig_allure.attach(msg, title, attachment_type)

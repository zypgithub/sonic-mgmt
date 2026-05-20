import contextlib
import enum
import logging
import time
from collections.abc import Callable, Generator
from typing import Any

import pytest

from ngts.nvos_constants.constants_nvos import OperationTimeConsts
from ngts.nvos_tools.infra.ResultObj import ResultObj, IssueType
from ngts.nvos_tools.infra.thread_safe_dict import ThreadSafeDict

logger = logging.getLogger(__name__)


class SubDuration(enum.StrEnum):
    """Canonical names for sub-duration buckets recorded via OperationTime.record_sub_duration().

    TOTAL is synthesized by save_duration; producers should use OPERATION / REBOOT (or add new
    members here rather than passing raw strings).
    """
    OPERATION = enum.auto()
    REBOOT = enum.auto()
    TOTAL = enum.auto()


# Side channel used to carry split (operation/reboot) durations through call chains where
# intermediate layers (SendCommandTool, nvue_action's verify_result) discard the producing
# ResultObj. Producers (e.g. DutUtilsTool.reload, OpenAPI action_deprecated) call
# OperationTime.record_sub_duration(...) and consumers wrap their measurement in
# OperationTime.capture_sub_durations(). Backed by ThreadSafeDict so concurrent operations
# (threads/asyncio tasks) don't collide.
_SUB_DURATIONS: ThreadSafeDict = ThreadSafeDict()


class OperationTime:
    """Time NVOS operations and emit rows into ``pytest.operation_list``.

    Basic:

    >>> OperationTime.save_duration('nv set hostname', params, test_name, func, *args)

    Split into named parts (producers deep in the stack call ``record_sub_duration``;
    only takes effect when wrapped in ``capture_sub_durations``):

    >>> with OperationTime.capture_sub_durations():
    ...     OperationTime.save_duration('reboot flow', '', test_name, DutUtilsTool.reload, ...)
    # rows: 'reboot flow (operation)', 'reboot flow (reboot)', 'reboot flow' (total)
    """

    @staticmethod
    @contextlib.contextmanager
    def capture_sub_durations() -> Generator[dict, None, None]:
        """Yields a dict that producers downstream populate via record_sub_duration().

        Each invocation binds a fresh dict on the side-channel ThreadSafeDict for this
        execution context; record_sub_duration calls inside the with-block land in that
        dict. Nested captures are supported (each fresh context shadows the parent's
        binding and the parent is restored on exit).
        """
        with _SUB_DURATIONS.fresh_context() as cmd_type_to_duration:  # noqa
            yield cmd_type_to_duration

    @staticmethod
    def record_sub_duration(name: str | SubDuration, value: float) -> None:
        """Record a sub-duration into the active capture, if any. No-op otherwise."""
        try:
            _SUB_DURATIONS[name] = value
        except LookupError:
            # Producers may run outside a capture_sub_durations() context (e.g. when their
            # caller doesn't care about split rows); silently drop the value rather than
            # leaking it into the next capture scope.
            pass

    @staticmethod
    def save_duration(operation: str, oper_params: str, test_name: str,
                      func: Callable[..., ResultObj], *args: Any, **kargs: Any) -> tuple[ResultObj, float]:
        """
        save the duration of the command and add it to pytest.operation_list
        just if the operation succeed and we have test_name in the duration_time_dict
        :param operation: string that describe the operation
        :param oper_params: string that describe the parameter the operation use
        :param test_name: name of the test that call the operation
        :param func: the operation we want to measure, should return ResultObj
        :param args: args for func

        If the wrapped call produces split sub-durations (either by leaving a dict on
        result_obj.duration, or via the capture_sub_durations() context), this method
        records one row per sub-duration in pytest.operation_list and exposes the full
        breakdown on result_obj.duration as a dict (with a 'total' key added).
        Backwards compatible: when no sub-durations are present, behavior is identical
        to the previous single-float implementation.
        """
        start_time = time.perf_counter()
        result_obj = func(*args, **kargs)
        duration = time.perf_counter() - start_time

        # Sub-durations may arrive from two sources: the capture_sub_durations() side
        # channel (producers call record_sub_duration), or directly via result_obj.duration
        # set by the wrapped function. Merge both so neither is silently dropped.
        existing_dict: dict | None = result_obj.duration if isinstance(result_obj.duration, dict) else None
        captured: dict | None = dict(_SUB_DURATIONS) if _SUB_DURATIONS else None
        combined = {**(captured or {}), **(existing_dict or {})} if (captured or existing_dict) else None
        merged = {**combined, SubDuration.TOTAL: duration} if combined else None

        # Only emit DB rows on success and when caller supplied a test name; failures
        # and unattributed calls still flow through to set result_obj.duration below.
        if result_obj.result and test_name:
            logger.info(f"{operation} took {duration} seconds")
            if merged:
                # Row-naming convention: 'total' keeps the bare operation name,
                # sub-parts get '<operation> (<sub_name>)'.
                for sub_name, sub_value in merged.items():
                    pytest.operation_list.append(OperationTime.create_duration_time_dict(
                        OperationTime._row_name(operation, sub_name), oper_params, sub_value, test_name))
            else:
                pytest.operation_list.append(
                    OperationTime.create_duration_time_dict(operation, oper_params, duration, test_name))

        result_obj.duration = merged if merged else duration
        return result_obj, duration

    @staticmethod
    def _row_name(operation: str, sub_name: str | SubDuration) -> str:
        """Row-naming convention: TOTAL keeps the bare operation name, sub-parts get '<operation> (<sub_name>)'."""
        return operation if sub_name == SubDuration.TOTAL else f'{operation} ({sub_name})'

    @staticmethod
    def save_manual_operation_duration_to_db(operation: str, duration: float | dict, test_name: str) -> None:
        """Append one or more rows to pytest.operation_list.

        If `duration` is a dict, expands into one row per key using the same row-naming
        convention as save_duration. Otherwise records a single row.
        """
        if isinstance(duration, dict):
            for sub_name, sub_value in duration.items():
                pytest.operation_list.append(OperationTime.create_duration_time_dict(
                    OperationTime._row_name(operation, sub_name), '', sub_value, test_name))
        else:
            pytest.operation_list.append(
                OperationTime.create_duration_time_dict(operation, '', duration, test_name))

    @staticmethod
    def create_duration_time_dict(operation='', params='', duration='', test_name=''):
        duration_time_dict = {OperationTimeConsts.OPERATION_COL: operation, OperationTimeConsts.PARAMS_COL: params,
                              OperationTimeConsts.DURATION_COL: duration, OperationTimeConsts.TEST_NAME_COL: test_name}
        return duration_time_dict

    @staticmethod
    def update_duration_time_dict(duration_time_dict, operation='', command='', duration='', test_name='', override=False):
        # if override == false , will override just if empty.
        if duration_time_dict[OperationTimeConsts.OPERATION_COL] == '' or override:
            duration_time_dict[OperationTimeConsts.OPERATION_COL] = operation
        if duration_time_dict[OperationTimeConsts.PARAMS_COL] == '' or override:
            duration_time_dict[OperationTimeConsts.PARAMS_COL] = command
        if duration_time_dict[OperationTimeConsts.DURATION_COL] == '' or override:
            duration_time_dict[OperationTimeConsts.DURATION_COL] = duration
        if duration_time_dict[OperationTimeConsts.TEST_NAME_COL] == '' or override:
            duration_time_dict[OperationTimeConsts.TEST_NAME_COL] = test_name

    @staticmethod
    def verify_operation_time(duration, operation='', devices=None, threshold=None) -> ResultObj:
        """
        Verify that operation completed within expected threshold.

        Args:
            duration: The actual duration of the operation in seconds.
            operation: Name of the operation (for logging/error messages).
            devices: Devices object to look up threshold from expected_operation_durations.
            threshold: Optional explicit threshold (overrides devices lookup if provided).

        Returns:
            ResultObj indicating success or failure with error message.
        """
        ret_val = ResultObj(True)
        # Get threshold from devices if not explicitly provided
        if threshold is None and devices is not None:
            threshold = devices.dut.expected_operation_durations.get(operation)
        if threshold is not None and threshold < duration:
            err_msg = f"{operation} took {duration} seconds - more time than threshold of {threshold} seconds"
            logger.error(err_msg)
            ret_val = ResultObj(False, err_msg, issue_type=IssueType.PossibleBug)
        return ret_val

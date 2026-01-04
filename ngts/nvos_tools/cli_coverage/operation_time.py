from typing import Tuple
import logging
import time

import pytest

from ngts.nvos_constants.constants_nvos import OperationTimeConsts
from ngts.nvos_tools.infra.ResultObj import ResultObj, IssueType

logger = logging.getLogger()


class OperationTime:

    @staticmethod
    def save_duration(operation, oper_params, test_name, func, *args, **kargs) -> Tuple[ResultObj, float]:
        """
        save the duration of the command and add it to pytest.operation_list
        just if the operation succeed and we have test_name in the duration_time_dict
        :param operation: string that describe the operation
        :param oper_params: string that describe the parameter the operation use
        :param test_name: name of the test that call the operation
        :param func: the operation we want to measure, should return ResultObj
        :param args: args for func
        """
        start_time = time.perf_counter()
        result_obj = func(*args, **kargs)
        duration = 0
        if result_obj.result and test_name:
            end_time = time.perf_counter()
            duration = end_time - start_time
            logger.info("{operation} took {dur} seconds".format(operation=operation, dur=duration))
            duration_time_dict = OperationTime.create_duration_time_dict(operation, oper_params, duration, test_name)
            pytest.operation_list.append(duration_time_dict)
            logger.info(f"current state of pytest.operation_list: {pytest.operation_list}")

        result_obj.duration = duration
        return result_obj, duration

    @staticmethod
    def save_manual_operation_duration_to_db(operation, duration, test_name):
        duration_time_dict = OperationTime.create_duration_time_dict(operation, '', duration, test_name)
        pytest.operation_list.append(duration_time_dict)
        logger.info(f"current state of pytest.operation_list: {pytest.operation_list}")

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

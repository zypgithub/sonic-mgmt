"""
If a function returns a ResultObj and the verify_result() method is never called for it, a test might pass where it
should have failed. To avoid this, the verify_result_objects teardown fixture asserts that any ResultObj ever created
has result==True or has explicitly called verify_result (or get_returned_value, or ignore_result) at least once.
Theoretically the ignore_result method should never be used - use verify_result (with should_succeed set to True or
False according to the use case).
"""
import itertools
import logging
import re
import sys
import traceback


class IssueType:
    Unknown = 0
    TestIssue = 1
    PossibleBug = 2

    exception_msg = {Unknown: "", TestIssue: "*** POSSIBLE TEST ISSUE ***\n", PossibleBug: "*** POSSIBLE BUG ***\n"}


class ResultObj:
    _result = False
    _info = ""
    _returned_value = None
    issue_type = IssueType.Unknown
    _duration = None
    _instances = set()

    def __init__(self, result, info="", returned_value=None, issue_type=IssueType.Unknown, duration=None):
        self.update(result, info, returned_value, issue_type, duration)
        self._add_instance(self)

    def update(self, result, info="", returned_value=None, issue_type=IssueType.Unknown, duration=None):
        self._result = result
        self._info = info
        self._returned_value = returned_value
        self.issue_type = issue_type
        self._duration = duration
        self._update_traceback()

    @property
    def result(self):
        return self._result

    @result.setter
    def result(self, value):
        self._result = value
        self._update_traceback()

    @property
    def info(self):
        return self._info

    @info.setter
    def info(self, value):
        self._info = value
        self._update_traceback()

    @property
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, value):
        if value is None:
            raise ValueError("Duration cannot be None")  # Prevent setting None
        if value < 0:
            raise ValueError("Duration cannot be negative")  # Prevent invalid values
        self._duration = value
        self._update_traceback()

    @property
    def returned_value(self):
        return self._returned_value

    @returned_value.setter
    def returned_value(self, value):
        self._returned_value = value
        self._update_traceback()

    def verify_result(self, should_succeed=True, expected_value='', expected_duration=None):
        """
        Assert an error if result is False, otherwise returns returned_value
        :return: If 'result' is True, returns the 'returned_value'
        """
        self.ignore_result()
        logging.info("\n   Result: {result}\n   should_succeed: {should_succeed}\n   info: {info}\n".format(
                     result=bool(self.result),
                     should_succeed=bool(should_succeed),
                     info=self.info))
        if should_succeed != self.result:
            raise AssertionError(self._get_fail_message())

        output: str = self.returned_value if should_succeed else self.info
        if expected_value:
            if isinstance(expected_value, list):
                assert any(value in output for value in expected_value), (
                    f"None of the expected values {repr(expected_value)} matched the output: {output}")
            else:
                assert expected_value in output, (
                    f"Expected {repr(expected_value)} but output is: {output}")

        if should_succeed and expected_duration:
            self.verify_duration(expected_duration)

        return output

    def verify_duration(self, expected_duration):
        """Raises an exception if duration is missing or exceeds the expected threshold"""
        assert self._duration, "Duration is missing. Please set a valid duration before verifying."

        assert expected_duration > self._duration, f"Operation took {self._duration} seconds - more than the threshold of {expected_duration} seconds."

    def get_returned_value(self, should_succeed=True):
        return self.verify_result(should_succeed)

    def get_info(self, should_succeed=True):
        self.verify_result(should_succeed)
        return self.info

    def ignore_result(self) -> 'ResultObj':
        """Call this method if we don't care whether the operation succeeded or failed."""
        self._discard_instance(self)
        return self

    def __bool__(self):
        return bool(self.result)

    def __str__(self):
        info = self.info
        returned_value = self.returned_value
        return f'{self.__class__.__name__}({self.result}, {info=}, {returned_value=})'

    def update_traceback(self):
        """
        Updates self.traceback to reflect the current stack-trace.
        If called inside an `except` clause, it instead contains the exception's traceback.
        """
        if sys.exc_info()[0]:
            self.traceback = traceback.format_exc()
        else:
            self._update_traceback()

    def _update_traceback(self):
        self.traceback = traceback.format_stack()

    @classmethod
    def _discard_instance(cls, instance):
        cls._instances.discard(instance)  # `discard` does not raise an error if the element already doesn't exist

    @classmethod
    def _add_instance(cls, instance):
        cls._instances.add(instance)

    @classmethod
    def _pop_all_instances(cls):
        output = set(cls._instances)
        cls._instances.clear()
        return output

    def _get_fail_message(self):
        tb = self.traceback
        try:  # try to make the stack more readable by removing excess, but if it fails we just print the entire stack
            # Discard the lowest stack-entries, which are just ResultObj internals
            tb = list(itertools.takewhile(lambda s: __file__ not in s, tb))
            # Discard the top entries which are just pytest wrappers
            top = ['/test_' in x for x in tb].index(True)
            tb = tb[top:] or tb
        except BaseException:
            pass

        msg = IssueType.exception_msg[self.issue_type]
        msg += self.info or ("The operation succeeded while it is expected to fail" if self.result
                             else "The operation failed")
        msg += '\nResult traceback:\n' + ''.join(tb)
        return msg

    def apply_occurred(self) -> bool:
        apply_occurred = bool(self and self.result and isinstance(self.returned_value, str) and
                              re.findall('verif.*applied', self.returned_value))
        # logging.warning(
        #     f'DEBUG:\nresult: {self.result}\ninfo: {self.info}\nreturned value: {self.returned_value}\n'
        #     f'issue type: {self.issue_type}\n***should sleep***: {apply_occurred}')
        return apply_occurred

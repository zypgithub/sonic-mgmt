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
    _instances = set()

    def __init__(self, result, info="", returned_value=None, issue_type=IssueType.Unknown):
        self.update(result, info, returned_value, issue_type)
        self._add_instance(self)

    def update(self, result, info="", returned_value=None, issue_type=IssueType.Unknown):
        self._result = result
        self._info = info
        self._returned_value = returned_value
        self.issue_type = issue_type
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
    def returned_value(self):
        return self._returned_value

    @returned_value.setter
    def returned_value(self, value):
        self._returned_value = value
        self._update_traceback()

    def verify_result(self, should_succeed=True):
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

        return self.returned_value if self.result else self.info

    def get_returned_value(self, should_succeed=True):
        return self.verify_result(should_succeed)

    def ignore_result(self):
        """Call this method if we don't care whether the operation succeeded or failed."""
        self._discard_instance(self)

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

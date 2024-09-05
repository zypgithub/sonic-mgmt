import inspect
import os
import sys

from ngts.tools.test_utils.allure_utils import print_step_log_info as log

CLIENT_VERIFICATION_DIR = os.path.dirname(os.path.abspath(__file__))


def printtt(msg, prefix=''):
    if 'pytest' in sys.modules:
        caller_frame = inspect.currentframe().f_back.f_back
        caller_file = inspect.getframeinfo(caller_frame).filename
        lineno = caller_frame.f_lineno
        filename = os.path.basename(caller_file)

        prefix = f'[{prefix}] ' if prefix else ''
        msg = f'{prefix}{msg}'
        log(msg, lineno, filename)
    else:
        print(msg)

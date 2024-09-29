import logging
from typing import Tuple

import pexpect

from infra.tools.general_constants.constants import DefaultConnectionValues


class PexpectTool:
    TIMEOUT = -1

    def __init__(self, spawn_cmd: str = '', default_expect_err_msg: str = 'Expect failed'):
        self.child: pexpect.spawn = None
        self.expect_error_msg = default_expect_err_msg
        if spawn_cmd:
            self.spawn(spawn_cmd)
        self.last_output = ''

    def __del__(self):
        self.child.close()

    def spawn(self, cmd):
        logging.info(f'Spawn: {cmd}')
        self.child = pexpect.spawn(cmd)
        self.child.delaybeforesend = DefaultConnectionValues.PEXPECT_DELAYBEFORESEND

    def close(self):
        if self.child is not None:
            logging.info('close pexpect spawned process')
            self.child.close()
            self.child = None

    def expect(self, expect_msg, error_message='', raise_exception_for_timeout: bool = True, timeout=None) -> int:
        err_msg = error_message if error_message else self.expect_error_msg
        if isinstance(expect_msg, list):
            logging.info(f'Expect: {expect_msg}')
            expect_list = expect_msg + [pexpect.EOF]
        else:
            logging.info(f'Expect: "{expect_msg}"')
            expect_list = [expect_msg, pexpect.EOF]

        try:
            res_index = self.child.expect(expect_list) if timeout is None else self.child.expect(expect_list, timeout)
            decoded_before = self.child.before.decode('utf-8', errors='replace') if hasattr(self.child.before, 'decode') else ''
            decoded_after = self.child.after.decode('utf-8', errors='replace') if hasattr(self.child.after, 'decode') else ''
            self.last_output = decoded_before + decoded_after
            logging.info(f'Output:\n{self.last_output}')
            assert res_index != len(expect_list) - 1, err_msg
        except pexpect.exceptions.TIMEOUT as timeout_exception:
            logging.info(f'Got pexpect TIMEOUT exception.\n{err_msg}')
            if raise_exception_for_timeout:
                raise timeout_exception
            else:
                return PexpectTool.TIMEOUT

        return res_index

    def expect_and_get_output(self, expect_msg, error_message='', raise_exception_for_timeout: bool = True, timeout=None) -> Tuple[int, str]:
        res_index = self.expect(expect_msg, error_message, raise_exception_for_timeout, timeout)
        if res_index == PexpectTool.TIMEOUT:
            return res_index, 'TIMEOUT'
        return res_index, self.last_output

    def send(self, send_str):
        print_to_log = "\\r" if send_str == "\r" else send_str
        logging.info(f'Send: "{print_to_log}"')
        self.child.send(send_str)

    def sendline(self, send_str):
        print_to_log = "\\r" if send_str == "\r" else send_str
        logging.info(f'Send line: "{print_to_log}"')
        self.child.sendline(send_str)

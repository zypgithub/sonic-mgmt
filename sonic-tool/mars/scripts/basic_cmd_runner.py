#!/usr/bin/env python

# Built-in modules
import sys
import os
import re

from reg2_wrapper.common.error_code import ErrorCode
from reg2_wrapper.utils.parser.cmd_argument import RunningStage
from reg2_wrapper.test_wrapper.standalone_wrapper import StandaloneWrapper

from sig_term_handler.handler_mixin import TermHandlerMixin
from lib.utils import get_allure_project_id
import time

ErrorCode.NO_COLLECTION = 5


class RunPython(TermHandlerMixin, StandaloneWrapper):

    def configure_parser(self):
        super(RunPython, self).configure_parser()

         # Client arguments
        self.add_cmd_argument("--test_script", required=True, dest="test_script",
                              help="Path to the test script, example: /root/mars/workspace/sonic-mgmt/tests/")

    def run_commands(self):
        rc = ErrorCode.SUCCESS

        # Convert the test script path to module format
        if self.test_script.startswith('/'):
            # Remove the base path and convert remaining path to module format
            base_path = '/root/mars/workspace/sonic-mgmt'
            if self.test_script.startswith(base_path):
                # Remove base path and .py extension, convert slashes to dots
                module_path = self.test_script[len(base_path):].lstrip('/').replace('/', '.')
                if module_path.endswith('.py'):
                    module_path = module_path[:-3]
                cmd = f'cd {base_path} && python3 -m {module_path}'
            else:
                # If path doesn't start with base_path, run it directly
                cmd = f'python3 {self.test_script}'
        else:
            # For relative paths, use module format
            cmd_template = 'python3 -m {}'
            cmd = cmd_template.format(self.test_script)

        for epoint in self.EPoints:
            dic_args = self._get_dic_args_by_running_stage(RunningStage.RUN)
            dic_args["epoint"] = epoint
            for _ in range(self.num_of_processes):
                epoint.Player.putenv("PYTHONPATH", "/devts/")
                # Change to the correct directory before running the command
                epoint.Player.run_process(f'cd /root/mars/workspace/sonic-mgmt && {cmd}', 
                                        shell=True, 
                                        disable_realtime_log=False, 
                                        delete_files=False)

        for player in self.Players:
            rc = player.wait() or rc
            player.remove_remote_test_path(player.testPath)
        if rc == ErrorCode.NO_COLLECTION:
            rc = 0  # In case no tests are collected, should not fail mars step
        return rc


if __name__ == "__main__":
    run_python = RunPython("RunPython")
    run_python.execute(sys.argv[1:])

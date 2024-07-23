import logging
import os
import signal
import subprocess
import time
from typing import Tuple, List


class CmdRunner:
    """
    This class serves as a tool to run given commands directly on the running player,
        using subprocess/Popen module
    """
    DEFAULT_TIMEOUT = 30

    def __init__(self, runner_name: str = '', default_timeout=DEFAULT_TIMEOUT, print_outputs: bool = True, kill_live_processes_on_delete: bool = True):
        self._runner_name = runner_name
        self._default_timeout = default_timeout
        self._live_processes: List[subprocess.Popen] = []
        self._kill_live_processes_on_delete = kill_live_processes_on_delete
        self._print_outputs_to_log = print_outputs

    def __del__(self):
        if self._kill_live_processes_on_delete:
            self._log('close live processes')
            for process in self._live_processes:
                self.kill_cmd_process(process)

    def run_cmd_in_process(self, cmd: str, keep_process_alive: bool = False, wait_till_done: bool = True, cmd_timeout=None) -> Tuple[str, str, subprocess.Popen]:
        """
        run a given command in a process
        @param cmd: the command to run
        @param keep_process_alive: whether to keep the process alive (and return it) or not
        @param wait_till_done: if not keep_process_alive - whether to wait till the command is finished or not
        @param cmd_timeout: if not keep_process_alive/wait_till_done - number of seconds to give to the command.
            after timeout, kill the process of command.
            if this param is not provided, use the default_timeout initialized with the object.
        @return: several options:
            - when keep_process_alive is True - return the running process
                * the process is added to internal list of the opened processes
                * eventually when (before) self object is deleted, all saved open processes are killed
            - otherwise - return output, err of the command process
        """
        self._log(f"run: {cmd}")
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid)

        if keep_process_alive:
            self._log(f"keeping process alive and returning it")
            self._live_processes.append(process)
            return '', '', process

        if wait_till_done:
            self._log(f"wait till cmd is done and get output")
            out, err = self.wait_for_cmd_process(process)
            return out, err, None

        output, err = self.kill_cmd_process(process, cmd_timeout or self._default_timeout)
        return output, err, None

    def kill_cmd_process(self, process: subprocess.Popen, delay=0) -> Tuple[str, str]:
        """
        kill a given process, after a given delay
        @param process: given process to kill
        @param delay: number of seconds to wait before killing the process
        @return: output, err of the command process
        """
        if delay and process.poll() is None:
            self._log(f'process not finished yet. wait {delay} seconds')
            time.sleep(delay)
        self._log(f'kill process and get output')
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        return self.wait_for_cmd_process(process)

    def wait_for_cmd_process(self, process: subprocess.Popen) -> Tuple[str, str]:
        """
        wait for a given process to finish
        @param process: given process to wait for
        @return: output, err of the command process
        """
        output, err = process.communicate()
        output = output.decode('utf-8')
        err = err.decode('utf-8')
        if self._print_outputs_to_log:
            self._log(f"output: {output}")
            self._log(f"err: {err}")
        return output, err

    def _log(self, message: str):
        logging.info(f"{f'[{self._runner_name}] ' if self._runner_name else ''}{message}")

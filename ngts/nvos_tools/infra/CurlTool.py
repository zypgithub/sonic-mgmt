import logging
import os
import signal
import subprocess
import time
from typing import Tuple, List

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_constants.constants_nvos import SystemConsts


class CurlTool:
    def __init__(self, server_host: str, username: str, password: str,
                 server_port: str = SystemConsts.EXTERNAL_API_PORT_DEFAULT, cacert='',
                 verify_tools_installed: bool = False):

        self.server_host = server_host
        self.server_port = server_port
        self.username = username
        self.password = password
        self.cacert = cacert

        if verify_tools_installed:
            with allure.step('verify curl installed on player'):
                self._verify_curl_installed()

        self._live_processes: List[subprocess.Popen] = []

    def request(self, username: str = '', password: str = '', skip_cert_verify: bool = True, cacert='', path: str = '', request_type='') -> Tuple[str, str]:
        out, err, _ = self._run_rest_op(request_type, skip_cert_verify, cacert, username,
                                        password, path)
        return out, err

    def _run_rest_op(self, rest_op: str, is_insecure: bool, cacert: str, username: str = '',
                     password: str = '', path: str = '') -> Tuple[
            str, str, subprocess.Popen]:
        with allure.step('compose the curl command'):
            username = username or self.username
            password = password or self.password

            if is_insecure:
                cert_flag = '-insecure'
            else:
                cacert_to_use = cacert or self.cacert
                assert cacert_to_use, 'cacert path was not specified'
                cert_flag = f'--cacert {cacert_to_use}'

            curl_cmd = (f"curl {cert_flag} --user {username}:{password} "
                        f"--request {rest_op} 'https://{self.server_host}:{self.server_port}{path}'")
        with allure.step('run curl command in process'):
            return self._run_cmd_in_process(curl_cmd)

    def _verify_curl_installed(self):
        cmd = 'curl -version'
        output = self._run_cmd_in_process(cmd)
        assert 'bash' not in output, f"curl is not installed on player.\n{cmd}\n{output}"

    def _run_cmd_in_process(self, cmd: str) -> Tuple[
            str, str, subprocess.Popen]:
        self._log(f"run: {cmd}")
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   preexec_fn=os.setsid)
        self._log(f"get output from cmd process")
        out, err = self._get_cmd_process_output(process)
        return out, err, None

    def _get_cmd_process_output(self, process: subprocess.Popen):
        output, err = process.communicate()
        output = output.decode('utf-8')
        err = err.decode('utf-8')
        self._log(f"output: {output}")
        self._log(f"err: {err}")
        return output, err

    def _log(self, msg: str):
        logging.info(f"[CurlTool] {msg}")

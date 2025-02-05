import logging
import os
import subprocess
from typing import Tuple, List

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.infra.IpTool import IpTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo


class CurlTool:
    def __init__(self, server_host: str, username: str, password: str,
                 server_port: str = SystemConsts.EXTERNAL_API_PORT_DEFAULT, cacert='',
                 verify_tools_installed: bool = False, client_cert: CertInfo = None):

        self.server_host = server_host
        self.server_port = server_port
        self.username = username
        self.password = password
        self.cacert = cacert
        self.client_cert: CertInfo = client_cert

        if verify_tools_installed:
            with allure.step('verify curl installed on player'):
                self._verify_curl_installed()

        self._live_processes: List[subprocess.Popen] = []

    def request(self, username: str = '', password: str = '', skip_cert_verify: bool = True, cacert='', path: str = '', request_type='', client_cert: CertInfo = None, resolve_dn: str = '') -> Tuple[str, str]:
        out, err, _ = self._run_rest_op(request_type, skip_cert_verify, cacert, username,
                                        password, path, client_cert, resolve_dn)
        return out, err

    def _run_rest_op(self, rest_op: str, is_insecure: bool, cacert: str, username: str = '',
                     password: str = '', path: str = '', client_cert: CertInfo = None, resolve_dn: str = '') -> Tuple[
            str, str, subprocess.Popen]:
        curl_cmd = self._compose_curl_cmd(cacert, client_cert, is_insecure, password, path, resolve_dn, rest_op,
                                          username)
        with allure.step('run curl command in process'):
            return self._run_cmd_in_process(curl_cmd)

    def _compose_curl_cmd(self, cacert, client_cert, is_insecure, password, path, resolve_dn, rest_op, username):
        with allure.step('compose the curl command'):
            username = username or self.username
            password = password or self.password
            host = f'[{self.server_host}]' if IpTool.is_address_ipv6(self.server_host) else self.server_host

            if is_insecure:
                cert_flag = '--insecure'
            else:
                cacert_to_use = cacert or self.cacert
                assert cacert_to_use, 'cacert path was not specified'
                cert_flag = f'--cacert {cacert_to_use}'
                client_cert_to_use = client_cert or self.client_cert
                if client_cert_to_use:
                    cert_flag += f' --key {client_cert_to_use.private} --cert {client_cert_to_use.public}'
                if resolve_dn:
                    cert_flag += f' --resolve {resolve_dn}:{self.server_port}:{host}'
                    host = resolve_dn

            curl_cmd = (f"curl {cert_flag} --user {username}:{password} "
                        f"--request {rest_op} 'https://{host}:{self.server_port}{path}'")
        return curl_cmd

    def graceful_restart_bmc(self):
        return self.run_redfish_command(rest_op='POST', data='{"ResetType": "GracefulRestart"}',
                                        path='/Managers/BMC_0/Actions/Manager.Reset')

    def reset_bmc_to_factory(self, username='', password=''):
        return self.run_redfish_command(rest_op='POST', data='{"ResetToDefaultsType": "ResetAll"}',
                                        path='/Managers/BMC_0/Actions/Manager.ResetToDefaults',
                                        username=username, password=password)

    def change_root_password(self, username='', password='', dut_engine=None, new_password='ABYX12#14artb'):
        return self.run_redfish_command(
            rest_op='PATCH',
            data=f'{{"Password": "{new_password}"}}',
            path='/AccountService/Accounts/root',
            username=username,
            password=password,
            dut_engine=dut_engine
        )

    def run_redfish_command(self, rest_op: str, data: str = '', username: str = '',
                            password: str = '', path: str = '', dut_engine=None):
        dut_engine: LinuxSshEngine = dut_engine or TestToolkit.engines.dut
        with allure.step('compose the curl command'):
            username = username or self.username
            password = password or self.password

        if data:
            data = f'-d \'{data}\''
        curl_cmd = f"curl -k -w '\\n' -u {username}:{password} -H 'Content-Type:application/json' -X {rest_op} {data} https://{self.server_host}/redfish/v1{path}"
        return dut_engine.run_cmd(curl_cmd)

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

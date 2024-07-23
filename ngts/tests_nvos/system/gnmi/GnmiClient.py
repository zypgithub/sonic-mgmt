import logging
import subprocess
from typing import Tuple

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.tests_nvos.system.gnmi.constants import GnmiMode


class GnmiClient:
    def __init__(self, server_host, server_port, username, password, cmd_time: int = 5, cacert='',
                 verify_tools_installed: bool = False, print_outputs: bool = True):
        assert cmd_time >= 0, f'unsupported cmd time: {cmd_time}. must be >= 0'

        self.server_host = server_host
        self.server_port = server_port
        self.username = username
        self.password = password
        self.cacert = cacert
        self.cmd_time = cmd_time

        self.cmd_runner = CmdRunner('GnmiClient', self.cmd_time, print_outputs)

        if verify_tools_installed:
            with allure.step('verify gnmic installed on player'):
                self.verify_gnmic_installation()
            with allure.step('verify grpcurl installed on player'):
                self.verify_grpcurl_installation()

    def verify_gnmic_installation(self):
        with allure.step('check if gnmic already installed'):
            out, err, _ = self.cmd_runner.run_cmd_in_process('gnmic version')
            gnmic_installed = 'command not found' not in out and 'command not found' not in err
            self._log(f'gnmic is {"" if gnmic_installed else "not "}installed on player')
        if not gnmic_installed:
            with allure.step('install gnmic on player'):
                out, err, _ = self.cmd_runner.run_cmd_in_process(
                    "bash -c \"$(curl -sL https://get-gnmic.openconfig.net)\"")
            with allure.step('verify gnmic is installed'):
                output = f'out:\n{out}\nerr:\n{err}'
                assert 'gnmic installed into /usr/local/bin/gnmic' in output \
                       or 'gnmic is already at latest' in output, f"gnmic installation failed with: {output}"

    def verify_grpcurl_installation(self):
        with allure.step('check if grpcurl already installed'):
            out, err, _ = self.cmd_runner.run_cmd_in_process('grpcurl -version')
            grpcurl_installed = 'command not found' not in out and 'command not found' not in err
            self._log(f'gnmic is {"" if grpcurl_installed else "not "}installed on player')
        if not grpcurl_installed:
            with allure.step('install grpcurl'):
                self.cmd_runner.run_cmd_in_process(
                    'sudo wget -O /tmp/grpcurl.tar.gz https://github.com/fullstorydev/grpcurl/releases/download/v1.8.8/grpcurl_1.8.8_linux_x86_64.tar.gz')
                self.cmd_runner.run_cmd_in_process('sudo tar -xzvf /tmp/grpcurl.tar.gz -C /tmp')
                self.cmd_runner.run_cmd_in_process('sudo mv /tmp/grpcurl /usr/local/bin/')
                self.cmd_runner.run_cmd_in_process('sudo rm /tmp/grpcurl.tar.gz')
            with allure.step('verify grpcurl installed'):
                out, err, _ = self.cmd_runner.run_cmd_in_process('grpcurl -version')
                output = f'out:\n{out}\nerr:\n{err}'
                assert 'command not found' not in output, f"failed to install grpcurl: {output}"

    def gnmic_subscribe(self, prefix, path, mode: str, flat: bool = False, username='', password='',
                        skip_cert_verify: bool = False, cacert='', debug_mode: bool = True,
                        cmd_time=None, keep_session_alive: bool = False, wait_till_done: bool = False) -> Tuple[
            str, str, subprocess.Popen]:
        allowed_modes = GnmiMode.ALL_MODES if not keep_session_alive else [GnmiMode.STREAM, GnmiMode.POLL]
        assert mode in allowed_modes, f'unsupported gnmi subscribe mode: "{mode}"'
        mode = f"--mode {mode}" if mode != GnmiMode.STREAM else GnmiMode.STREAM
        flat_option = ' --format flat' if flat else ''
        subscribe_op = f"subscribe --prefix '{prefix}' --path '{path}' --target netq {mode}" + flat_option
        return self._run_gnmic_op(subscribe_op, skip_cert_verify, cacert, debug_mode, cmd_time, username, password,
                                  keep_session_alive, wait_till_done)

    def gnmic_subscribe_interface(self, mode: str, interface_name: str, username: str = '', password: str = '',
                                  skip_cert_verify: bool = False, cacert='', debug_mode: bool = True,
                                  cmd_time=None, wait_till_done: bool = False) -> Tuple[str, str]:
        out, err, _ = self._run_gnmic_subscribe_interface(mode, interface_name, username, password, skip_cert_verify,
                                                          cacert,
                                                          debug_mode, cmd_time, False, wait_till_done)
        return out, err

    def gnmic_subscribe_interface_and_keep_session_alive(self, mode: str, interface_name: str, username: str = '',
                                                         password: str = '',
                                                         skip_cert_verify: bool = False, cacert='',
                                                         debug_mode: bool = True) -> subprocess.Popen:

        _, _, process = self._run_gnmic_subscribe_interface(mode, interface_name, username, password, skip_cert_verify,
                                                            cacert,
                                                            debug_mode, None, True)
        return process

    def gnmic_subscribe_system_events(self, mode: str, username: str = '', password: str = '',
                                      skip_cert_verify: bool = False, cacert='', debug_mode: bool = True,
                                      cmd_time=None, wait_till_done: bool = False) -> Tuple[str, str]:
        out, err, _ = self._run_gnmic_subscribe_system_events(mode, username, password, skip_cert_verify, cacert,
                                                              debug_mode, cmd_time, False, wait_till_done)
        return out, err

    def gnmic_capabilities(self, username: str = '', password: str = '', skip_cert_verify: bool = False, cacert='',
                           debug_mode: bool = True, cmd_time=None, wait_till_done: bool = False) -> Tuple[str, str]:
        capabilities_op = "capabilities"
        out, err, _ = self._run_gnmic_op(capabilities_op, skip_cert_verify, cacert, debug_mode, cmd_time, username,
                                         password, wait_till_done=wait_till_done)
        return out, err

    def close_session_and_get_out_and_err(self, process: subprocess.Popen, delay=0) -> Tuple[str, str]:
        return self.cmd_runner.kill_cmd_process(process, delay)

    def grpcurl_describe(self, username: str = '', password: str = '', skip_cert_verify: bool = True, cacert='',
                         cmd_time=None, service='') -> Tuple[str, str]:
        describe_op = f"describe {service}"
        out, err, _ = self._run_grpcurl_op(describe_op, skip_cert_verify, cacert, cmd_time, username,
                                           password)
        return out, err

    def _run_gnmic_subscribe_interface(self, mode: str, interface_name: str, username: str = '', password: str = '',
                                       skip_cert_verify: bool = False, cacert='', debug_mode: bool = True,
                                       cmd_time=None, keep_session_alive: bool = False, wait_till_done: bool = False) -> \
            Tuple[str, str, subprocess.Popen]:
        return self.gnmic_subscribe(f'interfaces/interface[name={interface_name}]/state', 'description', mode, True,
                                    username, password, skip_cert_verify, cacert, debug_mode, cmd_time,
                                    keep_session_alive, wait_till_done)

    def _run_gnmic_subscribe_system_events(self, mode: str, username: str = '', password: str = '',
                                           skip_cert_verify: bool = False, cacert='', debug_mode: bool = True,
                                           cmd_time=None, keep_session_alive: bool = False,
                                           wait_till_done: bool = False) -> \
            Tuple[str, str, subprocess.Popen]:
        return self.gnmic_subscribe('system-events', '', mode, False, username, password, skip_cert_verify, cacert,
                                    debug_mode, cmd_time, keep_session_alive, wait_till_done)

    def _run_gnmic_op(self, gnmi_op: str, skip_cert_verify: bool, cacert: str, debug_mode: bool, cmd_time,
                      username: str = '', password: str = '', keep_session_alive: bool = False,
                      wait_till_done: bool = False) -> Tuple[
            str, str, subprocess.Popen]:
        with allure.step('compose the gnmic command'):
            username = username or self.username
            password = password or self.password

            if skip_cert_verify:
                cert_flag = '--skip-verify'
            else:
                cacert_to_use = cacert or self.cacert
                assert cacert_to_use, 'cacert path was not specified'
                cert_flag = f'--tls-ca {cacert_to_use}'

            gnmic_cmd = (f"gnmic -a {self.server_host} --port {self.server_port} {cert_flag} "
                         f"-u {username} -p {password} {gnmi_op}") + (" -d" if debug_mode else "")
        with allure.step('run gnmic command in process'):
            return self.cmd_runner.run_cmd_in_process(gnmic_cmd, keep_session_alive, wait_till_done, cmd_time)

    def _run_grpcurl_op(self, grpcurl_op: str, is_insecure: bool, cacert: str, cmd_time, username: str = '',
                        password: str = '', keep_session_alive: bool = False) -> Tuple[
            str, str, subprocess.Popen]:
        with allure.step('compose the grpcurl command'):
            username = username or self.username
            password = password or self.password

            if is_insecure:
                cert_flag = '-insecure'
            else:
                cacert_to_use = cacert or self.cacert
                assert cacert_to_use, 'cacert path was not specified'
                cert_flag = f'-cacert {cacert_to_use}'

            grpcurl_cmd = (f"grpcurl {cert_flag} -H username:{username} -H password:{password} "
                           f"{self.server_host}:{self.server_port} {grpcurl_op}")
        with allure.step('run grpcurl command in process'):
            return self.cmd_runner.run_cmd_in_process(grpcurl_cmd, cmd_timeout=cmd_time)

    def _log(self, msg: str):
        logging.info(f"[GnmiClient] {msg}")

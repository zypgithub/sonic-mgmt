import logging
import subprocess
import time
from typing import Tuple

import ngts.tools.test_utils.allure_utils as allure
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.infra.IpTool import IpTool
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
        def _gnmic_is_installed() -> bool:
            out, err, _ = self.cmd_runner.run_cmd_in_process('gnmic version')
            gnmic_installed = 'not found' not in out and 'not found' not in err
            self._log(f'gnmic is {"" if gnmic_installed else "not "}installed on player')
            return gnmic_installed

        with allure.step('check if gnmic already installed'):
            gnmic_installed = _gnmic_is_installed()
        if not gnmic_installed:
            for i in range(3):
                with allure.step(f'attempt {i + 1}: install gnmic on player'):
                    self.cmd_runner.run_cmd_in_process('bash -c "$(curl -sL https://get-gnmic.openconfig.net)" -- -v 0.38.2')
                with allure.step('verify gnmic is installed'):
                    gnmic_installed = _gnmic_is_installed()
                    if gnmic_installed:
                        break
                    else:
                        time.sleep(3)
            assert gnmic_installed, 'failed to install gnmic'

    def verify_grpcurl_installation(self):
        def _grpcurl_is_installed() -> bool:
            out, err, _ = self.cmd_runner.run_cmd_in_process('grpcurl -version')
            grpcurl_installed = 'not found' not in out and 'not found' not in err
            self._log(f'gnmic is {"" if grpcurl_installed else "not "}installed on player')
            return grpcurl_installed

        with allure.step('check if grpcurl already installed'):
            grpcurl_installed = _grpcurl_is_installed()
        if not grpcurl_installed:
            with allure.step('install grpcurl'):
                self.cmd_runner.run_cmd_in_process(
                    'sudo wget -O /tmp/grpcurl.tar.gz https://github.com/fullstorydev/grpcurl/releases/download/v1.8.8/grpcurl_1.8.8_linux_x86_64.tar.gz')
                self.cmd_runner.run_cmd_in_process('sudo tar -xzvf /tmp/grpcurl.tar.gz -C /tmp')
                self.cmd_runner.run_cmd_in_process('sudo mv /tmp/grpcurl /usr/local/bin/')
                self.cmd_runner.run_cmd_in_process('sudo rm /tmp/grpcurl.tar.gz')
            with allure.step('verify grpcurl installed'):
                grpcurl_installed = _grpcurl_is_installed()
                assert grpcurl_installed, "failed to install grpcurl"

    def gnmic_subscribe(self, prefix, path, mode: str, flat: bool = False, username='', password='',
                        skip_cert_verify: bool = False, cacert='', debug_mode: bool = True,
                        cmd_time=None, keep_session_alive: bool = False, wait_till_done: bool = False) -> Tuple[
            str, str, subprocess.Popen]:
        allowed_modes = GnmiMode.ALL_MODES if not keep_session_alive else [GnmiMode.STREAM, GnmiMode.POLL]
        assert mode in allowed_modes, f'unsupported gnmi subscribe mode: "{mode}"'
        mode = f"--mode {mode}" if mode != GnmiMode.STREAM else GnmiMode.STREAM
        flat_option = ' --format flat' if flat else ''
        subscribe_op = f"subscribe --prefix '{prefix}' --path '{path}' --target nvos {mode}" + flat_option
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

    def gnmic_subscribe_interface_speed_and_keep_session_alive(self, mode: str, interface_name: str, username: str = '',
                                                               password: str = '',
                                                               skip_cert_verify: bool = False, cacert='',
                                                               debug_mode: bool = True) -> subprocess.Popen:

        _, _, process = self._run_gnmic_subscribe_interface(mode, interface_name, username, password, skip_cert_verify,
                                                            cacert, debug_mode, None, True,
                                                            False, 'infiniband/state/speed')
        return process

    def gnmic_subscribe_system_events(self, mode: str, username: str = '', password: str = '',
                                      skip_cert_verify: bool = False, cacert='', debug_mode: bool = True,
                                      cmd_time=None, keep_session_alive: bool = True,
                                      wait_till_done: bool = False) -> Tuple[str, str, subprocess.Popen]:
        out, err, sub_proc = self._run_gnmic_subscribe_system_events(mode, username, password, skip_cert_verify, cacert,
                                                                     debug_mode, cmd_time, keep_session_alive, wait_till_done)
        return out, err, sub_proc

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
                                       cmd_time=None, keep_session_alive: bool = False, wait_till_done: bool = False,
                                       interface_path: str = None) -> \
            Tuple[str, str, subprocess.Popen]:
        path = interface_path or 'state/description'
        return self.gnmic_subscribe(f'interfaces/interface[name={interface_name}]', path, mode, True,
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
        debug_mode = debug_mode and not skip_cert_verify
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

            host = f'[{self.server_host}]' if IpTool.is_address_ipv6(self.server_host) else self.server_host
            grpcurl_cmd = (f"grpcurl {cert_flag} -H username:{username} -H password:{password} "
                           f"{host}:{self.server_port} {grpcurl_op}")
        with allure.step('run grpcurl command in process'):
            return self.cmd_runner.run_cmd_in_process(grpcurl_cmd, cmd_timeout=cmd_time)

    def _log(self, msg: str):
        logging.info(f"[GnmiClient] {msg}")


class GnmicCmdBuilder:
    DEFAULT_TARGET = 'nvos'
    DEFAULT_PORT = 9339
    CMD_TEMPLATE = "gnmic -a {host} --port {port}{opts} {op}"

    def __init__(self, host: str = '', port=DEFAULT_PORT):
        self.host = host
        self.port: int = port
        self.options: str = ''
        self.operation: str = ''

    def build(self) -> str:
        self.options.strip()
        self.operation.strip()
        return GnmicCmdBuilder.CMD_TEMPLATE.format(host=self.host, port=self.port, opts=self.options, op=self.operation).strip()

    def address(self, address: str) -> 'GnmicCmdBuilder':
        self.host = address
        return self

    def set_port(self, port: int) -> 'GnmicCmdBuilder':
        self.port = port
        return self

    def user_creds(self, username: str, password: str) -> 'GnmicCmdBuilder':
        self.options += f" -u {username} -p {password}"
        return self

    def skip_verify(self) -> 'GnmicCmdBuilder':
        self.options += ' --skip-verify'
        return self

    def ca(self, cacert_path: str) -> 'GnmicCmdBuilder':
        self.options += f' --tls-ca {cacert_path}'
        return self

    def cert(self, key_path: str, public_path: str) -> 'GnmicCmdBuilder':
        self.options += f' --tls-key {key_path} --tls-cert {public_path}'
        return self

    def subscribe(self, prefix: str = '', path: str = '', mode: str = '', target: str = DEFAULT_TARGET) -> 'GnmicCmdBuilder':
        self.operation = f"subscribe --target {target} --prefix \'{prefix}\' --path \'{path}\'"
        if mode:
            self.operation += f' --mode {mode}'
        return self

    def capabilities(self) -> 'GnmicCmdBuilder':
        self.operation = "capabilities"
        return self

    def debug(self) -> 'GnmicCmdBuilder':
        self.operation += " -d"
        return self

    def format_flat(self) -> 'GnmicCmdBuilder':
        self.operation += " --format flat"
        return self

    def subscribe_interface_description(self, interface_name: str, mode: str = '', target: str = DEFAULT_TARGET) -> 'GnmicCmdBuilder':
        return self.subscribe(f'interfaces/interface[name={interface_name}]/state', 'description', mode, target)

    def subscribe_system_events(self, mode: str = '', target: str = DEFAULT_TARGET) -> 'GnmicCmdBuilder':
        return self.subscribe('system-events', '', mode, target)

from ngts.nvos_tools.infra.IpTool import IpTool


class SshCmdBuilder:
    SSH_CMD_TEMPLATE = 'ssh {opts} -p {port} {target}'

    def __init__(self, user: str, host: str, port=22):
        self.user = user
        self.host = host
        self.port = port
        self.options: str = ''

    def _prepare_ipv6_for_ssh(self) -> None:
        """Use bare IPv6 with -6; bracketed user@host is resolved as a DNS name by OpenSSH."""
        if self.host.startswith('[') and self.host.endswith(']'):
            self.host = self.host[1:-1]
        if not IpTool.is_address_ipv6(self.host):
            return
        if '-6' not in self.options.split():
            self.options = f'-6 {self.options}'.strip()

    @staticmethod
    def _bracket_ipv6_host(host: str) -> str:
        if IpTool.is_address_ipv6(host) and not (host.startswith('[') and host.endswith(']')):
            return f'[{host}]'
        return host

    def build(self) -> str:
        self.options = self.options.strip()
        self._prepare_ipv6_for_ssh()
        target = f'{self.user}@{self.host}'
        return SshCmdBuilder.SSH_CMD_TEMPLATE.format(
            opts=self.options, port=self.port, target=target
        ).strip()

    def ControlMaster(self, val) -> 'SshCmdBuilder':
        self.options += f' -o ControlMaster={val}'
        return self

    def ControlMasterAuto(self) -> 'SshCmdBuilder':
        return self.ControlMaster('auto')

    def ControlPersist(self, val) -> 'SshCmdBuilder':
        self.options += f' -o ControlPersist={val}'
        return self

    def ControlPersistInSecs(self, seconds) -> 'SshCmdBuilder':
        return self.ControlPersist(f'{seconds}s')

    def StrictHostKeyChecking(self, val) -> 'SshCmdBuilder':
        self.options += f' -o StrictHostKeyChecking={val}'
        return self

    def NoStrictHostKeyChecking(self) -> 'SshCmdBuilder':
        return self.StrictHostKeyChecking('no')

    def UserKnownHostsFile(self, val) -> 'SshCmdBuilder':
        self.options += f' -o UserKnownHostsFile={val}'
        return self

    def NoUserKnownHostsFile(self) -> 'SshCmdBuilder':
        return self.UserKnownHostsFile('/dev/null')

    def GSSAPIAuthentication(self, val) -> 'SshCmdBuilder':
        self.options += f' -o GSSAPIAuthentication={val}'
        return self

    def NoGSSAPIAuthentication(self) -> 'SshCmdBuilder':
        return self.GSSAPIAuthentication('no')

    def PubkeyAuthentication(self, val) -> 'SshCmdBuilder':
        self.options += f' -o PubkeyAuthentication={val}'
        return self

    def NoPubkeyAuthentication(self) -> 'SshCmdBuilder':
        return self.PubkeyAuthentication('no')

    def ConnectTimeout(self, seconds=30) -> 'SshCmdBuilder':
        self.options += f' -o ConnectTimeout={seconds}'
        return self

    def PreferredAuthentications(self, val) -> 'SshCmdBuilder':
        self.options += f' -o PreferredAuthentications={val}'
        return self

    def PreferredAuthenticationsPassword(self) -> 'SshCmdBuilder':
        return self.PreferredAuthentications('password')

    def NumberOfPasswordPrompts(self, num_pw_prompts) -> 'SshCmdBuilder':
        self.options += f' -o NumberOfPasswordPrompts={num_pw_prompts}'
        return self

    def ServerAliveInterval(self, interval_seconds) -> 'SshCmdBuilder':
        self.options += f' -o ServerAliveInterval={interval_seconds}'
        return self

    def ServerAliveCountMax(self, num_intervals) -> 'SshCmdBuilder':
        self.options += f' -o ServerAliveCountMax={num_intervals}'
        return self

    def use_auth_key(self, key_path) -> 'SshCmdBuilder':
        self.options += f' -i {key_path}'
        return self

    def set_ssn(self) -> 'SshCmdBuilder':
        return self.NoStrictHostKeyChecking().NoUserKnownHostsFile()

    def ForceTTY(self) -> 'SshCmdBuilder':
        self.options += ' -tt'
        return self

    def set_num_password_prompts(self, num_pw_prompts) -> 'SshCmdBuilder':
        return self.PreferredAuthenticationsPassword().NumberOfPasswordPrompts(num_pw_prompts)

    def set_long_lasting_session(self, num_intervals=5, interval_seconds=60) -> 'SshCmdBuilder':
        return self.ServerAliveInterval(interval_seconds).ServerAliveCountMax(num_intervals)


class SshPassCmdBuilder(SshCmdBuilder):
    SSH_CMD_TEMPLATE = "sshpass -p '{pw}' " + SshCmdBuilder.SSH_CMD_TEMPLATE

    def __init__(self, user: str, password: str, host: str, port=22, cmd_to_execute: str = ''):
        super().__init__(user, host, port)
        self.password = password
        self.cmd_to_execute = cmd_to_execute

    def build(self) -> str:
        self.options = self.options.strip()
        self._prepare_ipv6_for_ssh()
        target = f'{self.user}@{self.host}'
        cmd = SshPassCmdBuilder.SSH_CMD_TEMPLATE.format(
            pw=self.password, opts=self.options, port=self.port, target=target
        ).strip() + f" '{self.cmd_to_execute}'"
        return cmd.strip()


class ScpPassCmdBuilder(SshPassCmdBuilder):
    SCP_CMD_TEMPLATE = "sshpass -p '{pw}' scp {opts} {src} {usr}@{host}:{dest}"

    def __init__(self, user: str, password: str, host: str, src: str, dest: str, port=22):
        super().__init__(user, password, host, port)
        self.src = src
        self.dest = dest

    def build(self) -> str:
        self.options = self.options.strip()
        self._prepare_ipv6_for_ssh()
        return ScpPassCmdBuilder.SCP_CMD_TEMPLATE.format(
            pw=self.password,
            opts=self.options,
            src=self.src,
            usr=self.user,
            host=self._bracket_ipv6_host(self.host),
            dest=self.dest
        )

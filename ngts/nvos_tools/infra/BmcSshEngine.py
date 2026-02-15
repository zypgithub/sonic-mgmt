from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.general_constants.constants import DefaultConnectionValues
from ngts.nvos_tools.infra.PexpectTool import PexpectTool
from ngts.nvos_tools.infra.SshCmdBuilder import SshCmdBuilder, SshPassCmdBuilder
from ngts.tools.test_utils import allure_utils as allure

PEXPECT_SSH_ERR = 'failed to start pexpect ssh session'
BMC_SESSION_ERR = 'failure in ssh session with BMC'

BMC_SELL_PROMPT_PATTERNS = ['.*@.*bmc.*#', '#']
SHELL_PROMPT_PATTERNS = DefaultConnectionValues.DEFAULT_PROMPTS + ['#', r'\$']
ENTER_PASSWORD_PATTERNS = ['[Pp]assword:']
CHANGE_PASSWORD_PATTERNS = ['Enter.*old password:']

BACKUP_PW = 'ABYX12#14artb'

SSN_CMD = 'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {usr}@{ip}'


class BmcSshEngine:
    """
    This class provides ssh engine to internal BMC, using pexpect tool
    """

    def __init__(self, dut_engine: LinuxSshEngine, bmc_username, bmc_default_password, bmc_another_password=''):
        self._session: PexpectTool = None
        self.dut_engine: LinuxSshEngine = dut_engine
        self.bmc_username = bmc_username
        self.bmc_default_password = bmc_default_password
        self.bmc_another_password = bmc_another_password

    def run_cmd(self, cmd, **kwargs) -> str:
        """
        Run command on BMC via pexpect SSH session.
        :param cmd: command to execute
        :param kwargs: accepts but does not implement validate, print_output, max_loops
                       from the SSH engine interface
        """
        exc: Exception = None
        try:
            if not self._session:
                self.connect()
            sanitized = kwargs.get('sanitized_cmd', None)
            log_cmd = cmd if sanitized is None else sanitized
            with allure.step(self._msg(f'run cmd: {log_cmd}')):
                self._session.sendline(cmd)
                res_index, out = self._session.expect_and_get_output(BMC_SELL_PROMPT_PATTERNS)
                assert res_index < len(BMC_SELL_PROMPT_PATTERNS), f'{BMC_SESSION_ERR}: did not get bmc shell prompt'
                return out
        except Exception as e:
            exc = e
            raise
        finally:
            if exc is not None:
                self.disconnect()

    def connect(self):
        #   TODO: handle: "There were too many logins for 'admin'." ?
        with allure.step(self._msg('connect bmc session')):
            passwords = [BACKUP_PW, self.bmc_default_password, self.bmc_another_password]
            for pw in passwords:
                try:
                    with allure.step(self._msg(f'ssh bmc using user: {self.bmc_username} , password: {pw}')):
                        session = self._start_new_bmc_ssh_session(pw)
                        self._session = session
                        return
                except Exception:
                    if pw == passwords[-1]:
                        self.disconnect()
                        raise

    def disconnect(self):
        if self._session is not None:
            with allure.step(self._msg('disconnect bmc session')):
                self._session.close()
                self._session = None

    def _start_new_bmc_ssh_session(self, password) -> PexpectTool:
        with allure.step(self._msg('start pexpect ssh session to dut')):
            nos_session = self._start_ssh_to_nos_pexpect_session()
        with allure.step(self._msg('ssh bmc from within the dut ssh session')):
            bmc_session = self._connect_bmc_from_nos_pexpect_session(nos_session, password)
        return bmc_session

    def _start_ssh_to_nos_pexpect_session(self) -> PexpectTool:
        with allure.step(self._msg('send dummy cmd with devts engine to handle password change if needed')):
            self.dut_engine.run_cmd('echo "hi"')
        with allure.step(self._msg('start ssh pexpect session to nos')):
            ssh_cmd = SshPassCmdBuilder(self.dut_engine.username, self.dut_engine.password, self.dut_engine.ip,
                                        self.dut_engine.ssh_port).set_ssn().set_long_lasting_session().build()
            session = PexpectTool(ssh_cmd)
            self._expect_shell_prompt(session)
        return session

    def _connect_bmc_from_nos_pexpect_session(self, nos_shell: PexpectTool, password) -> PexpectTool:
        with allure.step('start ssh to bmc from nos shell'):
            ssn_cmd = SshCmdBuilder(self.bmc_username, '10.0.1.1').set_ssn().build()
            nos_shell.sendline(ssn_cmd)
            res = nos_shell.expect(ENTER_PASSWORD_PATTERNS)
            assert res < len(ENTER_PASSWORD_PATTERNS), f'{PEXPECT_SSH_ERR}: no password prompt'
        with allure.step(f'enter password: {password}'):
            nos_shell.sendline(password)
            password = self._handle_change_password_prompt(nos_shell, password)
            # TODO: save the new password somehow?
            bmc_shell = nos_shell
        return bmc_shell

    def _handle_change_password_prompt(self, session: PexpectTool, old_password: str) -> str:
        expect = SHELL_PROMPT_PATTERNS + CHANGE_PASSWORD_PATTERNS
        res = session.expect(SHELL_PROMPT_PATTERNS + CHANGE_PASSWORD_PATTERNS)
        assert res < len(expect), f'{PEXPECT_SSH_ERR}: did not get expected prompt. expected: {expect}'
        if res < len(SHELL_PROMPT_PATTERNS):
            return old_password

        session.sendline(old_password)
        expect = ['Enter.*new password:']
        res = session.expect(expect)
        assert res < len(expect), f'{PEXPECT_SSH_ERR}: did not get expected prompt. expected: {expect}'

        new_password = BACKUP_PW
        session.sendline(new_password)
        expect = ['Retype.*new password:']
        res = session.expect(expect)
        assert res < len(expect), f'{PEXPECT_SSH_ERR}: did not get expected prompt. expected: {expect}'

        session.sendline(new_password)
        self._expect_shell_prompt(session)

        return new_password

    def _expect_shell_prompt(self, session: PexpectTool):
        res = session.expect(SHELL_PROMPT_PATTERNS)
        assert res < len(SHELL_PROMPT_PATTERNS), f'{PEXPECT_SSH_ERR}: did not get shell prompt'

    def _msg(self, msg: str) -> str:
        return f'[{self.bmc_username}@bmc] {msg}'

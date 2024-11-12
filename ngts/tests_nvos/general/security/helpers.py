from typing import List

from ngts.nvos_tools.infra.CmdRunner import CmdRunner


def add_issue_if(issue_cond, issues: List[str], issue_msg: str):
    if issue_cond:
        issues.append(issue_msg)


def assert_no_issues(header_prefix: str, issues: List[str], err_msg_header: str = ''):
    assert not issues, f'{header_prefix} - {err_msg_header}\nissues found:\n\t* ' + '\n\t* '.join(issues)


ETC_HOSTS = '/etc/hosts'


def add_etc_host_mapping_to_dn(dn, address, cmd_runner=None):
    cmd_runner = cmd_runner or CmdRunner()
    cmd_runner.run_cmd(f'echo "{address} {dn}" | sudo tee -a {ETC_HOSTS}')


def remove_etc_host_mapping_to_dn(dn, cmd_runner=None):
    cmd_runner = cmd_runner or CmdRunner()
    # cmd = f"sudo sed -i '/{dn}/d' {ETC_HOSTS}"
    cmd = f"cp -f {ETC_HOSTS} /tmp/hosts.new && sed -i '/{dn}/d' /tmp/hosts.new && sudo tee {ETC_HOSTS} < /tmp/hosts.new && rm -f /tmp/hosts.new"
    cmd_runner.run_cmd(cmd)

from ngts.nvos_tools.infra.CmdRunner import CmdRunner

ETC_HOSTS = '/etc/hosts'


def add_etc_host_mapping_to_dn(dn, address, cmd_runner=None):
    cmd_runner = cmd_runner or CmdRunner()
    cmd_runner.run_cmd(f'echo "{address} {dn}" | sudo tee -a {ETC_HOSTS}')


def remove_etc_host_mapping_to_dn(dn, cmd_runner=None):
    cmd_runner = cmd_runner or CmdRunner()
    # cmd = f"sudo sed -i '/{dn}/d' {ETC_HOSTS}"
    cmd = f"cp -f {ETC_HOSTS} /tmp/hosts.new && sed -i '/{dn}/d' /tmp/hosts.new && sudo tee {ETC_HOSTS} < /tmp/hosts.new && rm -f /tmp/hosts.new"
    cmd_runner.run_cmd(cmd)

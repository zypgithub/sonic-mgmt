from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.CmdRunner import CmdRunner


def get_player_scp_host_creds(player: LinuxSshEngine) -> str:
    return f'{player.username}:{player.password}@{player.ip}'


def run_scp(player: LinuxSshEngine, src_path, dst_path, download_from_remote=False):
    scp_cmd = f'sshpass -p {player.password} scp -P {player.ssh_port} ' \
        f'-o PubkeyAuthentication=no -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
    if download_from_remote:
        scp_cmd += f'{player.username}@{player.ip}:{src_path} {dst_path}'
    else:
        scp_cmd += f'{src_path} {player.username}@{player.ip}:{dst_path}'

    local_engine = CmdRunner('Local Player')
    local_engine.run_cmd(scp_cmd)

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine


def get_player_scp_host_creds(player: LinuxSshEngine) -> str:
    return f'{player.username}:{player.password}@{player.ip}'

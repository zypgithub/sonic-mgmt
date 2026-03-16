from ngts.nvos_tools.infra.IpTool import IpTool


def get_player_scp_host_creds(player) -> str:
    ip = IpTool.format_ip_for_uri(player)
    return f'{player.username}:{player.password}@{ip}'

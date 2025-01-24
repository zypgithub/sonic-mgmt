import re
from collections import namedtuple
from ngts.constants.performance_constants import PerfConsts


def get_dvs_topology_obj(players):
    topology = namedtuple('Topology', ['players', 'ports', 'ports_interconnects', 'players_all_ports'])
    dut_left_right_ports_aliases = players['dut']['cli'].performance.get_player_left_right_ports_aliases()
    ports = {}
    players_all_ports = {}
    ports_interconnects = {}
    dut_left_port_dict = dict(dut_left_right_ports_aliases['left_ports'])
    dut_right_port_dict = dict(dut_left_right_ports_aliases['right_ports'])
    ports.update(dut_left_port_dict)
    ports.update(dut_right_port_dict)
    players_all_ports.update({'dut': {'left_ports': list(dut_left_port_dict.values()),
                                      'right_ports': list(dut_right_port_dict.values())}})
    for tg_alias in PerfConsts.PERF_SETUP_TG_ALIASES:
        tg_port_labels, _ = players[tg_alias]['cli'].performance.get_base_ports()
        tg_ports = list(map(lambda port_label_tuple: port_label_tuple[0], tg_port_labels))
        tg_port_aliases = players[tg_alias]['cli'].performance.get_player_unconnected_connected_ports_aliases()
        tg_unconnected_port_aliases = dict(tg_port_aliases['unconnected_ports'])
        tg_connected_port_aliases = dict(tg_port_aliases['connected_ports'])
        ports.update(tg_unconnected_port_aliases)
        ports.update(tg_connected_port_aliases)
        players_all_ports.update({tg_alias: {'unconnected_ports': list(tg_unconnected_port_aliases.values()),
                                             'connected_ports': list(tg_connected_port_aliases.values())}})
        tg_regex = r"(left|right)_tg"
        tg_place = re.search(tg_regex, tg_alias).group(1)
        for tg_port_alias, tg_port in tg_port_aliases['connected_ports']:
            port_index = tg_ports.index(tg_port) % len(dut_left_right_ports_aliases[f'{tg_place}_ports'])
            port_alias, port = dut_left_right_ports_aliases[f'{tg_place}_ports'][port_index]
            ports_interconnects.update({port_alias: tg_port_alias})
    return topology(players, ports, ports_interconnects, players_all_ports)


def get_nvue_sonic_topology_obj(players):
    pass

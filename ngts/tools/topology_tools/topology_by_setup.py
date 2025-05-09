from infra.tools.topology_tools.topology_setup_utils import get_topology_by_setup_name, create_player_entry
from ngts.constants.constants import PlayersAliases
import logging
from ngts.common.util import get_specified_installed_dpu_indexes
logger = logging.getLogger()


def need_dpu_player(setup_name):
    return 'bobcat' in setup_name or 'CI_sonic_SS' in setup_name


def get_topology_by_setup_name_and_aliases(setup_name, slow_cli, override_type=False):
    topology = get_topology_by_setup_name(setup_name, slow_cli, override_type)
    if need_dpu_player(setup_name):
        add_dpu_player(topology, slow_cli, override_type)

    return update_dut_alias(topology)


def update_dut_alias(topology):
    if 'dut' not in topology.players.keys():
        # For the lower tor in dual-tor topology, the key of dut name got from noga is 'dut-b'
        # If the topology only has key 'dut-b' without key 'dut', means it is deployed as a normal setup
        # Change the 'dut-b' to 'dut' in this case
        if 'dut-b' in topology.players.keys():
            topology.players['dut'] = topology.players.pop('dut-b')
            topology.players['dut_serial'] = topology.players.pop('dut-b_serial')
            topology.players['dut']['attributes'].noga_query_data['attributes']['Common']['Description'] = 'dut'
            topology.players['fanout'] = topology.players.pop('fanout-b')
            topology.players['fanout_serial'] = topology.players.pop('fanout-b_serial')
            topology.players['fanout']['attributes'].noga_query_data['attributes']['Common']['Description'] = 'fanout'
        for alias in PlayersAliases.Aliases_list:
            if alias in topology.players.keys():
                topology.players['dut'] = topology.players[alias]
                del topology.players[alias]
    return topology


def add_dpu_player(topology, slow_cli, override_type):
    dpu_player_entry = {'DESCRIPTION': 'dpu0',
                        'SSH_PORT': 5021,
                        'XML_RPC_PORT': 9999,
                        'TYPE_TITLE': "Switch",
                        'TYPE': '11',
                        'IP': topology.players['dut']['engine'].ip,
                        }
    dpu_indexes = get_specified_installed_dpu_indexes()
    base_dpu_ssh_nat_port = 5021

    for dpu_index in dpu_indexes:
        dpu_host_name = f'dpu{dpu_index}'
        dpu_player_entry['DESCRIPTION'] = dpu_host_name
        dpu_player_entry['SSH_PORT'] = base_dpu_ssh_nat_port + dpu_index
        logger.info(f"create dpu{dpu_index} players")
        topology.players.update(create_player_entry(dpu_player_entry, slow_cli, override_type))
        if dpu_host_name in topology.players:
            topology.players[dpu_host_name]['attributes'].noga_query_data['attributes']['Common']['Name'] += f"-dpu-{dpu_index}"
            topology.players[dpu_host_name]['attributes'].noga_query_data['attributes']['Common']['Description'] = dpu_host_name

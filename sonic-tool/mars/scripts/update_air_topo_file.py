import argparse
import json
import xml.etree.ElementTree as ET
import xml.dom.minidom

from infra.tools.nvidia_air_tools.air import (
    SONIC_MGMT_RPYC_PORT,
    SONIC_MGMT_SSH,
    generate_port_mapping_dict,
    get_air_api_object,
    get_public_port_for_host,
    get_simulation_hosts_services_dict
)
from infra.tools.general_constants.air_constants import HostsConstants, NvidiaAirConstants, SimulationMetadata

MARS_TOPO_FOLDER_PATH = "/auto/sw_regression/system/SONIC/MARS/conf/topo/"

def get_xml_parsed_topo(setup_name):
    topo_file_path = MARS_TOPO_FOLDER_PATH + setup_name + "/topology.xml"
    with open(topo_file_path, "r") as file:
        topo_xml = file.read()
    topo = ET.fromstring(topo_xml)
    return topo

def get_setup_topo(setup_name):
    topo_file_path = MARS_TOPO_FOLDER_PATH + setup_name + "/topology.xml"
    with open(topo_file_path, "r") as file:
        topo_xml = file.read()
    topo = ET.fromstring(topo_xml)
    return topo

def get_simulation_connections(setup_name):
    air = get_air_api_object(NvidiaAirConstants.SONIC)
    simulation = air.simulations.list(title=setup_name)
    if not simulation:
        raise Exception(f'Simulation {setup_name} not available. Please check that simulation started.')
    simulation = simulation[0]
    simulation_metadata = json.loads(simulation.metadata)
    topology_type = simulation_metadata.get(SimulationMetadata.TOPOLOGY_TYPE, '').upper()
    _, ports_mapping_dict, mapping_public_ports_to_host = generate_port_mapping_dict(topology_type)
    hosts_services_dict = get_simulation_hosts_services_dict(simulation, mapping_public_ports_to_host)

    simulation_connections = {}

    sonic_mgmt_ip, sonic_mgmt_ssh_port = get_public_port_for_host(HostsConstants.HYPERVISOR, hosts_services_dict,
        internal_port=ports_mapping_dict[HostsConstants.HYPERVISOR].get(SONIC_MGMT_SSH))
    _, sonic_mgmt_rpyc_port = get_public_port_for_host(HostsConstants.HYPERVISOR, hosts_services_dict,
        internal_port=ports_mapping_dict[HostsConstants.HYPERVISOR].get(SONIC_MGMT_RPYC_PORT))

    simulation_connections[HostsConstants.SONIC_MGMT] = {
        "IP": sonic_mgmt_ip,
        "SSH_PORT": sonic_mgmt_ssh_port,
        "RPYC_PORT": sonic_mgmt_rpyc_port
    }
    return simulation_connections

def update_topo_player(player_name, parent_map, player_connections):
    base_ip_node = topo.find(f"HOSTS[@name='{player_name}']").find("HOST").find("BASE_IP")
    host_node = parent_map[base_ip_node]
    base_ip_node.text = player_connections["IP"]
    port_node = host_node.find("PORT")
    if port_node is None:
        port_node = ET.Element("PORT")
        host_node.append(port_node)
    port_node.text = str(player_connections["SSH_PORT"])
    rpyc_port_node = host_node.find("RPC_PORT")
    if rpyc_port_node is None:
        rpyc_port_node = ET.Element("RPC_PORT")
        host_node.append(rpyc_port_node)
    rpyc_port_node.text = str(player_connections["RPYC_PORT"])

    ip_node = topo.find(f"HOSTS[@name='{player_name}']").find("HOST").find("CONNECTIONS").find("CONNECTION").find("IP")
    ip_node.text = player_connections["IP"]
    connection_node = parent_map[ip_node]
    connection_port_node = connection_node.find("PORT")
    if connection_port_node is None:
        connection_port_node = ET.Element("PORT")
        connection_node.append(connection_port_node)
    connection_port_node.text = str(player_connections["SSH_PORT"])

def update_air_topo(topo, simulation_connections):
    # Build the parent map
    parent_map = {child: parent for parent in topo.iter() for child in parent}

    update_topo_player('SONIC_MGMT', parent_map, simulation_connections[HostsConstants.SONIC_MGMT])

def write_air_topo_file(topo, setup_name):
    rough_string = ET.tostring(topo, encoding='unicode')
    reparsed = xml.dom.minidom.parseString(rough_string)

    # Remove whitespace-only text nodes to avoid extra blank lines
    def remove_whitespace_nodes(node):
        for child in list(node.childNodes):
            if child.nodeType == xml.dom.minidom.Node.TEXT_NODE:
                if child.data.strip() == '':
                    node.removeChild(child)
                    child.unlink()
            elif child.nodeType == xml.dom.minidom.Node.ELEMENT_NODE:
                remove_whitespace_nodes(child)

    remove_whitespace_nodes(reparsed)

    pretty_xml = reparsed.toprettyxml(indent="    ")
    # Replace the default XML declaration with the proper one including encoding
    lines = pretty_xml.split('\n')
    if lines[0].startswith('<?xml'):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    pretty_xml = '\n'.join(lines)
    with open(MARS_TOPO_FOLDER_PATH + setup_name + "/topology.xml", "w") as file:
        file.write(pretty_xml)

def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup_name", dest="setup_name", required=True, help="The setup name")
    return parser.parse_args()

if __name__ == "__main__":
    args = _parse_args()
    simulation_connections = get_simulation_connections(args.setup_name)
    topo = get_xml_parsed_topo(args.setup_name)
    update_air_topo(topo, simulation_connections)
    write_air_topo_file(topo, args.setup_name)
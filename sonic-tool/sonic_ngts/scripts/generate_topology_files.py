#!/usr/bin/env python
"""
Script to generate XML and JSON topology files from configuration files.

This script reads:
- setup_conf.yml: Device configuration (switches, hosts, other_entities)
- leopard_port_connection.csv: Port connection mappings
- port_config_leopard.ini: Port configuration (Ethernet to alias mapping)

And generates:
- Individual XML files for each device (switches and hosts)
- topology.xml: Main topology file with all devices and connections
- JSON file: Device info and links information

Usage:
    python generate_topology_files.py
"""

import argparse
import csv
import yaml
import os
import re
import json
import hashlib
from collections import defaultdict


def generate_mac_address(seed_string):
    """
    Generate a deterministic MAC address from a seed string.
    """
    hash_obj = hashlib.md5(seed_string.encode())
    hash_hex = hash_obj.hexdigest()
    # Use first 12 hex digits to form MAC address
    mac = ':'.join([hash_hex[i:i+2] for i in range(0, 12, 2)])
    return mac


def parse_setup_conf_yml(yml_file):
    """Parse the setup configuration YAML file."""
    with open(yml_file, 'r') as f:
        config = yaml.safe_load(f)
    return config


def get_hostnames(setup_config_file=None, setup_config=None):
    """
    Get hostnames for sonic_mgmt, ha, and hb from setup configuration.

    :param setup_config_file: Path to YAML configuration file
                              (optional if setup_config is provided)
    :param setup_config: Parsed configuration dictionary
                         (optional if setup_config_file is provided)
    :return: Dictionary with keys 'sonic_mgmt', 'ha', 'hb' containing
             hostname strings, or None if not found
    """
    # Load config if file path provided
    if setup_config_file:
        setup_config = parse_setup_conf_yml(setup_config_file)

    if not setup_config:
        raise ValueError("Either setup_config_file or setup_config must be "
                         "provided")

    hostnames = {
        'sonic_mgmt': None,
        'ha': None,
        'hb': None
    }

    # Get ha and hb hostnames from hosts section
    for host in setup_config.get('hosts', []):
        alias = host.get('alias', '')
        if alias == 'ha':
            hostnames['ha'] = host.get('hostname')
        elif alias == 'hb':
            hostnames['hb'] = host.get('hostname')

    # Get sonic_mgmt hostname from other_entities section
    for entity in setup_config.get('other_entities', []):
        alias = entity.get('alias', '')
        entity_id = entity.get('entity_id', '')
        # Check both alias and entity_id for sonic-mgmt/sonic_mgmt
        if (alias in ['sonic-mgmt', 'sonic_mgmt'] or
                entity_id in ['sonic-mgmt', 'sonic_mgmt']):
            hostnames['sonic_mgmt'] = entity.get('hostname')
            break

    return hostnames


def parse_port_connection_csv(csv_file):
    """
    Parse the port connection CSV file.
    Expected format: StartDevice,StartPort,EndDevice,EndPort
    """
    connections = []
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            start_device = row.get('StartDevice', '').strip()
            start_port = row.get('StartPort', '').strip()
            end_device = row.get('EndDevice', '').strip()
            end_port = row.get('EndPort', '').strip()

            if not start_device or not start_port:
                continue

            # Normalize port names (ept -> etp)
            start_port = start_port.replace('ept', 'etp')
            end_port = end_port.replace('ept', 'etp')

            connections.append({
                'start_device': start_device,
                'start_port': start_port,
                'end_device': end_device,
                'end_port': end_port
            })
    return connections


def parse_port_config_ini(ini_file):
    """
    Parse the port config INI file.
    Expected format: name (EthernetX), lanes, alias, index, speed
    """
    port_config = {}
    with open(ini_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) >= 4:
                ethernet_name = parts[0]
                alias = parts[2]
                port_config[ethernet_name] = {
                    'alias': alias,
                    'lanes': parts[1] if len(parts) > 1 else '',
                    'index': parts[3] if len(parts) > 3 else '',
                    'speed': parts[4] if len(parts) > 4 else ''
                }
    return port_config


def build_device_map(setup_config):
    """
    Build a mapping from device alias to device info.
    """
    device_map = {}

    # Process switches
    for switch in setup_config.get('switches', []):
        alias = switch['alias']
        device_map[alias] = {
            'type': 'switch',
            'alias': alias,
            'ip': switch['ip'],
            'hostname': switch['hostname'],
            'username': switch.get('username', ''),
            'password': switch.get('password', ''),
            'mac': switch.get('mac', generate_mac_address(switch['hostname'])),
            'sub_type': switch.get('sub_type', ''),
            'switch_type': switch.get('switch_type', ''),
            'devdescription': switch.get('devdescription', '')
        }

    # Process hosts
    for host in setup_config.get('hosts', []):
        alias = host['alias']
        device_map[alias] = {
            'type': 'host',
            'alias': alias,
            'ip': host['ip'],
            'hostname': host['hostname'],
            'username': host.get('username', ''),
            'password': host.get('password', ''),
            'mac': host.get('mac', generate_mac_address(host['hostname']))
        }
        # Store port mappings (e.g., ha-1: enp130s0f0)
        for key, value in host.items():
            if key.startswith(alias + '-') or (key.startswith('h') and '-' in key):
                device_map[alias][key] = value

    # Process other_entities
    for entity in setup_config.get('other_entities', []):
        entity_id = entity.get('entity_id', '')
        alias = entity.get('alias', '')
        if entity_id:
            device_map[entity_id] = {
                'type': 'host',
                'alias': alias,
                'ip': entity['ip'],
                'hostname': entity['hostname'],
                'username': entity.get('username', ''),
                'password': entity.get('password', ''),
                'mac': entity.get('mac', generate_mac_address(entity['hostname']))
            }

    return device_map


def get_alias_number(port_alias):
    """Extract the number from port alias, e.g., 'etp1' -> '1', 'etp4a' -> '4'"""
    match = re.search(r'etp(\d+)', port_alias, re.IGNORECASE)
    return match.group(1) if match else None


def get_alias_letter(port_alias):
    """Extract the letter from port alias, e.g., 'etp4a' -> 'a', 'etp1' -> None"""
    match = re.search(r'etp\d+([a-z])', port_alias, re.IGNORECASE)
    return match.group(1) if match else None


def get_port_split_number(port_alias):
    """Get port split number from letter: a=1, b=2, c=3, d=4, etc."""
    letter = get_alias_letter(port_alias)
    if not letter:
        return None
    return ord(letter.lower()) - ord('a') + 1


def get_split_number(port_alias, port_config):
    """Get the split number (2, 4, or 8) for a port alias."""
    alias_num = get_alias_number(port_alias)
    if not alias_num:
        return None
    # Count all ports with same base number (e.g., etp4a, etp4b, etp4c, etp4d -> 4)
    split_count = 0
    for eth_name, info in port_config.items():
        port_alias_check = info.get('alias', '')
        if get_alias_number(port_alias_check) == alias_num:
            split_count += 1
    return split_count if split_count > 1 else None


def get_port_number_from_ethernet(ethernet_name):
    """Extract port number from Ethernet name, e.g., 'Ethernet0' -> 0"""
    match = re.search(r'Ethernet(\d+)', ethernet_name, re.IGNORECASE)
    return int(match.group(1)) if match else None


def get_loopback_port_number(port1_info, port2_info):
    """Determine port number in loopback (1 or 2) based on port_num comparison."""
    port_num_1 = port1_info.get('port_num')
    port_num_2 = port2_info.get('port_num')
    if port_num_1 is None or port_num_2 is None:
        return None
    return 1 if port_num_1 < port_num_2 else 2


def build_port_mappings(setup_config, port_config, connections, device_map):
    """
    Build port mappings for each device.
    Returns: dict mapping device alias to list of port info
    """
    device_ports = defaultdict(list)

    # Build host port alias mapping
    host_port_alias_map = {}
    for alias, device_info in device_map.items():
        if device_info['type'] == 'host':
            for key, value in device_info.items():
                if isinstance(value, str) and (key.startswith(alias + '-') or
                    (key.startswith('h') and '-' in key and key.endswith(('1', '2')))):
                    host_port_alias_map[(alias, key)] = value

    # Add ports for switches from port_config
    for switch_alias, switch_info in device_map.items():
        if switch_info['type'] == 'switch':
            for ethernet_name, port_info in port_config.items():
                port_alias = port_info['alias']
                port_num = get_port_number_from_ethernet(ethernet_name)
                is_split = get_alias_letter(port_alias) is not None
                split_num = get_split_number(port_alias, port_config) if is_split else None
                port_split_num = get_port_split_number(port_alias) if is_split else None

                device_ports[switch_alias].append({
                    'id': port_alias,
                    'if': ethernet_name,
                    'description': '',
                    'mac': generate_mac_address(f"{switch_info['hostname']}-{port_alias}"),
                    'port_num': port_num,
                    'is_split': is_split,
                    'split_num': split_num,
                    'port_split_number': port_split_num
                })

    # Add ports for hosts
    for host_alias, host_info in device_map.items():
        if host_info['type'] == 'host':
            for key, value in host_info.items():
                if isinstance(value, str) and (key.startswith(host_alias + '-') or
                    (key.startswith('h') and '-' in key and key.endswith(('1', '2')))):
                    port_name = value
                    device_ports[host_alias].append({
                        'id': port_name,
                        'if': port_name,
                        'description': '',
                        'mac': generate_mac_address(f"{host_info['hostname']}-{port_name}")
                    })

    # Build connection descriptions from CSV
    # Expand split port connections: if etp4b->etp5b exists, also create etp4a->etp5a, etc.
    expanded_connections = []
    seen_connections = set()  # Track connections to avoid duplicates

    for conn in connections:
        start_port_norm = conn['start_port'].strip().replace('ept', 'etp')
        end_port_norm = conn['end_port'].strip().replace('ept', 'etp')
        conn_key = (conn['start_device'], start_port_norm, conn['end_device'].strip(), end_port_norm)

        if conn_key not in seen_connections:
            expanded_connections.append(conn)
            seen_connections.add(conn_key)

        # For DUT to DUT connections, check if we need to expand split ports
        if conn['start_device'] == 'dut' and conn['end_device'].strip() == 'dut':
            start_port = start_port_norm
            end_port = end_port_norm

            # Check if these are split ports
            start_letter = get_alias_letter(start_port)
            end_letter = get_alias_letter(end_port)

            if start_letter and end_letter:
                # Both are split ports - find all ports in the same split groups
                start_base = get_alias_number(start_port)
                end_base = get_alias_number(end_port)

                if start_base and end_base:
                    # Find all ports with same base numbers from port_config
                    start_split_ports = []
                    end_split_ports = []

                    for eth_name, port_info in port_config.items():
                        port_alias = port_info.get('alias', '')
                        if not port_alias:
                            continue
                        port_base = get_alias_number(port_alias)
                        port_letter = get_alias_letter(port_alias)

                        if port_base == start_base and port_letter:
                            start_split_ports.append(port_alias)
                        if port_base == end_base and port_letter:
                            end_split_ports.append(port_alias)

                    # Sort by letter to ensure consistent ordering (a, b, c, d...)
                    start_split_ports.sort(key=lambda x: get_alias_letter(x) or '')
                    end_split_ports.sort(key=lambda x: get_alias_letter(x) or '')

                    # Create connections for all matching split ports
                    # Match ports by their position in the sorted list (a->a, b->b, etc.)
                    for i, start_sp in enumerate(start_split_ports):
                        if i < len(end_split_ports):
                            end_sp = end_split_ports[i]
                            # Create connection key
                            new_conn_key = ('dut', start_sp, 'dut', end_sp)

                            # Skip if this is the original connection or already exists
                            if new_conn_key not in seen_connections:
                                expanded_connections.append({
                                    'start_device': 'dut',
                                    'start_port': start_sp,
                                    'end_device': 'dut',
                                    'end_port': end_sp
                                })
                                seen_connections.add(new_conn_key)

    # Initialize alias counter for loopback numbering
    alias_counter = defaultdict(int)
    connection_map = {}
    # Track loopback pairs to assign same lb_number to both sides
    loopback_pairs = {}

    for conn in expanded_connections:
        start_dev = conn['start_device']
        start_port = conn['start_port'].strip().replace('ept', 'etp')
        end_dev = conn['end_device'].strip()
        end_port = conn['end_port'].strip().replace('ept', 'etp')

        # Map host port aliases to actual port names
        start_port_actual = start_port
        end_port_actual = end_port

        if start_dev in device_map and device_map[start_dev]['type'] == 'host':
            mapped = host_port_alias_map.get((start_dev, start_port))
            if mapped:
                start_port_actual = mapped

        if end_dev in device_map and device_map[end_dev]['type'] == 'host':
            mapped = host_port_alias_map.get((end_dev, end_port))
            if mapped:
                end_port_actual = mapped

        # Build descriptions
        start_alias = device_map.get(start_dev, {}).get('alias', start_dev)
        end_alias = device_map.get(end_dev, {}).get('alias', end_dev)

        # Description format based on connection type
        if start_dev == 'dut' and end_dev != 'dut':
            # DUT to host: dut-ha-1 (number comes from host port alias in CSV, e.g., ha-1 -> 1)
            # Use original CSV port alias (end_port) to extract port number
            host_port_num = end_port.split('-')[-1] if '-' in end_port else '1'
            desc_start = f"{start_alias}-{end_alias}-{host_port_num}"
            # Host to DUT: ha-dut-1 (number comes from host port alias in CSV)
            # Use original CSV port alias (end_port) to extract port number
            desc_end = f"{end_alias}-{start_alias}-{host_port_num}"
        elif end_dev == 'dut' and start_dev != 'dut':
            # Host to DUT: ha-dut-1 (number comes from host port alias in CSV, e.g., ha-1 -> 1)
            # Use original CSV port alias (start_port) to extract port number
            host_port_num = start_port.split('-')[-1] if '-' in start_port else '1'
            desc_start = f"{start_alias}-{end_alias}-{host_port_num}"
            # DUT to host: dut-ha-1 (number comes from host port alias in CSV)
            desc_end = f"{end_alias}-{start_alias}-{host_port_num}"
        else:
            # DUT to DUT connection (loopback)
            # Get port info from device_ports
            start_port_info = None
            end_port_info = None

            for port in device_ports.get(start_dev, []):
                if port['id'] == start_port_actual:
                    start_port_info = port
                    break

            for port in device_ports.get(end_dev, []):
                if port['id'] == end_port_actual:
                    end_port_info = port
                    break

            # Skip if ports not found in device_ports
            if not start_port_info or not end_port_info:
                continue

            # Check if this is a split loopback connectivity
            start_is_split = start_port_info.get('is_split', False)
            end_is_split = end_port_info.get('is_split', False)
            is_split_loopback = start_is_split and end_is_split

            # Create a unique key for this loopback pair (sorted to handle both directions)
            pair_key = tuple(sorted([(start_dev, start_port_actual), (end_dev, end_port_actual)]))

            if is_split_loopback:
                # Split loopback: format "{alias}-lb{lb_number}-splt{split_number}-p{lb_port_num}-{port_split_num}"
                split_number = start_port_info.get('split_num') or end_port_info.get('split_num')
                port_split_num_start = start_port_info.get('port_split_number')
                port_split_num_end = end_port_info.get('port_split_number')

                # Check if we've already assigned lb_number to this pair
                if pair_key in loopback_pairs:
                    lb_number = loopback_pairs[pair_key]
                else:
                    # Use counter - check if reverse connection already processed
                    reverse_key = tuple(sorted([(end_dev, end_port_actual), (start_dev, start_port_actual)]))
                    if reverse_key in loopback_pairs:
                        lb_number = loopback_pairs[reverse_key]
                    else:
                        # Check if neighbor port already has a description with lb_number
                        neighbor_desc = connection_map.get((end_dev, end_port_actual), {}).get('description', '')
                        if neighbor_desc:
                            pattern = f"{start_alias}-lb(\\d+)-splt{split_number}"
                            match = re.search(pattern, neighbor_desc, re.IGNORECASE)
                            if match:
                                lb_number = match.group(1)
                            else:
                                # Increment counter for this split loopback type
                                # Use template matching topology_manager: "{alias}-lb-splt{split_number}-{port_split_num}"
                                loopback_alias_template = f"{start_alias}-lb-splt{split_number}-{port_split_num_start}"
                                alias_counter[loopback_alias_template] += 1
                                lb_number = str(alias_counter[loopback_alias_template])
                        else:
                            # Increment counter for this split loopback type
                            loopback_alias_template = f"{start_alias}-lb-splt{split_number}-{port_split_num_start}"
                            alias_counter[loopback_alias_template] += 1
                            lb_number = str(alias_counter[loopback_alias_template])
                    loopback_pairs[pair_key] = lb_number

                # Get loopback port number (1 or 2)
                lb_port_num = get_loopback_port_number(start_port_info, end_port_info) or 1

                desc_start = f"{start_alias}-lb{lb_number}-splt{split_number}-p{lb_port_num}-{port_split_num_start}"
                # For end port, determine lb_port_num (opposite side)
                lb_port_num_end = 2 if lb_port_num == 1 else 1
                desc_end = f"{end_alias}-lb{lb_number}-splt{split_number}-p{lb_port_num_end}-{port_split_num_end}"
            else:
                # Regular loopback: format "{alias}-lb{lb_number}-{lb_port_num}"
                # Check if we've already assigned lb_number to this pair
                if pair_key in loopback_pairs:
                    lb_number = loopback_pairs[pair_key]
                else:
                    # Use counter - check if reverse connection already processed
                    reverse_key = tuple(sorted([(end_dev, end_port_actual), (start_dev, start_port_actual)]))
                    if reverse_key in loopback_pairs:
                        lb_number = loopback_pairs[reverse_key]
                    else:
                        # Check if neighbor port already has a description with lb_number
                        neighbor_desc = connection_map.get((end_dev, end_port_actual), {}).get('description', '')
                        if neighbor_desc:
                            pattern = f"{start_alias}-lb(\\d+)"
                            match = re.search(pattern, neighbor_desc, re.IGNORECASE)
                            if match:
                                lb_number = match.group(1)
                            else:
                                # Increment counter
                                loopback_alias_template = f"{start_alias}-lb"
                                alias_counter[loopback_alias_template] += 1
                                lb_number = str(alias_counter[loopback_alias_template])
                        else:
                            # Increment counter
                            loopback_alias_template = f"{start_alias}-lb"
                            alias_counter[loopback_alias_template] += 1
                            lb_number = str(alias_counter[loopback_alias_template])
                    loopback_pairs[pair_key] = lb_number

                # Get loopback port number (1 or 2)
                lb_port_num = get_loopback_port_number(start_port_info, end_port_info) or 1

                desc_start = f"{start_alias}-lb{lb_number}-{lb_port_num}"
                # For end port, determine lb_port_num (opposite side)
                lb_port_num_end = 2 if lb_port_num == 1 else 1
                desc_end = f"{end_alias}-lb{lb_number}-{lb_port_num_end}"

        # Store connection info
        connection_map[(start_dev, start_port_actual)] = {
            'description': desc_start,
            'connected_to': (end_dev, end_port_actual)
        }
        connection_map[(end_dev, end_port_actual)] = {
            'description': desc_end,
            'connected_to': (start_dev, start_port_actual)
        }

    # Update port descriptions
    for dev_alias, ports in device_ports.items():
        for port in ports:
            conn_key = (dev_alias, port['id'])
            if conn_key in connection_map:
                port['description'] = connection_map[conn_key]['description']

    return device_ports, connection_map


def generate_switch_xml(switch_info, ports, output_dir):
    """Generate XML file for a switch."""
    hostname = switch_info['hostname']

    # Get sub_type and switch_type from switch_info, with fallback to hostname-based detection
    sub_type = switch_info.get('sub_type', '')
    switch_type = switch_info.get('switch_type', '')

    # Fallback: Extract system type from hostname if not provided
    if not sub_type:
        if 'leopard' in hostname.lower():
            sub_type = 'leopard'
        elif 'tigris' in hostname.lower():
            sub_type = 'tigris'
        elif 'panther' in hostname.lower():
            sub_type = 'panther'
        else:
            sub_type = 'leopard'  # Default

    # Fallback: Default switch type if not provided
    if not switch_type:
        switch_type = 'ACS-MSN4700'  # Default

    xml_content = f"""<?xml version="1.0" ?>

    <INTERCONNECT>
        <TYPE>MLNX_SWITCH</TYPE>
        <SUB_TYPE>{sub_type}</SUB_TYPE>
        <SWITCH_TYPE>{switch_type}</SWITCH_TYPE>
        <NUM_PORTS>32</NUM_PORTS>
        <IS_DUT>True</IS_DUT>
        <ACT_AS>SWITCH</ACT_AS>
        <SWITCH_NICKNAME>{hostname}</SWITCH_NICKNAME>
        <DESCRIPTION>{switch_info['alias']}</DESCRIPTION>
        <REBOOT_IN_POST_CHECKER>yes</REBOOT_IN_POST_CHECKER>

        <CONNECTIONS>
            <CONNECTION CONN_TYPE="SSH">
                <CLI_TYPE>SHELL</CLI_TYPE>
                <IP>{switch_info['ip']}</IP>
                <MAC>{switch_info['mac']}</MAC>
            </CONNECTION>
        </CONNECTIONS>

        <USERS>
            <USER>
                <TYPE>CLI</TYPE>
                <USERNAME>{switch_info['username']}</USERNAME>
                <PASSWORD>{switch_info['password']}</PASSWORD>
            </USER>
        </USERS>

"""

    # Add ports
    for port in ports:
        xml_content += f"""<PORTS name="{port['id']}">
            <PORT>
                <IF>{port['if']}</IF>
                <DESCRIPTION>{port['description']}</DESCRIPTION>
            </PORT>
        </PORTS>
"""

    # Add active ports
    for port in ports:
        xml_content += f"""<ACTIVE_PORTS_IDS>{port['id']}</ACTIVE_PORTS_IDS>
"""

    xml_content += "\n</INTERCONNECT>\n"

    xml_file = os.path.join(output_dir, f"{hostname}.xml")
    with open(xml_file, 'w') as f:
        f.write(xml_content)

    return xml_file


def generate_host_xml(host_info, ports, output_dir):
    """Generate XML file for a host."""
    hostname = host_info['hostname']

    xml_content = f"""<HOST>
        <TYPE>Linux</TYPE>
        <IS_ROUTER>False</IS_ROUTER>
        <DESCRIPTION>{host_info['alias']}</DESCRIPTION>
        <CONNECTIONS>
            <CONNECTION CONN_TYPE="SSH">
                <CLI_TYPE>SHELL</CLI_TYPE>
                <IP>{host_info['ip']}</IP>
                <MAC>{host_info['mac']}</MAC>
            </CONNECTION>
        </CONNECTIONS>

        <USERS>
            <USER>
                <USERNAME>{host_info['username']}</USERNAME>
                <PASSWORD>{host_info['password']}</PASSWORD>
            </USER>
        </USERS>

"""

    # Add ports if any
    for port in ports:
        xml_content += f"""<PORTS name="{port['id']}">
                <PORT>
                    <MAC>{port['mac']}</MAC>
                    <IF>{port['if']}</IF>
                    <DESCRIPTION>{port['description']}</DESCRIPTION>

                    <TYPE>ETH</TYPE>
                </PORT>
            </PORTS>
"""

    # Add active ports
    for port in ports:
        xml_content += f"""<ACTIVE_PORTS_IDS>{port['id']}</ACTIVE_PORTS_IDS>
"""

    xml_content += "</HOST>\n"

    xml_file = os.path.join(output_dir, f"{hostname}.xml")
    with open(xml_file, 'w') as f:
        f.write(xml_content)

    return xml_file


def generate_topology_xml(setup_config, device_map, device_ports, connections, output_dir):
    """Generate the main topology.xml file."""

    xml_content = """<?xml version="1.0" ?>

    <TOPOLOGY>
"""

    # Add switches
    for switch in setup_config.get('switches', []):
        hostname = switch['hostname']
        xml_content += f"""<INTERCONNECTS xmlns:xi="http://www.w3.org/2001/XInclude" name="{hostname}">
            <xi:include href="{hostname}.xml"/>
        </INTERCONNECTS>
"""

    # Add hosts
    for host in setup_config.get('hosts', []):
        hostname = host['hostname']
        xml_content += f"""<HOSTS xmlns:xi="http://www.w3.org/2001/XInclude" name="{hostname}">
            <xi:include href="{hostname}.xml"/>
        </HOSTS>
"""

    # Add other entities
    for entity in setup_config.get('other_entities', []):
        hostname = entity['hostname']
        xml_content += f"""<HOSTS xmlns:xi="http://www.w3.org/2001/XInclude" name="{hostname}">
            <xi:include href="{hostname}.xml"/>
        </HOSTS>
"""

    # Build connectivity links
    host_port_alias_map = {}
    for alias, device_info in device_map.items():
        if device_info['type'] == 'host':
            for key, value in device_info.items():
                if isinstance(value, str) and (key.startswith(alias + '-') or
                    (key.startswith('h') and '-' in key and key.endswith(('1', '2')))):
                    host_port_alias_map[(alias, key)] = value
                    # Also map with device prefix correction (e.g., hb-1 for ha device)
                    if key.startswith(alias + '-'):
                        # Create alternative mapping
                        alt_prefix = 'hb' if alias == 'ha' else 'ha'
                        alt_key = key.replace(alias, alt_prefix, 1)
                        host_port_alias_map[(alias, alt_key)] = value

    connectivity_links = []
    for conn in connections:
        start_dev = conn['start_device']
        start_port = conn['start_port'].strip().replace('ept', 'etp')
        end_dev = conn['end_device'].strip()
        end_port = conn['end_port'].strip()

        # Fix CSV errors: if port alias doesn't match device, find correct device
        if end_dev in device_map and device_map[end_dev]['type'] == 'host':
            # Check if port alias matches device's port aliases
            # Port aliases are keys like 'ha-1', 'ha-2', 'hb-1', 'hb-2'
            port_found = end_port in device_map[end_dev]

            # If not found, try to find which device has this port alias
            if not port_found:
                for alias, device_info in device_map.items():
                    if device_info['type'] == 'host' and alias != end_dev:
                        # Check if this device has the port alias as a key
                        if end_port in device_info:
                            # Found the correct device
                            end_dev = alias
                            break

        start_hostname = device_map.get(start_dev, {}).get('hostname', start_dev)
        end_hostname = device_map.get(end_dev, {}).get('hostname', end_dev)

        # Map port aliases to actual port IDs
        start_port_actual = start_port
        end_port_actual = end_port

        if start_dev in device_map and device_map[start_dev]['type'] == 'host':
            # Try exact match first
            mapped = host_port_alias_map.get((start_dev, start_port))
            if not mapped:
                # Try with device prefix correction
                mapped = host_port_alias_map.get((start_dev, start_port))
            if mapped:
                start_port_actual = mapped
            else:
                # Try to find port in device_ports
                ports = device_ports.get(start_dev, [])
                for port in ports:
                    if port['id'] == start_port or port['id'].endswith(start_port.split('-')[-1]):
                        start_port_actual = port['id']
                        break

        if end_dev in device_map and device_map[end_dev]['type'] == 'host':
            # Try exact match first
            mapped = host_port_alias_map.get((end_dev, end_port))
            if not mapped:
                # Try with device prefix correction
                mapped = host_port_alias_map.get((end_dev, end_port))
            if mapped:
                end_port_actual = mapped
            else:
                # Try to find port in device_ports
                ports = device_ports.get(end_dev, [])
                for port in ports:
                    if port['id'] == end_port or port['id'].endswith(end_port.split('-')[-1]):
                        end_port_actual = port['id']
                        break

        link1 = f"{start_hostname}-{start_port_actual}"
        link2 = f"{end_hostname}-{end_port_actual}"

        connectivity_links.append((link1, link2))

    # Add connectivity sections
    for link1, link2 in connectivity_links:
        xml_content += f"""<CONNECTIVITY>
            <CONNECTION>
                <LINK>{link1}</LINK>
                <LINK>{link2}</LINK>
            </CONNECTION>
        </CONNECTIVITY>
"""

    xml_content += "</TOPOLOGY>\n"

    xml_file = os.path.join(output_dir, 'topology_all.xml')
    with open(xml_file, 'w') as f:
        f.write(xml_content)

    return xml_file


def generate_json_file(setup_config, device_map, device_ports, connections, output_dir, setup_name):
    """Generate JSON file with device info and links."""

    # Build host port alias mapping
    host_port_alias_map = {}
    for alias, device_info in device_map.items():
        if device_info['type'] == 'host':
            for key, value in device_info.items():
                if isinstance(value, str) and (key.startswith(alias + '-') or
                    (key.startswith('h') and '-' in key and key.endswith(('1', '2')))):
                    host_port_alias_map[(alias, key)] = value

    json_data = {
        'switches': {},
        'hosts': {}
    }

    # Process switches
    for switch in setup_config.get('switches', []):
        switch_alias = switch['alias']
        switch_info = device_map[switch_alias]
        ip = switch_info['ip']
        hostname = switch_info['hostname']

        links = {}
        for port in device_ports.get(switch_alias, []):
            # Only include ports that have connections (non-empty descriptions)
            description = port.get('description', '').strip()
            if description:
                link_key = f"{ip} - {switch_info['hostname']}-{port['id']}"
                links[link_key] = description

        # Build custom_params dictionary
        custom_params = {}
        mac = switch_info.get('mac', '')
        if mac:
            custom_params['mac address 1'] = mac
        devdescription = switch_info.get('devdescription', '')
        if devdescription:
            custom_params['devdescription'] = devdescription
        # Pass through connection/CLI type when provided in setup config
        conn_type = switch.get('CONN_TYPE')
        if conn_type:
            custom_params['CONN_TYPE'] = conn_type
        cli_type = switch.get('CLI_TYPE')
        if cli_type:
            custom_params['CLI_TYPE'] = cli_type

        json_data['switches'][hostname] = {
            'ip': ip,
            'alias': switch_alias,
            'links': links
        }

        # Add custom_params if it has any values
        if custom_params:
            json_data['switches'][hostname]['custom_params'] = custom_params

    # Process hosts
    for host in setup_config.get('hosts', []):
        host_alias = host['alias']
        host_info = device_map[host_alias]
        hostname = host_info['hostname']

        links = {}
        for port in device_ports.get(host_alias, []):
            # Only include ports that have connections (non-empty descriptions)
            description = port.get('description', '').strip()
            if description:
                link_key = f"{host_info['ip']} - {hostname}-{port['id']}"
                links[link_key] = description

        # Build custom_params dictionary
        custom_params = {}
        mac = host_info.get('mac', '')
        if mac:
            custom_params['mac address 1'] = mac

        json_data['hosts'][hostname] = {
            'ip': host_info['ip'],
            'alias': host_alias,
            'links': links
        }

        # Add custom_params if it has any values
        if custom_params:
            json_data['hosts'][hostname]['custom_params'] = custom_params

    # Process other entities
    for entity in setup_config.get('other_entities', []):
        entity_id = entity.get('entity_id', '')
        if entity_id:
            host_info = device_map[entity_id]
            hostname = host_info['hostname']

            # Build custom_params dictionary
            custom_params = {}
            mac = host_info.get('mac', '')
            if mac:
                custom_params['mac address 1'] = mac

            json_data['hosts'][hostname] = {
                'ip': host_info['ip'],
                'alias': host_info['alias'],
                'links': {}
            }

            # Add custom_params if it has any values
            if custom_params:
                json_data['hosts'][hostname]['custom_params'] = custom_params

    json_file = os.path.join(output_dir, f"{setup_name}.json")
    with open(json_file, 'w') as f:
        json.dump(json_data, f, indent=1)

    return json_file


def get_setup_name_from_dut(device_map):
    """Generate setup name from DUT information."""
    dut_info = None
    for device_alias, device_info in device_map.items():
        if device_info['type'] == 'switch':
            dut_info = device_info
            break

    if not dut_info:
        raise ValueError("No switch (DUT) found in setup configuration")

    hostname = dut_info['hostname']

    # Get sub_type from device_map, with fallback to hostname-based detection
    system_type = dut_info.get('sub_type', '')

    if not system_type:
        # Fallback: Extract system type from hostname
        hostname_lower = hostname.lower()
        if 'leopard' in hostname_lower:
            system_type = 'leopard'
        elif 'tigris' in hostname_lower:
            system_type = 'tigris'
        elif 'panther' in hostname_lower:
            system_type = 'panther'
        else:
            system_type = 'leopard'  # Default

    setup_name = f"sonic_{system_type}_{hostname}"
    return setup_name


def parse_arguments():
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description='Generate XML and JSON topology files from configuration files'
    )
    parser.add_argument(
        '--setup_conf_yml',
        required=True,
        help='Path to setup configuration YAML file'
    )
    parser.add_argument(
        '--port_connection_csv',
        required=False,
        default=None,
        help='Path to port connection CSV file (optional). If omitted, no CONNECTIVITY/PORT/ACTIVE_PORTS_IDS will be generated.'
    )
    parser.add_argument(
        '--port_config_ini',
        required=False,
        default=None,
        help='Path to port config INI file (optional). If omitted, no CONNECTIVITY/PORT/ACTIVE_PORTS_IDS will be generated.'
    )
    parser.add_argument(
        '--output_dir',
        default='/auto/sw_regression/system/SONIC/MARS/conf/topo',
        help='Output directory base path'
    )
    parser.add_argument(
        '-s', '--setup_name',
        dest='setup_name',
        default=None,
        help='Specify setup name if setup name should be named differently than '
             'sonic_<switch_type>_<switch_hostname>'
    )
    parser.add_argument(
        '-g', '--setup_group',
        dest='setup_group',
        default='SONiC_Canonical',
        help='Specify setup group, if group is different than SONiC_Canonical'
    )

    return parser.parse_args()


def generate_topology_files(port_connection_csv, port_config_ini, setup_config, device_map, output_dir, setup_name):
    """
    Generate all topology XML and JSON files.

    Args:
        port_connection_csv: Path to port connection CSV file
        port_config_ini: Path to port config INI file
        setup_config: Parsed setup configuration dictionary
        device_map: Device map dictionary
        output_dir: Output directory path
        setup_name: Setup name string
    """
    include_ports_and_connectivity = bool(port_connection_csv and port_config_ini)

    if include_ports_and_connectivity:
        print("Parsing port connection CSV file...")
        connections = parse_port_connection_csv(port_connection_csv)
        print(f"Found {len(connections)} connections")

        print("Parsing port config INI file...")
        port_config = parse_port_config_ini(port_config_ini)
        print(f"Found {len(port_config)} port configurations")

        print("Building port mappings...")
        device_ports, connection_map = build_port_mappings(setup_config, port_config, connections, device_map)
    else:
        print("Port inputs not provided; skipping CONNECTIVITY/PORT/ACTIVE_PORTS_IDS generation.")
        connections = []
        port_config = {}
        device_ports = {}
        connection_map = {}

    # Generate XML files for switches
    print("Generating switch XML files...")
    for switch in setup_config.get('switches', []):
        switch_alias = switch['alias']
        switch_info = device_map[switch_alias]
        ports = device_ports.get(switch_alias, [])
        xml_file = generate_switch_xml(switch_info, ports, output_dir)
        print(f"Generated: {xml_file}")

    # Generate XML files for hosts
    print("Generating host XML files...")
    for host in setup_config.get('hosts', []):
        host_alias = host['alias']
        host_info = device_map[host_alias]
        ports = device_ports.get(host_alias, [])
        xml_file = generate_host_xml(host_info, ports, output_dir)
        print(f"Generated: {xml_file}")

    # Generate XML files for other entities
    print("Generating other entity XML files...")
    for entity in setup_config.get('other_entities', []):
        entity_id = entity.get('entity_id', '')
        if entity_id and entity_id in device_map:
            entity_info = device_map[entity_id]
            ports = device_ports.get(entity_id, [])
            xml_file = generate_host_xml(entity_info, ports, output_dir)
            print(f"Generated: {xml_file}")

    # Generate topology.xml
    print("Generating topology.xml...")
    topology_xml = generate_topology_xml(setup_config, device_map, device_ports, connections, output_dir)
    print(f"Generated: {topology_xml}")

    # Generate JSON file
    print("Generating JSON file...")
    json_file = generate_json_file(setup_config, device_map, device_ports, connections, output_dir, setup_name)
    print(f"Generated: {json_file}")

    print("\nAll files generated successfully!")


def process_setup_and_generate_topology(
        setup_conf_yml, output_dir_base, port_connection_csv=None,
        port_config_ini=None, setup_name=None, setup_group='SONiC_Canonical'):
    """
    Process setup configuration and generate topology files.

    Args:
        setup_conf_yml: Path to setup configuration YAML file
        output_dir_base: Base output directory path
        port_connection_csv: Path to port connection CSV file
        port_config_ini: Path to port config INI file
        setup_name: Optional setup name (if None, will be generated from DUT)
        setup_group: Setup group name (default: 'SONiC_Canonical')
    """
    print("Parsing setup configuration YAML file...")
    setup_config = parse_setup_conf_yml(setup_conf_yml)
    device_map = build_device_map(setup_config)

    # Use provided setup_name or generate from DUT
    if not setup_name:
        setup_name = get_setup_name_from_dut(device_map)
    print(f"Setup name: {setup_name}")

    # Use provided setup_group or default
    print(f"Setup group: {setup_group}")

    output_dir = os.path.join(output_dir_base, setup_name)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    # Set output directory permissions to 777
    os.chmod(output_dir, 0o777)

    # Generate all topology files
    generate_topology_files(
        port_connection_csv, port_config_ini, setup_config, device_map,
        output_dir, setup_name)
    return setup_name, output_dir


def main():
    args = parse_arguments()

    # Use paths as provided (assumed to be absolute or relative to current working directory)
    setup_conf_yml = args.setup_conf_yml
    port_connection_csv = args.port_connection_csv
    port_config_ini = args.port_config_ini
    output_dir_base = args.output_dir

    process_setup_and_generate_topology(
        setup_conf_yml=setup_conf_yml,
        port_connection_csv=port_connection_csv,
        port_config_ini=port_config_ini,
        output_dir_base=output_dir_base,
        setup_name=args.setup_name,
        setup_group=args.setup_group
    )


if __name__ == '__main__':
    main()


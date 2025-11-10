#!/usr/bin/env python3
import argparse
import json
import re
import sys
import os
from typing import Dict, Any, List, Tuple
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_constants.constants_nvos import IbConsts
from ngts.tools.sysdumps import copy_dump_file


AGG_LABEL_RE = re.compile(r'^\s*APort\s+(?P<aport>\d+)\s+Aggregated label:\s+(?P<label>\S+)\s*$')
PLANE_LINE_RE = re.compile(
    r'^\s*(?P<plane>\S+):\s+(?P<state>\S+)\s+PortGuid:\s+(?P<port_guid>\S+)\s+NodeGuid:\s+(?P<node_guid>\S+)\s+Port:\s+(?P<port_num>\d+),'
)
SYSTEM_LINE_RE = re.compile(r'^\s*SW\s+SystemGUID:\s*(?P<guid>\S+)\s+Description:\s*(?P<desc>.+?)\s*$')


def generate_connectivity_json(input_path: str, output_path: str) -> str:
    """
    Parse ibdiagnet textual output from input_path and write topology JSON to output_path.
    Returns the output_path.
    """
    if input_path == "-" or not input_path:
        content = sys.stdin.read()
    else:
        with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    lines = content.splitlines()
    topology = build_topology(lines)
    json_str = json.dumps(topology, indent=2, sort_keys=True)
    with open(output_path, "w", encoding="utf-8") as out_f:
        out_f.write(json_str)
    return output_path


def test_connectivity_update_json_file(engines, setup_name):
    """
        Test flow:
            1. run nv action run ib cmd "ibdiagnet --get_cable_info"
            2. run zcat /host/ibdiagnet/ibdiagnet2_output.tgz and same output in .txt file
            3. run python3 ngts/tests_nvos/general/connectivity_json_generator.py -i /host/ibdiagnet/ibdiagnet2_output.txt -o /host/ibdiagnet/connectivity.json
            4. verify connectivity.json is not empty
            5. verify no Errors in ibdiagnet output
        """
    with allure.step('Run nv action run ib cmd "ibdiagnet --get_cable_info"'):
        ib = Ib(None)
        ib.ibdiagnet.action_run(command=IbConsts.IBDIAGNET_COMMAND, option=IbConsts.IBDIAGNET_CABLE_INFO, expected_str=IbConsts.IBDIAGNET_EXPECTED_MESSAGE)

    with allure.step('Run read ibdiagnet2_output.txt file'):
        engines.dut.run_cmd('sudo mkdir -p /host/ibdiagnet')
        engines.dut.run_cmd('zcat {path} > ibdiagnet2_output.txt'.format(
            path=IbConsts.IBDIAGNET_ZIPPED_FOLDER_PATH + '/' + IbConsts.IBDIAGNET_FILE_NAME))

    with allure.step('Generate connectivity.json file'):
        # Read remote txt, generate JSON locally, then write back to DUT
        txt = engines.dut.run_cmd('cat ibdiagnet2_output.txt')
        json_str = json.dumps(build_topology(txt.splitlines()), indent=2, sort_keys=True)
        engines.dut.run_cmd("cat > /home/admin/{name}.json << 'EOF'\n{data}\nEOF".format(name=setup_name, data=json_str))
        assert 'OK' in engines.dut.run_cmd('test -s /home/admin/{name}.json && echo OK'.format(name=setup_name)), "connectivity json should be created and non-empty"

    with allure.step("upload connectivity json file to the server"):
        dest_dir = '/auto/sw_system_project/NVOS_INFRA/verification_files/connectivity_files'
        os.makedirs(dest_dir, exist_ok=True)
        dest_file = os.path.join(dest_dir, f'{setup_name}.json')
        copy_dump_file(engines.dut, source_file=f'/home/admin/{setup_name}.json', dest_file=dest_file)


def parse_aggregated_ports(lines: List[str]) -> Dict[str, Any]:
    """
    Parses the 'APort <N> Aggregated label: <agg>' section with per-plane lines.
    Returns a dict mapping aggregated label to:
      {
        "aport": <int>,
        "planes": {
          "<plane>": {"state": <str>, "port_guid": <str>, "node_guid": <str>, "port": <int>}
        }
      }
    """
    ports: Dict[str, Any] = {}
    current_label: str = ""
    current_aport: int = -1

    for line in lines:
        agg_match = AGG_LABEL_RE.match(line)
        if agg_match:
            current_label = agg_match.group("label")
            current_aport = int(agg_match.group("aport"))
            if current_label not in ports:
                ports[current_label] = {"aport": current_aport, "planes": {}}
            else:
                ports[current_label]["aport"] = current_aport
            continue

        if not current_label:
            continue

        plane_match = PLANE_LINE_RE.match(line)
        if plane_match:
            plane_name = plane_match.group("plane")
            ports[current_label]["planes"][plane_name] = {
                "state": plane_match.group("state"),
                "port_guid": plane_match.group("port_guid"),
                "node_guid": plane_match.group("node_guid"),
                "port": int(plane_match.group("port_num")),
            }
            continue

        # blank line or next section ends current aggregated block implicitly
    return ports


def _extract_neighbor_device(desc_quoted: str) -> str:
    """
    Given a quoted neighbor description like: "MF0;mtvr-croc-19-mgmt2:Q3200_RA/U1"
    extract the device name 'mtvr-croc-19-mgmt2'.
    """
    # Strip surrounding quotes if present
    desc = desc_quoted.strip()
    if desc.startswith('"') and desc.endswith('"') and len(desc) >= 2:
        desc = desc[1:-1]
    # Prefer: after ';' until next ':' (or end)
    # Examples:
    #   MF0;mtvr-croc-19-mgmt2:Q3200_RA/U1  -> mtvr-croc-19-mgmt2
    #   MF0;mtvr-croc-19-mgmt2              -> mtvr-croc-19-mgmt2
    #   mtvr-croc-19-mgmt2                  -> mtvr-croc-19-mgmt2
    if ';' in desc:
        desc = desc.split(';', 1)[1]
    if ':' in desc:
        desc = desc.split(':', 1)[0]
    return desc.strip()


def parse_system_and_connections(lines: List[str]) -> Tuple[Dict[str, Any], int]:
    """
    Parses the 'SW SystemGUID: <guid> Description: <desc>' section followed by
    the connection table starting with 'Label      : # ...'.
    Returns:
      - system_info: {"system_guid": <str>, "description": <str>, "connections": {label: {...}}}
      - index where parsing ended (for potential further parsing)
    """
    system_info: Dict[str, Any] = {"system_guid": "", "description": "", "connections": {}}
    i = 0
    n = len(lines)

    # Find system line
    while i < n:
        m = SYSTEM_LINE_RE.match(lines[i])
        if m:
            system_info["system_guid"] = m.group("guid")
            system_info["description"] = m.group("desc")
            i += 1
            break
        i += 1

    # Skip until header line starting with 'Label'
    while i < n and not lines[i].lstrip().startswith("Label"):
        i += 1
    # skip header
    if i < n and lines[i].lstrip().startswith("Label"):
        i += 1

    # Parse rows until blank line or next 'SW SystemGUID' or EOF
    while i < n:
        line = lines[i].rstrip("\n")
        if not line.strip():
            break
        if SYSTEM_LINE_RE.match(line):
            # Start of a new system block
            break
        # Extract the trailing quoted neighbor description (if present) to avoid colon confusion
        desc_match = re.search(r':\s*"([^"]*)"\s*$', line)
        neighbor_desc_clean = ""
        pre = line
        if desc_match:
            neighbor_desc_raw = desc_match.group(1)
            neighbor_desc_clean = _extract_neighbor_device(neighbor_desc_raw)
            pre = line[:desc_match.start()]
        # Now split the prefix by ':' safely
        parts = [p.strip() for p in pre.split(':')]
        if len(parts) >= 13:
            label = parts[0]
            # parts indices based on the sample format
            sta = parts[3] if len(parts) > 3 else ""
            phys = parts[4] if len(parts) > 4 else ""
            neighbor_guid = parts[10] if len(parts) > 10 else ""
            neighbor_label = parts[11] if len(parts) > 11 else ""
            system_info["connections"][label] = {
                "state": sta,
                "physical_state": phys,
                "neighbor_guid": neighbor_guid,
                "connected_to": neighbor_label,
                "neighbor_description": neighbor_desc_clean,
                "neighbor_device": neighbor_desc_clean or "",
                # loopback will be set by caller (needs local description)
            }
        i += 1

    return system_info, i


def build_topology(lines: List[str]) -> Dict[str, Any]:
    """
    Build the final JSON structure from ibdiagnet output lines.
    """
    # First, parse aggregated ports + planes
    agg_ports = parse_aggregated_ports(lines)

    # Then, parse system + connections (may be multiple systems; take first that matches our planes' labels)
    # We'll iterate through the file and gather all system blocks, then apply connections for labels we have.
    systems: List[Dict[str, Any]] = []
    idx = 0
    n = len(lines)
    while idx < n:
        sys_info, next_idx = parse_system_and_connections(lines[idx:])
        if sys_info.get("system_guid"):
            systems.append(sys_info)
            idx += next_idx
        else:
            idx += 1

    # Choose system whose connections reference our labels; fallback to first
    chosen_system = {}
    for s in systems:
        if any(label in agg_ports for label in s.get("connections", {}).keys()):
            chosen_system = s
            break
    if not chosen_system and systems:
        chosen_system = systems[0]

    description = chosen_system.get("description", "")
    connections = chosen_system.get("connections", {})

    # Merge connections into agg_ports and compute loopback
    ports_out: Dict[str, Any] = {}
    for label, data in agg_ports.items():
        entry = {
            "aport": data.get("aport"),
            "planes": data.get("planes", {}),
        }
        if label in connections:
            conn = connections[label]
            neighbor_device = conn.get("neighbor_device", "")
            entry.update({
                "connected_to": conn.get("connected_to"),
                "neighbor_guid": conn.get("neighbor_guid"),
                # Store the cleaned device name as neighbor_description
                "neighbor_description": neighbor_device,
                "state": conn.get("state"),
                "physical_state": conn.get("physical_state"),
            })
            entry["loopback"] = (neighbor_device == description) if description else False
        else:
            entry["loopback"] = False
        ports_out[label] = entry

    result = {
        "system_guid": chosen_system.get("system_guid", ""),
        "description": description,
        "ports": ports_out,
    }
    return result

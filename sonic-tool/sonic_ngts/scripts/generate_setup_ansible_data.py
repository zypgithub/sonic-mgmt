#!/usr/bin/env python3
"""
Script to generate DUT setup files for sonic-mgmt.

This script takes DUT configuration parameters and generates the necessary
configuration files including:
- graph_groups.yml entry
- sonic_{dut_name}_devices.csv
- sonic_{dut_name}_pdu_links.csv
- inventory entries
- lab entry
- testbed.yaml entry
"""

import argparse
import csv
import re
import sys
import yaml
import subprocess
from pathlib import Path


class DUTSetupGenerator:
    def __init__(self, sonic_mgmt_path):
        """Initialize the generator with paths to sonic-mgmt files."""
        self.sonic_mgmt_path = Path(sonic_mgmt_path)
        self.ansible_path = self.sonic_mgmt_path / "ansible"
        self.files_path = self.ansible_path / "files"

    @staticmethod
    def _normalize_str(value):
        """Normalize strings by stripping leading/trailing whitespace."""
        if value is None:
            return ""
        return str(value).strip()

    def _extract_pdu_entries_from_psus(self, psus):
        """
        Extract PDU inventory entries from PSU definitions.

        Returns list of dicts: [{'name': pdu_name, 'ip': ip, 'protocol': protocol}, ...]
        """
        pdu_entries = []
        seen = set()
        for psu_input in psus or []:
            pdu_name, _, _, pdu_info = self.parse_psu_input(psu_input)
            pdu_name = self._normalize_str(pdu_name)
            if not pdu_name:
                continue

            pdu_ip = ""
            protocol = "snmp"

            if pdu_info:
                pdu_ip = self._normalize_str(pdu_info.get("ip"))
                protocol = self._normalize_str(pdu_info.get("protocol")) or "snmp"
            else:
                # Best-effort: derive IP from pdu-<a>-<b>-<c>-<d>
                m = re.match(r"^pdu-(\d+)-(\d+)-(\d+)-(\d+)$", pdu_name)
                if m:
                    pdu_ip = ".".join(m.groups())

            if not pdu_ip:
                continue

            key = (pdu_name, pdu_ip, protocol)
            if key in seen:
                continue
            seen.add(key)
            pdu_entries.append({"name": pdu_name, "ip": pdu_ip, "protocol": protocol})

        return pdu_entries

    def _ensure_pdu_entries_in_inventory(self, content, pdu_entries):
        """
        Ensure each PDU in pdu_entries exists under [pdu] section.

        Returns (new_content, added_entries_list)
        """
        if not pdu_entries:
            return content, []

        # Ensure [pdu] section exists
        if re.search(r"^\[pdu\]\s*$", content, re.MULTILINE) is None:
            # Append section at the end
            if content and not content.endswith("\n"):
                content += "\n"
            content += "\n[pdu]\n"

        # Locate [pdu] section body
        pdu_pattern = r"(\[pdu\]\s*\n)(.*?)(?=\n\[|\Z)"
        match = re.search(pdu_pattern, content, re.DOTALL)
        if not match:
            return content, []

        section_header = match.group(1)
        section_body = match.group(2)

        existing_hosts = set()
        for line in section_body.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # host is the first token
            host = line.split()[0].strip()
            if host:
                existing_hosts.add(host)

        added = []
        new_lines = []
        for entry in pdu_entries:
            name = self._normalize_str(entry.get("name"))
            ip = self._normalize_str(entry.get("ip"))
            protocol = self._normalize_str(entry.get("protocol")) or "snmp"
            if not name or not ip:
                continue
            if name in existing_hosts:
                continue
            new_lines.append(f"{name} ansible_host={ip} protocol={protocol}\n")
            existing_hosts.add(name)
            added.append(name)

        if not new_lines:
            return content, []

        # Insert at end of [pdu] section body
        insert_pos = match.end(2)
        if section_body and not section_body.endswith("\n"):
            new_lines.insert(0, "\n")

        new_content = content[:insert_pos] + "".join(new_lines) + content[insert_pos:]
        return new_content, added

    def ssh_execute_command(self, host, username, password, command, timeout=30):
        """Execute command via SSH and return output"""
        try:
            # Use sshpass for password authentication
            ssh_cmd = [
                'sshpass', '-p', password,
                'ssh', '-o', 'StrictHostKeyChecking=no',
                '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'ConnectTimeout=10',
                f'{username}@{host}',
                command
            ]
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                print(f"  ⚠ SSH command failed: {result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            print(f"  ⚠ SSH command timed out after {timeout} seconds")
            return None
        except FileNotFoundError:
            # sshpass not available, try using pexpect
            print("  ⚠ sshpass not found, trying alternative SSH method...")
            return self._ssh_execute_pexpect(host, username, password, command, timeout)
        except Exception as e:
            print(f"  ⚠ SSH error: {e}")
            return None

    def _ssh_execute_pexpect(self, host, username, password, command, timeout=30):
        """Execute command via SSH using pexpect (fallback)"""
        try:
            import pexpect
            ssh_cmd = f'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null {username}@{host}'
            child = pexpect.spawn(ssh_cmd, timeout=timeout)
            child.expect(['password:', pexpect.EOF, pexpect.TIMEOUT])
            child.sendline(password)
            child.expect(['#', '$', pexpect.EOF, pexpect.TIMEOUT])
            child.sendline(command)
            child.expect(['#', '$', pexpect.EOF, pexpect.TIMEOUT])
            output = child.before.decode('utf-8', errors='ignore')
            child.close()
            return output
        except ImportError:
            print("  ⚠ pexpect not available. Cannot execute SSH commands.")
            return None
        except Exception as e:
            print(f"  ⚠ SSH pexpect error: {e}")
            return None

    def get_eeprom_info(self, dut_ip, username='admin', password='YourPaSsWoRd'):
        """Get EEPROM information from switch via SSH"""
        # Extract IP address
        ip_address = dut_ip.split('/')[0] if '/' in dut_ip else dut_ip

        print(f"  Connecting to {ip_address} to get EEPROM information...")

        # Execute show platform syseeprom
        syseeprom_output = self.ssh_execute_command(
            ip_address, username, password, 'show platform syseeprom'
        )

        if not syseeprom_output:
            print(f"  ⚠ Could not get syseeprom info from {ip_address}")
            return None

        # Parse syseeprom output
        eeprom_data = self._parse_syseeprom_output(syseeprom_output)

        # Execute show platform sum to get additional info if needed
        sum_output = self.ssh_execute_command(
            ip_address, username, password, 'show platform sum'
        )

        if sum_output:
            # Parse sum output for additional info if needed
            pass

        return eeprom_data

    def _parse_syseeprom_output(self, output):
        """Parse show platform syseeprom output"""
        # TLV mapping: Field name -> hex code
        tlv_mapping = {
            'Product Name': '0x21',
            'Part Number': '0x22',
            'Serial Number': '0x23',
            'Base MAC Address': '0x24',
            'Manufacture Date': '0x25',
            'Device Version': '0x26',
            'Platform Name': '0x28',
            'ONIE Version': '0x29',
            'MAC Addresses': '0x2a',
            'Manufacturer': '0x2b',
            'CRC-32': '0xfe'
        }

        parsed_data = {}

        # Parse lines - format: "Field Name    0xXX  Len Value"
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('---') or 'TLV Name' in line:
                continue

            # Match pattern: field name, hex code, length, value
            # Example: "Product Name          0x21  64 MSN4700"
            # Or: "Base MAC Address       0x24   6 1C:34:DA:27:6C:00"
            # Pattern: field name (may have spaces), hex code, length (number), value (rest of line)
            match = re.match(r'^([A-Za-z][^\t]+?)\s+(0x[0-9a-fA-F]+)\s+(\d+)\s+(.+)$', line)
            if match:
                field_name = match.group(1).strip()
                hex_code = match.group(2).strip().lower()
                length = match.group(3).strip()
                value = match.group(4).strip()

                # Map field name to hex code if available
                if field_name in tlv_mapping:
                    hex_code = tlv_mapping[field_name].lower()

                parsed_data[hex_code] = value
                parsed_data[field_name] = value

        # Extract specific fields
        base_mac = parsed_data.get('0x24') or parsed_data.get('Base MAC Address', '')
        serial = parsed_data.get('0x23') or parsed_data.get('Serial Number', '')
        model = parsed_data.get('0x22') or parsed_data.get('Part Number', '')
        product_name = parsed_data.get('0x21') or parsed_data.get('Product Name', '')

        # Build syseeprom_info dictionary
        syseeprom_info = {}
        for hex_code in ['0x21', '0x22', '0x23', '0x24', '0x25', '0x26', '0x28', '0x29', '0x2a', '0x2b', '0xfe']:
            if hex_code in parsed_data:
                value = parsed_data[hex_code]
                syseeprom_info[hex_code] = value

        return {
            'base_mac': base_mac,
            'serial': serial,
            'model': model,
            'product_name': product_name,
            'syseeprom_info': syseeprom_info
        }

    def parse_psu_input(self, psu_string):
        """
        Parse PSU input string.
        Supports two formats:
        1. Extended format: 'pdu-name,ip-address,manufacturer,type,protocol,port,psu-name'
        2. Simple format: 'pdu-name,port,psu-name' or 'pdu-name,port'
        Returns: (pdu_name, port, psu_name, pdu_info_dict)
        where pdu_info_dict contains: {'ip': ip, 'manufacturer': mfr, 'type': type, 'protocol': protocol}
        or None if not in extended format
        """
        parts = [p.strip() for p in psu_string.split(',')]

        # Check if it's extended format (has 5+ parts with IP address pattern)
        if len(parts) >= 5:
            # Try to detect if second part is an IP address (contains dots)
            if '.' in parts[1] and len(parts[1].split('.')) == 4:
                # Extended format: pdu-name,ip-address,manufacturer,type,protocol[,port,psu-name]
                pdu_name = parts[0]
                pdu_ip = parts[1]
                manufacturer = parts[2]
                pdu_type = parts[3]
                protocol = parts[4]
                port = parts[5] if len(parts) > 5 else None
                psu_name = parts[6] if len(parts) > 6 else None

                pdu_info = {
                    'ip': pdu_ip,
                    'manufacturer': manufacturer,
                    'type': pdu_type,
                    'protocol': protocol
                }
                return pdu_name, port, psu_name, pdu_info

        # Simple format: pdu-name,port[,psu-name]
        if len(parts) >= 2:
            pdu_name = parts[0]
            port = parts[1]
            psu_name = parts[2] if len(parts) > 2 else None
            return pdu_name, port, psu_name, None

        raise ValueError(f"Invalid PSU format: {psu_string}. Expected 'pdu-name,ip,manufacturer,type,protocol,port,psu-name' or 'pdu-name,port,psu-name'")

    def add_to_graph_groups(self, dut_name):
        """Add DUT name to existing graph_groups.yml file, before example_ixia if it exists"""
        graph_groups_file = self.files_path / "graph_groups.yml"

        if not graph_groups_file.exists():
            raise FileNotFoundError(f"graph_groups.yml file not found at {graph_groups_file}")

        # Read existing content
        with open(graph_groups_file, 'r') as f:
            lines = f.readlines()

        # Check if already exists
        for line in lines:
            if f"  - {dut_name}" in line or f"- {dut_name}" in line:
                print(f"ℹ DUT '{dut_name}' already exists in graph_groups.yml")
                return

        # Find the position of example_ixia to insert before it
        insert_pos = None
        for i, line in enumerate(lines):
            if 'example_ixia' in line:
                insert_pos = i
                break

        # Insert the entry before example_ixia, or append at the end if not found
        new_entry = f"  - {dut_name}\n"
        if insert_pos is not None:
            lines.insert(insert_pos, new_entry)
        else:
            # Append at the end if example_ixia not found
            if lines and not lines[-1].endswith('\n'):
                lines[-1] += '\n'
            lines.append(new_entry)

        with open(graph_groups_file, 'w') as f:
            f.writelines(lines)

        print(f"✓ Added '{dut_name}' to graph_groups.yml")

    def create_devices_csv(self, dut_name, dut_ip, sonic_hwsku, psus):
        """Create or overwrite sonic_{dut_name}_devices.csv file"""
        devices_file = self.files_path / f"sonic_{dut_name}_devices.csv"

        # Create CSV file with DUT entry
        fieldnames = ['Hostname', 'ManagementIp', 'HwSku', 'Type', 'Protocol', 'Os']
        rows = [{
            'Hostname': dut_name,
            'ManagementIp': dut_ip,
            'HwSku': sonic_hwsku,
            'Type': 'DevSonic',
            'Protocol': '',
            'Os': 'sonic'
        }]

        # Extract unique PDU devices from PSU inputs (based on pdus information from YAML)
        # Each PDU device entry is written to devices.csv based on the pdus section
        pdu_devices = {}
        for psu_input in psus:
            pdu_name, _, _, pdu_info = self.parse_psu_input(psu_input)
            if pdu_info and pdu_name not in pdu_devices:
                # Add PDU device entry based on pdus information
                # Format: Hostname,ManagementIp,HwSku,Type,Protocol,Os
                rows.append({
                    'Hostname': pdu_name,
                    'ManagementIp': pdu_info['ip'],
                    'HwSku': pdu_info['manufacturer'],
                    'Type': pdu_info['type'],
                    'Protocol': pdu_info['protocol'],
                    'Os': ''
                })
                pdu_devices[pdu_name] = True

        file_exists = devices_file.exists()
        with open(devices_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        if file_exists:
            print(f"✓ Overwritten existing file: sonic_{dut_name}_devices.csv")
        else:
            print(f"✓ Created NEW file: sonic_{dut_name}_devices.csv")

    def create_pdu_links_csv(self, dut_name, psus):
        """Create or overwrite sonic_{dut_name}_pdu_links.csv file based on pdus information"""
        pdu_links_file = self.files_path / f"sonic_{dut_name}_pdu_links.csv"

        # Parse PSU inputs from pdus information and assign sequential PSU names (PSU1, PSU2, etc.)
        # First pass: collect all PSU names to detect duplicates (only entries with port)
        # PDU links are written based on the pdus section from YAML
        parsed_psus = []
        for psu_input in psus:
            pdu_name, port, psu_name, _ = self.parse_psu_input(psu_input)
            # Only include entries that have port information
            if port:
                parsed_psus.append((pdu_name, port, psu_name))

        # If no entries have port info, skip creating pdu_links file
        if not parsed_psus:
            print(f"ℹ No port information found in PSU inputs. Skipping pdu_links.csv creation.")
            return

        # Check for duplicates or if first PSU doesn't start with PSU1
        psu_names = [p[2] for p in parsed_psus if p[2]]
        has_duplicates = len(psu_names) != len(set(psu_names))
        use_sequential = has_duplicates or (psu_names and psu_names[0].upper() != 'PSU1')

        # Second pass: assign PSU names (ensure uppercase format)
        psu_entries = []
        for i, (pdu_name, port, psu_name) in enumerate(parsed_psus, start=1):
            if use_sequential or not psu_name:
                psu_name = f"PSU{i}"
            else:
                # Ensure PSU name is uppercase (e.g., psu1 -> PSU1)
                psu_name = psu_name.upper() if psu_name else f"PSU{i}"

            psu_entries.append({
                'pdu_name': pdu_name,
                'port': port,
                'psu_name': psu_name
            })

        # Create or overwrite CSV file with PSU entries based on pdus information
        # Format: StartDevice,StartPort,EndDevice,EndPort,EndFeed
        fieldnames = ['StartDevice', 'StartPort', 'EndDevice', 'EndPort', 'EndFeed']
        rows = []
        for entry in psu_entries:
            # Each row represents a PDU link based on pdus information from YAML
            rows.append({
                'StartDevice': entry['pdu_name'],
                'StartPort': entry['port'],
                'EndDevice': dut_name,
                'EndPort': entry['psu_name'],
                'EndFeed': ''
            })

        file_exists = pdu_links_file.exists()
        with open(pdu_links_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        if file_exists:
            print(f"✓ Overwritten existing file: sonic_{dut_name}_pdu_links.csv")
        else:
            print(f"✓ Created NEW file: sonic_{dut_name}_pdu_links.csv")

    def add_to_inventory(self, dut_name, dut_ip, sonic_hwsku, serial_console, ptf_host, psus):
        """Add entries to existing inventory file"""
        inventory_file = self.ansible_path / "inventory"

        if not inventory_file.exists():
            raise FileNotFoundError(f"Inventory file not found at {inventory_file}")

        # Normalize inputs
        dut_name = self._normalize_str(dut_name)
        dut_ip = self._normalize_str(dut_ip)
        sonic_hwsku = self._normalize_str(sonic_hwsku)
        serial_console = self._normalize_str(serial_console)
        ptf_host = self._normalize_str(ptf_host)

        # Extract PDU host from first PSU
        pdu_host = ""
        if psus:
            pdu_name, _, _, _ = self.parse_psu_input(psus[0])
            pdu_host = self._normalize_str(pdu_name)

        # Extract IP and subnet from dut_ip (format: 10.245.21.100/22)
        ip_parts = dut_ip.split('/')
        ip_address = ip_parts[0]
        subnet_mask = ip_parts[1] if len(ip_parts) > 1 else "22"

        # Try to get EEPROM information via SSH (optional - script continues if SSH fails)
        eeprom_data = None
        try:
            eeprom_data = self.get_eeprom_info(dut_ip, username='admin', password='YourPaSsWoRd')
            if eeprom_data:
                print(f"  ✓ Retrieved EEPROM information from switch")
            else:
                print(f"  ⚠ Could not retrieve EEPROM info from switch (SSH may not be available)")
        except Exception as e:
            print(f"  ⚠ Could not retrieve EEPROM info: {e}")
            print(f"  ℹ Continuing without EEPROM information...")

        # Prepare EEPROM fields
        base_mac = eeprom_data.get('base_mac', '') if eeprom_data else ''
        serial = eeprom_data.get('serial', '') if eeprom_data else ''
        model = eeprom_data.get('model', '') if eeprom_data else ''

        # Build syseeprom_info string
        syseeprom_info_str = '""'
        if eeprom_data and eeprom_data.get('syseeprom_info'):
            syseeprom_dict = eeprom_data['syseeprom_info']
            # Format as Python dict string: "{'0x21': u'value', '0x22': u'value', ...}"
            # Escape single quotes in values
            syseeprom_items = []
            for k, v in sorted(syseeprom_dict.items()):
                # Escape single quotes in value
                escaped_value = str(v).replace("'", "\\'")
                syseeprom_items.append(f"'{k}': u'{escaped_value}'")
            syseeprom_dict_str = '{' + ', '.join(syseeprom_items) + '}'
            syseeprom_info_str = f'"{syseeprom_dict_str}"'

        # Update sonic_hwsku if we got product info (optional - keep original if EEPROM doesn't have it)
        final_hwsku = sonic_hwsku
        if eeprom_data and eeprom_data.get('product_name'):
            # You might want to map product_name to hwsku, but for now keep original
            pass

        # Read inventory file
        with open(inventory_file, 'r') as f:
            content = f.read()

        # Ensure PDUs exist in [pdu] section (based on parsed PSU/PDU data)
        pdu_entries = self._extract_pdu_entries_from_psus(psus)
        updated_content, added_pdus = self._ensure_pdu_entries_in_inventory(content, pdu_entries)
        if updated_content != content:
            with open(inventory_file, 'w') as f:
                f.write(updated_content)
            content = updated_content
            if added_pdus:
                print(f"✓ Added missing PDU entries to inventory [pdu]: {', '.join(added_pdus)}")

        # Check if entries already exist
        if f"{dut_name}-ptf-any" in content:
            print(f"ℹ DUT entries already exist in inventory")
            return

        # Find [sonic_latest] section
        pattern = r'(\[sonic_latest\]\s*\n)(.*?)(?=\n\[|\Z)'
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            raise ValueError("Could not find [sonic_latest] section in inventory file")

        section_end = match.end(2)

        # Create inventory entries
        # Format 1: name ansible_host=name  sonic_version=v2  sonic_hwsku=SKU  serial_console="..." ptf_host=... pdu_host=... base_mac=... serial=... model=... syseeprom_info=...
        base_mac_str = f'"{base_mac}"' if base_mac else '""'
        serial_str = f'"{serial}"' if serial else '""'
        model_str = f'"{model}"' if model else '""'

        entry_template = (
            f"\n{dut_name}-ptf-any ansible_host={dut_name}  sonic_version=v2  "
            f"sonic_hwsku={final_hwsku}             "
            f'serial_console="{serial_console}" ptf_host={ptf_host} ptf_portmap="" '
            f"pdu_host={pdu_host} base_mac={base_mac_str} serial={serial_str} model={model_str} syseeprom_info={syseeprom_info_str}\n"
            f"{dut_name} ansible_host={dut_name}  sonic_version=v2  "
            f"sonic_hwsku={final_hwsku}             "
            f'serial_console="{serial_console}" ptf_host={ptf_host} ptf_portmap="" '
            f"pdu_host={pdu_host} base_mac={base_mac_str} serial={serial_str} model={model_str} syseeprom_info={syseeprom_info_str}\n"
        )

        # Format 2: Lab-style entry with IP address, iface_speed, etc.
        # Format: name      ansible_host=ip ansible_hostv6="" sonic_version=v2 hwsku="SKU" iface_speed=200000  mgmt_subnet_mask_length=22 vm_base=VM0000
        lab_style_entry = (
            f"{dut_name}      ansible_host={ip_address} ansible_hostv6=\"\" "
            f"sonic_version=v2 hwsku=\"{sonic_hwsku}\" iface_speed=200000  "
            f"mgmt_subnet_mask_length={subnet_mask} vm_base=VM0000\n"
        )

        # Insert entries into [sonic_latest] section
        new_content = (
            content[:section_end] +
            entry_template +
            lab_style_entry +
            content[section_end:]
        )

        # Also add to [lab] section
        lab_pattern = r'(\[lab\]\s*\n)(.*?)(?=\n\[|\Z)'
        lab_match = re.search(lab_pattern, new_content, re.DOTALL)

        if lab_match:
            lab_section_end = lab_match.end(2)
            lab_entries = f"\n{dut_name}-ptf-any\n{dut_name}\n"
            new_content = (
                new_content[:lab_section_end] +
                lab_entries +
                new_content[lab_section_end:]
            )

        # Write back
        with open(inventory_file, 'w') as f:
            f.write(new_content)

        print(f"✓ Added entries to inventory file")

    def add_to_lab(self, dut_name, dut_ip, sonic_hwsku):
        """Add entry to [sonic_latest] section in lab file"""
        lab_file = self.ansible_path / "lab"

        if not lab_file.exists():
            raise FileNotFoundError(f"Lab file not found at {lab_file}")

        # Extract IP and subnet from dut_ip (format: 10.210.24.55/22)
        ip_parts = dut_ip.split('/')
        ip_address = ip_parts[0]
        subnet_mask = ip_parts[1] if len(ip_parts) > 1 else "22"

        # Read lab file
        with open(lab_file, 'r') as f:
            content = f.read()

        # Check if entry already exists
        if f"{dut_name}" in content and f"ansible_host={ip_address}" in content:
            print(f"ℹ DUT entry already exists in lab file")
            return

        # Find [sonic_latest] section in lab file
        pattern = r'(\[sonic_latest\]\s*\n)(.*?)(?=\n\[|\Z)'
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            raise ValueError("Could not find [sonic_latest] section in lab file")

        section_end = match.end(2)

        # Format: name      ansible_host=ip ansible_hostv6="fe80::e42:a1ff:fe44:44c0" sonic_version=v2 hwsku="SKU" iface_speed=25000  mgmt_subnet_mask_length=22 vm_base=VM0000
        # Default iface_speed is 25000, but can be overridden if needed
        entry = (
            f"{dut_name}      ansible_host={ip_address} ansible_hostv6=\"fe80::e42:a1ff:fe44:44c0\" "
            f"sonic_version=v2 hwsku=\"{sonic_hwsku}\" iface_speed=25000  "
            f"mgmt_subnet_mask_length={subnet_mask} vm_base=VM0000\n"
        )

        # Insert entry into [sonic_latest] section
        new_content = (
            content[:section_end] +
            entry +
            content[section_end:]
        )

        # Write back
        with open(lab_file, 'w') as f:
            f.write(new_content)

        print(f"✓ Added entry to lab file [sonic_latest] section")

    def add_to_testbed_yaml(self, dut_name, ptf_host):
        """Add entry to existing testbed.yaml file"""
        testbed_file = self.ansible_path / "testbed.yaml"

        if not testbed_file.exists():
            raise FileNotFoundError(f"testbed.yaml file not found at {testbed_file}")

        # Read testbed.yaml
        with open(testbed_file, 'r') as f:
            content = f.read()

        # Check if entry already exists
        if f"{dut_name}-ptf-any" in content:
            print(f"ℹ Testbed entry already exists in testbed.yaml")
            return

        # Format based on example
        entry = (
            f"\n- conf-name: {dut_name}-ptf-any\n"
            f"  group-name: vm-t1\n"
            f"  topo: ptf-any\n"
            f"  ptf_image_name: docker-ptf-mlnx\n"
            f"  ptf: {ptf_host}\n"
            f"  ptf_ip: 1.1.1.1/16\n"
            f"  ptf_ipv6:\n"
            f"  server: server_54\n"
            f"  vm_base: VM0000\n"
            f"  dut:\n"
            f"     - {dut_name}\n"
            f"  comment: NvidiaAir testbed"
        )

        # Append to file
        with open(testbed_file, 'a') as f:
            f.write(entry)

        print(f"✓ Added entry to testbed.yaml")

    def generate_all(self, dut_name, dut_ip, psus, ptf_host, sonic_hwsku, serial_console):
        """Generate all configuration files"""
        print(f"\n{'='*70}")
        print(f"Generating DUT setup for: {dut_name}")
        print(f"{'='*70}\n")

        try:
            self.add_to_graph_groups(dut_name)
            self.create_devices_csv(dut_name, dut_ip, sonic_hwsku, psus)
            self.create_pdu_links_csv(dut_name, psus)
            self.add_to_inventory(dut_name, dut_ip, sonic_hwsku, serial_console, ptf_host, psus)
            # Note: Lab-style entry is now added to [sonic_latest] section in inventory
            self.add_to_lab(dut_name, dut_ip, sonic_hwsku)
            self.add_to_testbed_yaml(dut_name, ptf_host)

            print(f"\n{'='*70}")
            print(f"✓ Successfully generated all configuration files for {dut_name}")
            print(f"{'='*70}\n")

        except Exception as e:
            print(f"\n✗ Error: {e}")
            sys.exit(1)


def parse_yaml_config(yaml_file):
    """Parse YAML configuration file and return parameters"""
    with open(yaml_file, 'r') as f:
        config = yaml.safe_load(f)

    # Optional extras (previously CLI flags)
    ptf_host = str(config.get('ptf_host', 'ptf-dummy')).strip() or 'ptf-dummy'
    # Parse switches section - handle list of dicts with single key-value pairs
    switches = config.get('switches', [])
    if not switches:
        raise ValueError("No switches found in YAML file")

    # Merge all switch items into a single dict
    switch_dict = {}
    for item in switches:
        if isinstance(item, dict):
            switch_dict.update(item)

    # Debug: print what we found
    if not switch_dict:
        raise ValueError(f"No switch data found. Parsed switches: {switches}")

    dut_ip = str(switch_dict.get('ip', '')).strip()
    dut_name = str(switch_dict.get('domain', '')).strip()
    sonic_hwsku = str(switch_dict.get('sonic_hwsku', '')).strip()
    serial_console = str(switch_dict.get('serial_console', '')).strip()

    # Provide helpful error messages
    missing_fields = []
    if not dut_ip:
        missing_fields.append("ip")
    if not dut_name:
        missing_fields.append("domain")
    if not sonic_hwsku:
        missing_fields.append("sonic_hwsku")
    if not serial_console:
        missing_fields.append("serial_console")

    if missing_fields:
        raise ValueError(
            f"Missing required switch fields in YAML file: {', '.join(missing_fields)}. "
            f"Found fields: {list(switch_dict.keys())}. "
            f"Parsed switches list: {switches}"
        )

    # Add subnet mask if not present (default to /22)
    if '/' not in dut_ip:
        dut_ip = f"{dut_ip}/22"

    # Parse PDUs section - handle list format where PDU entries are separated
    pdus = config.get('pdus', [])
    psus = []

    # Group PDU entries - each PDU entry consists of multiple dict items
    # When we see a new 'ip' key, it starts a new PDU entry
    current_pdu = {}
    for item in pdus:
        if isinstance(item, dict):
            # Check if this is a new PDU entry (has 'ip' key and we already have a PDU)
            if 'ip' in item:
                # Save previous PDU entry if it exists
                if current_pdu and 'ip' in current_pdu:
                    pdu_ip = str(current_pdu.get('ip', '')).strip()
                    # Handle both 'pdu_name' (correct) and 'psu_name' (typo)
                    psu_name = str(current_pdu.get('psu_name') or current_pdu.get('pdu_name', '')).strip()
                    port = str(current_pdu.get('port', '')).strip()
                    sku = str(current_pdu.get('sku', '')).strip()
                    protocol = str(current_pdu.get('protocol', 'snmp')).strip() or 'snmp'

                    if pdu_ip:
                        pdu_name = f"pdu-{pdu_ip.replace('.', '-')}"
                        psu_str = f"{pdu_name},{pdu_ip},{sku},Pdu,{protocol},{port},{psu_name}"
                        psus.append(psu_str)

                # Start new PDU entry
                current_pdu = item.copy()
            else:
                # Merge into current PDU entry
                current_pdu.update(item)

    # Don't forget the last PDU entry
    if current_pdu and 'ip' in current_pdu:
        pdu_ip = str(current_pdu.get('ip', '')).strip()
        # Handle both 'pdu_name' (correct) and 'psu_name' (typo)
        psu_name = str(current_pdu.get('psu_name') or current_pdu.get('pdu_name', '')).strip()
        port = str(current_pdu.get('port', '')).strip()
        sku = str(current_pdu.get('sku', '')).strip()
        protocol = str(current_pdu.get('protocol', 'snmp')).strip() or 'snmp'

        if pdu_ip:
            pdu_name = f"pdu-{pdu_ip.replace('.', '-')}"
            psu_str = f"{pdu_name},{pdu_ip},{sku},Pdu,{protocol},{port},{psu_name}"
            psus.append(psu_str)

    return {
        'dut_name': dut_name,
        'dut_ip': dut_ip,
        'sonic_hwsku': sonic_hwsku,
        'serial_console': serial_console,
        'psus': psus,
        'ptf_host': ptf_host,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Generate DUT setup files for sonic-mgmt',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using YAML config file:
  %(prog)s --yaml-config setup_ansible_data.yaml
        """
    )

    parser.add_argument('--yaml-config', required=True,
                        help='YAML configuration file path (e.g., setup_ansible_data.yaml)')
    parser.add_argument('--sonic-mgmt-path', default=None,
                       help='Path to sonic-mgmt repository (default: auto-detect from script location)')

    args = parser.parse_args()

    # Auto-detect sonic-mgmt root directory if not provided
    if args.sonic_mgmt_path is None:
        # Get the directory where this script is located
        script_dir = Path(__file__).resolve().parent
        # Navigate up to find sonic-mgmt root (should have 'ansible' directory)
        current = script_dir
        while current != current.parent:
            ansible_dir = current / "ansible"
            if ansible_dir.exists() and ansible_dir.is_dir():
                args.sonic_mgmt_path = str(current)
                break
            current = current.parent
        else:
            # If not found, default to current working directory
            args.sonic_mgmt_path = '.'
            print("⚠ Warning: Could not auto-detect sonic-mgmt root. Using current directory.")

    # Convert to absolute path and verify
    sonic_mgmt_path = Path(args.sonic_mgmt_path).resolve()
    ansible_path = sonic_mgmt_path / "ansible"
    files_path = ansible_path / "files"

    if not ansible_path.exists():
        raise FileNotFoundError(
            f"Ansible directory not found at {ansible_path}. "
            f"Please specify correct --sonic-mgmt-path or run from sonic-mgmt root directory."
        )

    if not files_path.exists():
        raise FileNotFoundError(
            f"Ansible files directory not found at {files_path}. "
            f"Please specify correct --sonic-mgmt-path or run from sonic-mgmt root directory."
        )

    # Update args with resolved path
    args.sonic_mgmt_path = str(sonic_mgmt_path)

    # Resolve YAML config path (if relative, resolve from current working directory)
    yaml_config_path = Path(args.yaml_config)
    if not yaml_config_path.is_absolute():
        yaml_config_path = Path.cwd() / yaml_config_path
    if not yaml_config_path.exists():
        raise FileNotFoundError(f"YAML config file not found: {yaml_config_path}")

    config = parse_yaml_config(str(yaml_config_path))
    dut_name = config['dut_name']
    dut_ip = config['dut_ip']
    sonic_hwsku = config['sonic_hwsku']
    serial_console = config['serial_console']
    psus = config['psus']
    ptf_host = config.get('ptf_host', 'ptf-dummy')

    generator = DUTSetupGenerator(args.sonic_mgmt_path)
    generator.generate_all(
        dut_name=dut_name,
        dut_ip=dut_ip,
        psus=psus,
        ptf_host=ptf_host,
        sonic_hwsku=sonic_hwsku,
        serial_console=serial_console
    )


if __name__ == '__main__':
    main()

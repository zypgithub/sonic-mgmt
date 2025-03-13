"""
This script runs the mlxreg command for xdr_slow or cleanup on specified port name(s) on a remote system.

Steps for enabling xdr_slow speed:
1. Establish an SSH connection to the remote system and login using username and password
2. In default configuration - we expect the configured ports to be the following state:
    sw7p1s1    down                 nvl                    Down           Disabled
    sw7p1s2    down                 nvl                    Down           Disabled
    sw7p2s1    down                 nvl                    Down           Disabled
    sw7p2s2    down                 nvl                    Down           Disabled
    sw8p1s1    down                 nvl                    Down           Disabled
    sw8p1s2    down                 nvl                    Down           Disabled
    sw8p2s1    down                 nvl                    Down           Disabled
    sw8p2s2    down                 nvl                    Down           Disabled
3. Set both ports states to down: (assuming sw7,sw8 are connected on juliet-126)
   a. nv set interface sw7p1-2s1-2 link state down
   b. nv set interface sw8p1-2s1-2 link state down
   c. nv config apply
4. Run this script:
   a. python run_xdr_slow.py -u admin -p password juliet-126 sw8 xdr_slow
   a. python run_xdr_slow.py -u admin -p password juliet-126 sw7 xdr_slow
5. Set both ports states to up:
   a. nv set interface sw7p1-2s1-2 link state up
   b. nv set interface sw8p1-2s1-2 link state up
   c. nv config apply
6. All done - we expect the configured ports to be the following state:
    sw7p1s1    up     400G   256    nvl                    Initialize     LinkUp
    sw7p1s2    up     400G   256    nvl                    Initialize     LinkUp
    sw7p2s1    up     400G   256    nvl                    Initialize     LinkUp
    sw7p2s2    up     400G   256    nvl                    Initialize     LinkUp
    sw8p1s1    up     400G   256    nvl                    Initialize     LinkUp
    sw8p1s2    up     400G   256    nvl                    Initialize     LinkUp
    sw8p2s1    up     400G   256    nvl                    Initialize     LinkUp
    sw8p2s2    up     400G   256    nvl                    Initialize     LinkUp

"""

import argparse
import re
import paramiko
import json


def get_log_port(table: str, label_port: int, lane_bmap: str):
    """
    Fetches the log_port value based on label_port and lane_bmap values from a given table.
    Returns only the last two digits of log_port after removing the '0x100' prefix.

    Args:
        table (str): The table as a multiline string.
        label_port (int): The switch number (label_port).
        lane_bmap (str): The lane_bmap value (either '0x01' or '0x80').

    Returns:
        str: The corresponding log_port value without the '0x100' prefix, e.g., '09'.

    Raises:
        ValueError: If the specified label_port and lane_bmap combination are not found in the table.
    """

    # Split the table into rows
    rows = table.splitlines()
    header = rows[1]  # Header row with column names

    # Identify column indexes based on the header
    columns = header.split("|")
    col_indexes = {
        "log_port": columns.index("  log_port"),
        "label_port": columns.index("label_port"),
        "lane_bmap": columns.index(" lane_bmap")
    }

    # Parse rows and find the matching row based on label_port and lane_bmap
    for row in rows[3:]:  # Data rows start after the separator line
        cols = row.split("|")
        try:
            row_label_port = cols[col_indexes["label_port"]].strip()
            row_lane_bmap = cols[col_indexes["lane_bmap"]].strip()

            # Match the given label_port and lane_bmap
            if row_label_port == label_port and row_lane_bmap == lane_bmap:
                # Extract the last two digits of log_port, remove the "0x100" prefix
                log_port_value = cols[col_indexes["log_port"]].strip()
                return log_port_value[-2:]  # Return the last two characters
        except ValueError:
            continue  # Skip rows with non-numeric values in relevant columns

    raise ValueError(f"Entry not found for label_port={label_port}, lane_bmap={lane_bmap}")


def get_local_port_and_lane_bmap(port_name):
    """
    Extracts the switch number and lane_bmap from a port name.

    Args:
        port_name (str): The port name string (e.g., 'sw17p1s1', 'sw17p1s2', 'sw17p2s1', 'sw17p2s2').

    Returns:
        tuple: A tuple containing the switch number and lane_bmap (e.g., ('17', '0x80')).
    """
    match = re.search(r'[sS][wW]\s*(\d+)p(\d+)s(\d+)', port_name)

    if match:
        port_number = match.group(1)
        local_port = int(match.group(2))
        split_port = int(match.group(3))

        # Determine the lane_bmap based on the local_port and split_port
        if split_port == 1:
            if local_port == 1:
                lane_bmap = '0x0C'
            elif local_port == 2:
                lane_bmap = '0xC0'
            else:
                raise ValueError(f"Unsupported local_port value: {local_port}")
        elif split_port == 2:
            if local_port == 1:
                lane_bmap = '0x03'
            elif local_port == 2:
                lane_bmap = '0x30'
            else:
                raise ValueError(f"Unsupported local_port value: {local_port}")
        else:
            raise ValueError(f"Unsupported split_port value: {split_port}")

        return port_number, lane_bmap

    raise ValueError(f"Invalid port name format: {port_name}")


def get_device_path(ssh_client, port_name):
    # Command to get the device path in JSON format (replace with the actual command)
    cmd = f"nv show fae interface {port_name} --output json"
    stdin, stdout, stderr = ssh_client.exec_command(cmd)
    result = stdout.read().decode()
    error = stderr.read().decode()
    if error:
        print(f"Error getting device path: {error}")
        return None

    try:
        device_info = json.loads(result)
        device_path = device_info.get("primary-asic-device")
        primary_asic = device_info.get("primary-asic")
        if not device_path or not primary_asic:
            print("Error: 'primary-asic-device' not found in the JSON output.")
            return None
        return device_path, primary_asic
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON output: {str(e)}")
        return None


def get_local_port(ssh_client, port_name, primary_asic):
    # Command to get the local port number based on the port name (replace with the actual command)
    docker = f"syncd-ibv0{primary_asic}"
    cmd = f"docker exec {docker} sx_api_ports_mapping_dump.py"
    stdin, stdout, stderr = ssh_client.exec_command(cmd)
    table_output = stdout.read().decode()
    error = stderr.read().decode()
    if error:
        print(f"Error getting local port: {error}")
        return None
    local_port, lane_bmap = get_local_port_and_lane_bmap(port_name)
    return get_log_port(table_output, local_port, lane_bmap)


def run_mlxreg_command(ssh_client, device_path, local_port, action):
    if action == "xdr_slow":
        mlxreg_cmd = (
            f"sudo mlxreg -d {device_path} --set \"ib_link_width_admin=0x3,ib_proto_admin=0x100,xdr_2x_slow_admin=1,an_disable_admin=0\" --reg_name PTYS "
            f"--indexes \"local_port=0x{local_port},proto_mask=1,port_type=0,lp_msb=0,plane_ind=0\" -y --overwrite"
        )
    elif action == "cleanup":
        mlxreg_cmd = (
            f"sudo mlxreg -d {device_path} --set \"ib_link_width_admin=0x2,ib_proto_admin=0x100,xdr_2x_slow_admin=0,an_disable_admin=0\" --reg_name PTYS "
            f"--indexes \"local_port=0x{local_port},proto_mask=1,port_type=0,lp_msb=0,plane_ind=0\" -y --overwrite"
        )
    else:
        print(f"Unknown action: {action}")
        return

    print(f"Running mlxreg command: {mlxreg_cmd}")
    stdin, stdout, stderr = ssh_client.exec_command(mlxreg_cmd)
    result = stdout.read().decode()
    error = stderr.read().decode()
    if error:
        print(f"Error running mlxreg command: {error}")
    else:
        print("mlxreg command executed successfully.")
        print(f"Result: {result}")


def process_port(ssh_client, port_name, action):
    device_path, primary_asic = get_device_path(ssh_client, port_name)
    if device_path is None:
        return

    local_port = get_local_port(ssh_client, port_name, primary_asic)
    if local_port is None:
        return

    run_mlxreg_command(ssh_client, device_path, local_port, action)


def main():
    parser = argparse.ArgumentParser(description="Run mlxreg command for xdr_slow with specified port name(s) on a remote system.")
    parser.add_argument("-u", "--username", help="The username for SSH login.")
    parser.add_argument("-p", "--password", help="The password for SSH login.")
    parser.add_argument("hostname", help="The hostname of the remote system.")
    parser.add_argument("port_name", help="The name of the split port (sw8p1s1) or full port (sw8).")
    parser.add_argument("action", choices=["xdr_slow", "cleanup"], help="Action to perform: 'xdr_slow' or 'cleanup'.")

    parser.epilog = ("Example: python run_xdr_slow.py -u admin -p password hostname port_name {xdr_slow,cleanup}")

    args = parser.parse_args()

    hostname = args.hostname
    username = args.username
    port_name = args.port_name
    action = args.action
    password = args.password

    # Establish SSH connection
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        if password:
            ssh_client.connect(hostname, username=username, password=password)
        else:
            ssh_client.connect(hostname, username=username)

        if re.match(r'[sS][wW]\s*\d+', port_name):
            # Handle all ports on the switch
            port_number = re.search(r'\d+', port_name).group(0)
            for p in [1, 2]:
                for s in [1, 2]:
                    port = f"sw{port_number}p{p}s{s}"
                    process_port(ssh_client, port, action)
        elif port_name.lower() == 'all':
            # Handle all port names from 1-18
            for port_number in range(1, 19):
                for p in [1, 2]:
                    for s in [1, 2]:
                        port = f"sw{port_number}p{p}s{s}"
                        process_port(ssh_client, port, action)
        else:
            # Handle single port
            process_port(ssh_client, port_name, action)
    finally:
        ssh_client.close()


if __name__ == "__main__":
    main()

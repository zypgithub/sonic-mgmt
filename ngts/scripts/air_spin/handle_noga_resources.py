import os
import re
os.environ["PYTHONPATH"] = "/local/remote/sonic/sonic-mgmt:$PYTHONPATH"
from .config import NOGA_MANAGE_SCRIPT, NOGA_UPDATE_ATTR_SCRIPT


def get_mac_for_ip(ip):
    cmd = f"cat /auto/LIT/SCRIPTS/DHCPD/list | grep {ip}"
    output = os.popen(cmd).read()
    return output.split("; ")[1]


def parse_noga_manage_output(output):
    result = output.split("[INFO] Reply:")[1]
    available_vms = result.split("\n")
    ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    if len(available_vms) <= 1:
        print("Error: No available IP found")
        exit(1)
    for vm in available_vms[1:]:
        ip_match = re.search(ip_pattern, vm)
        if ip_match:
            print(f"Found available IP: {ip_match.group(0)}")
            return ip_match.group(0), vm.split("\t")[0]
    print("Error: No available IP found")
    exit(1)


def lock_unlock_vm(ip, lock):
    action = "l" if lock else "u"
    cmd = f"{NOGA_MANAGE_SCRIPT} -{action} --ip {ip}"
    output = os.popen(cmd).read()
    return output


def add_simulation_id_to_noga(simulation_id, resource_id):
    cmd = f"{NOGA_UPDATE_ATTR_SCRIPT} --id {resource_id} --attr_name \"Free_Text\" --attr_value \"{simulation_id}\""
    output = os.popen(cmd).read()
    print(f"Added simulation ID {simulation_id} to Noga {resource_id}: {output}\
        Visible in (Free_Text attribute)")
    return output


def delete_simulation_id_from_noga(resource_id):
    cmd = f"{NOGA_UPDATE_ATTR_SCRIPT} --id {resource_id} --attr_name \"Free_Text\" --attr_value \"\""
    output = os.popen(cmd).read()
    print(f"Deleted simulation ID (Free_Text attribute) from Noga: {resource_id}")


if __name__ == "__main__":
    print(get_mac_for_ip("10.0.0.1"))

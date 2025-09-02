import os
import re
os.environ["PYTHONPATH"] = "/local/remote/sonic/sonic-mgmt:$PYTHONPATH"
from .config import NOGA_MANAGE_SCRIPT
import logging
import sys
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)


def get_mac_for_ip(ip):
    cmd = f"cat /auto/LIT/SCRIPTS/DHCPD/list | grep {ip}"
    output = os.popen(cmd).read()
    return output.split("; ")[1]


def parse_noga_manage_output(output):
    result = output.split("[INFO] Reply:")[1]
    available_vms = result.split("\n")
    ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    if len(available_vms) <= 1:
        raise Exception("No available VMs found")
    for vm in available_vms[1:]:
        ip_match = re.search(ip_pattern, vm)
        if ip_match:
            logger.info(f"Found available IP: {ip_match.group(0)}")
            return ip_match.group(0)
    raise Exception("No available IPs found")


def lock_unlock_vm(ip):
    cmd = f"{NOGA_MANAGE_SCRIPT} -l --ip {ip}"
    output = os.popen(cmd).read()
    return output


def release_ip(ip):
    lock_unlock_vm(ip)
    logger.info(f"Released IP: {ip}")

# def add_label_to_vm(ip):
#     cmd = f"curl https://noga.mellanox.com/app/server/php/rest_api/api_cmd=update_resource_labels&login_user=ytzur&"
#     output = os.popen(cmd).read()
#     return output


if __name__ == "__main__":
    vm_obj = get_vm_obj_from_noga()
    print(vm_obj.ip)
    print(vm_obj.mac)
    print(vm_obj.labels)
    print(vm_obj.vm_type)
    print(vm_obj.vm_name)

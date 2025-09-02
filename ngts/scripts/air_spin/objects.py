import os
from .config import SETUP_TEMPLATE_FILE, NOGA_MANAGE_SCRIPT
from .utils import create_setup_file, create_topo_files
from .allocate_ip import get_mac_for_ip, parse_noga_manage_output, lock_unlock_vm


class VMObj:
    def __init__(self, ip=None, mac=None):
        self.ip = ip
        self.mac = mac
        self.labels = None
        self.vm_type = None
        self.vm_name = None
        self.get_vm_obj_from_noga()

    def get_vm_obj_from_noga(self):
        """get available ip address"""
        cmd = f"{NOGA_MANAGE_SCRIPT} -qr -e group_name:Sagi,subgroup:SONiC_Air,with_labels:air_spin -t VM"
        output = os.popen(cmd).read()
        available_ip = parse_noga_manage_output(output)
        self.ip = available_ip
        self.mac = get_mac_for_ip(available_ip)
        lock_unlock_vm(available_ip)


class SetupObj:
    def __init__(self, setup_name, topology_type, simx_version, dut_name, dut_hwsku,
                 chip_type, base_version, custom_tarball_name, sonic_mgmt_repo_branch, topology, organization_name="SONIC", docker_ip=None, topology_links_path=""):
        setup_name = setup_name if setup_name.startswith("air") else "air-" + setup_name
        self.setup_name = setup_name
        self.topology_type = topology_type
        self.simx_version = simx_version
        self.organization_name = organization_name
        self.docker_ip = docker_ip
        self.dut_name = dut_name if dut_name.startswith("air") else "air-" + dut_name
        self.dut_hwsku = dut_hwsku
        self.chip_type = chip_type
        self.base_version = base_version
        self.sonic_mgmt_repo_branch = sonic_mgmt_repo_branch
        self.topology = topology
        self.custom_tarball_name = custom_tarball_name
        self.topology_links_path = topology_links_path
        self.topology_xml_path = None
        self.setup_path = None
        self.docker_mac = None
        self.vm_obj = None

    def allocate_vm_obj(self):
        self.vm_obj = VMObj()

    def create_files(self, topology_type):
        create_setup_file(self)
        create_topo_files(self)

import os
import json
import string
import re
import random
from .config import *
from .utils import create_setup_file, create_topo_files
from .handle_noga_resources import get_mac_for_ip, parse_noga_manage_output, lock_unlock_vm


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
        available_ip, resource_id = parse_noga_manage_output(output)
        self.ip = available_ip
        self.resource_id = resource_id
        self.mac = get_mac_for_ip(available_ip)
        lock_unlock_vm(available_ip, lock=True)


class SetupObj:
    def __init__(self, setup_name, topology_type, simx_version, dut_name, dut_hwsku,
                 chip_type, base_version, custom_tarball_name, sonic_mgmt_repo_branch,
                 topology, organization_name, custom_links_path, dbs_to_run_path):
        setup_name = self.generate_setup_name(setup_name)
        self.setup_name = setup_name
        self.topology_type = topology_type
        self.simx_version = simx_version
        self.organization_name = organization_name
        self.dut_name = dut_name if dut_name else setup_name
        self.dut_hwsku = dut_hwsku
        self.chip_type = chip_type
        self.base_version = base_version
        self.sonic_mgmt_repo_branch = sonic_mgmt_repo_branch
        self.topology = topology
        self.custom_tarball_name = custom_tarball_name
        self.custom_links_path = custom_links_path
        self.dbs_to_run_path = dbs_to_run_path
        self.topology_file_path = None
        self.setup_path = None
        self.docker_mac = None
        self.vm_obj = None
        self.simulation_data = None

    def validate_setup_name(self, setup_name):
        if not bool(re.fullmatch(r"[A-Za-z0-9-]+", setup_name)):
            print(f"Error: Setup name must contain only letters, numbers, and hyphens(-): {setup_name}\
                    please run the command again with a valid setup name")
            exit(1)
        if not setup_name.startswith("air"):
            setup_name = "air-" + setup_name
        return setup_name

    def generate_setup_name(self, setup_name):
        if not setup_name:
            setup_name = "air-" + random.choice(string.ascii_letters) + str(random.randint(100000, 999999))
        return self.validate_setup_name(setup_name)

    def allocate_vm_obj(self):
        self.vm_obj = VMObj()

    def create_files(self):
        create_setup_file(self)
        create_topo_files(self)

    def get_simulation_data(self):
        data_file_path = os.path.join(SETUPS_FOLDER_PATH, self.setup_name, "simulation_details.json")
        if not os.path.exists(data_file_path):
            raise Exception(f"Simulation data file not found: {data_file_path}")
        with open(data_file_path, "r") as f:
            simulation_data = json.load(f)
            simulation_data["sonic_mgmt_ip"] = self.vm_obj.ip
            json.dump(simulation_data, open(data_file_path, "w"), indent=4)
            os.system(f"chmod 777 {data_file_path}")
            print(f"Updated simulation data file: {data_file_path}")
            self.simulation_data = simulation_data

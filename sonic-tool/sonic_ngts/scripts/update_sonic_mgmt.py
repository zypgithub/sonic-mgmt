import argparse
import csv
import os
import logging
import shutil

from infra.tools.topology_tools.topology_setup_utils import get_topology_by_setup_name

logger = logging.getLogger(__name__)


class ConfFiles:
    def __init__(self, sonic_mgmt):
        self.testbed_csv = "{sonic_mgmt}/ansible/testbed.csv".format(sonic_mgmt=sonic_mgmt)
        self.lab = "{sonic_mgmt}/ansible/lab".format(sonic_mgmt=sonic_mgmt)
        self.inventory = "{sonic_mgmt}/ansible/inventory".format(sonic_mgmt=sonic_mgmt)
        self.minigraph_facts = "{sonic_mgmt}/ansible/library/minigraph_facts.py".format(sonic_mgmt=sonic_mgmt)

    def __getattribute__(self, name):
        return object.__getattribute__(self, name)


class TestbedCSV:
    """
    @summary: Class which adds entry to the 'testbed.csv' file
    """
    def __init__(self, csv_file):
        self.testbed_csv = csv_file

    def entry_exists(self, dut_name):
        """
        Ensure entry with specified DUT exists in 'ansible/testbed.csv' file
        @param dut_name: DUT name
        """
        with open(self.testbed_csv) as testbed_file:
            csv_reader = csv.DictReader(testbed_file)
            if any([dut_name in row["# conf-name"] for row in csv_reader]):
                return True
            else:
                return False

    def add_testbed_entry(self, dut_name):
        """
        Add new entry to the testbed.csv file
        Entry example:
        air_2700_1-ptf-any,vm-t1,ptf-any,docker-ptf-mlnx,ptf-dummy,1.1.1.1/16,,server_54,VM0000,air_2700_1,NvidiaAir testbed
        """
        with open(self.testbed_csv, "a+") as testbed_file:
            line = f"\n{dut_name}-ptf-any,vm-t1,ptf-any,docker-ptf-mlnx,ptf-dummy,1.1.1.1/16,,server_54,VM0000,{dut_name},NvidiaAir testbed\n"
            testbed_file.write(line)


class Inventory:
    """
    @summary: Class to add entry to the 'inventory' file
    """
    def __init__(self, inventory):
        self.inventory_path = inventory
        self.inventory_buff = self.read()

    def read(self):
        """
        Read and return content of 'ansible/inventory' file
        """
        with open(self.inventory_path) as inv_file:
            buff = inv_file.read()
        return buff

    def entry_exists(self, dut_name):
        """
        Ensure entry with specified DUT exists in 'ansible/inventory' file
        @param dut_name: DUT name
        """
        with open(self.inventory_path) as inventory_file:
            for line in inventory_file.read().splitlines():
                if dut_name in line:
                    return True
        return False

    def add_entry(self, dut_name, ansible_host, ansible_port):
        """
        Add new entries to the inventory file
        Entry example:
        air_2700_1-ptf-any ansible_host=147.75.47.205 ansible_port=18696
        air_2700_1 ansible_host=147.75.47.205 ansible_port=18696
        """
        buff = ""
        host_entry_ptf_any = f"{dut_name}-ptf-any ansible_host={ansible_host} ansible_port={ansible_port}"
        host_entry = f"{dut_name} ansible_host={ansible_host} ansible_port={ansible_port}"

        for line in self.inventory_buff.splitlines():
            if "[sonic_latest]" in line:
                buff += line + "\n"
                buff += host_entry_ptf_any + "\n"
                buff += host_entry + "\n"
            elif "[lab]" in line:
                buff += line + "\n"
                buff += f"{dut_name}-ptf-any" + "\n"
                buff += dut_name + "\n"
            else:
                buff += line + "\n"
        with open(self.inventory_path, "w", 0o0600) as inv_file:
            inv_file.write(buff)


class Lab:
    """
    @summary: Class to add entry to the 'lab' file.
    """
    def __init__(self, lab_path):
        self.lab_path = lab_path
        self.lab_buff = self.read()

    def read(self):
        """
        Read and return content of 'ansible/lab' file
        """
        with open(self.lab_path) as lab_file:
            buff = lab_file.read()
        return buff

    def add_entry(self, dut_name, ansible_host, ansible_port):
        """
        Add new entry to the lab file
        Entry example:
        air_2700_1      ansible_host=10.210.25.107 ansible_port=12345 sonic_version=v2
        """
        buff = ""
        lab_template = "{dut_name}      ansible_host={ansible_host} ansible_port={ansible_port} sonic_version=v2"
        lab_entry = lab_template.format(dut_name=dut_name, ansible_host=ansible_host, ansible_port=ansible_port)
        for line in self.lab_buff.splitlines():
            if "[sonic_latest]" in line:
                buff += line + "\n"
                buff += lab_entry + "\n"
            else:
                buff += line + "\n"

        with open(self.lab_path, "w", 0o0600) as lab_file:
            lab_file.write(buff)


class MinigraphFacts:
    def __init__(self, mgmt_minigraph_path):
        self.mgmt_minigraph_path = mgmt_minigraph_path
        self.stub_mgmt_minigraph_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "minigraph_facts.py")

    def write_minigraph_facts(self):
        shutil.copyfile(self.stub_mgmt_minigraph_path, self.mgmt_minigraph_path)


def replace_conn_graph_facts(sonic_mgmt_path):
    mgmt_conn_graph_facts_path = '{}/ansible/library/conn_graph_facts.py'.format(sonic_mgmt_path)
    stub_mgmt_conn_graph_facts_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'conn_graph_facts.py')
    logger.info('Replacing: {} by {}'.format(mgmt_conn_graph_facts_path, stub_mgmt_conn_graph_facts_path))
    shutil.copyfile(stub_mgmt_conn_graph_facts_path, mgmt_conn_graph_facts_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dut", help="DUT name", type=str, required=True)
    parser.add_argument("--mgmt_repo", help="Path to the sonic-mgmt repo", type=str, required=True)

    args = parser.parse_args()

    dut_name = args.dut
    mgmt_repo = args.mgmt_repo

    conf_files = ConfFiles(mgmt_repo)
    testbed_csv = TestbedCSV(conf_files.testbed_csv)

    lab = Lab(lab_path=conf_files.lab)
    inv = Inventory(conf_files.inventory)
    mg_facts = MinigraphFacts(conf_files.minigraph_facts)

    # Update minigraph_facts.py
    mg_facts.write_minigraph_facts()
    logger.info('minigraph_facts.py replaced by stub file')

    if testbed_csv.entry_exists(dut_name=dut_name):
        logger.warning(f"{conf_files.testbed_csv} - Entry for '{dut_name}' DUT already exists. Skip configuration.")
    else:
        """
        This logic used for add NvidiaAir dynamic setup data into ansible related files(inventory, lab, testbed.csv)
        It will add short info about setup: name, ip, ssh_port - which used by LogAnalyzer and other community plugins
        """
        topology = get_topology_by_setup_name(setup_name=dut_name, slow_cli=False)
        ansible_host = topology.players['dut']['engine'].ip
        ansible_port = topology.players['dut']['engine'].ssh_port

        # Update testbed.csv
        testbed_csv.add_testbed_entry(dut_name)

        # Update ansible/lab
        lab.add_entry(dut_name=dut_name, ansible_host=ansible_host, ansible_port=ansible_port)

        # Update inventory
        inv.add_entry(dut_name, ansible_host=ansible_host, ansible_port=ansible_port)

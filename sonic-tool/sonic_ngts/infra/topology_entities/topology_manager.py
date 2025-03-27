
import os
import logging
import re
import json
import ipaddress

from infra.topology_entities.host_topology_entity import HostTopologyEntity
from infra.topology_entities.switch_topology_entity import SwitchTopologyEntity
from infra.exceptions.entity_exception import TopologyEntityError
from infra.utilities.topology_util import *
#
# create a logger for this class
#
logger = logging.getLogger("topology_manager")


class TopologyManager:
    """
    TopologyManager
    Creates the topology.xml file
    creates setup connectivity
    """

    def __init__(self, setup_arguments, setup_name):
        self.switches = {}
        self.hosts = {}
        self.setup_entities = {}
        self.setup_connectivity = {}
        self.port_aliases_counter = {}
        self.topology_dir_path = None
        self.sonic_topology_dir = "/auto/sw_regression/system/SONIC/MARS/conf/topo/{}"
        self.sonic_setup_dir = "/auto/sw_regression/system/SONIC/MARS/conf/setups/{}"
        self.noga_json_file_path = None
        self.setup_name = None
        self.dut = None
        self.noga_dict = None
        self.set_setup_entities(setup_arguments, setup_name)

    def set_setup_entities(self, setup_arguments, setup_name):
        """
        set the setup entity topology objects, the setup dut, the setup name and connectivity.
        :param setup_arguments: a dictionary with the setup entity information
        :param setup_name: a string specify setup name if setup name should be name differently
                            than sonic_<switch_type>_<switch_hostname>
        :return: None.
        """
        self.set_host_entities(setup_arguments['hosts'])
        self.set_switch_entities(setup_arguments['switches'])
        self.setup_entities.update(self.switches)
        self.setup_entities.update(self.hosts)
        self.set_other_setup_entities(setup_arguments['other_entities'])
        self.set_dut()
        self.set_setup_name(setup_name)
        self.get_connectivity()

    def set_switch_entities(self, switches_list):
        """
        update the switches dictionary.
        :param switches_list: a list of dictionaries with the setup switches information.
                              e.g. [{'ip': '10.210.24.168', ... , 'alias': 'dut'} , ...]
        :return: None.
        for example self.switches = { '10.210.24.168': SwitchTopologyEntity object, ...}
        """
        for switch_dict in switches_list:
            ste = SwitchTopologyEntity(ip=switch_dict['ip'],
                                       username=switch_dict['username'],
                                       password=switch_dict['password'],
                                       alias=switch_dict['alias'])
            self.switches[ste.hostname] = ste

    def set_host_entities(self, hosts_list):
        """
        update the hosts dictionary.
        :param hosts_list: a list of dictionaries with the setup hosts information.
                              e.g. [{'ip': '10.210.24.168', ... , 'alias': 'ha'} , ...]
        :return: None.
        for example self.hosts = { '10.210.24.168': HostTopologyEntity object, ...}
        """
        for host_dict in hosts_list:
            hte = HostTopologyEntity(ip=host_dict['ip'],
                                     username=host_dict['username'],
                                     password=host_dict['password'],
                                     alias=host_dict['alias'])
            self.hosts[hte.hostname] = hte

    def set_other_setup_entities(self, other_setup_entities_list):
        for entity in other_setup_entities_list:
            entity_obj = HostTopologyEntity(ip=entity['ip'],
                                            username=entity['username'],
                                            password=entity['password'],
                                            alias=entity['alias'],
                                            mac=entity['mac'],
                                            hostname=entity['hostname'],
                                            set_entity_info=False)
            self.setup_entities[entity['entity_id']] = entity_obj

    def get_switches_ips(self):
        """
        :return: a list of the switches ip's in setup.
        e.g.  ['10.210.24.168',...]
        """
        ips_list = []
        for switch in self.switches.values():
            ips_list.append(switch.ip)
        return ips_list

    def get_switch_by_ip(self, switch_ip):
        for switch in self.switches.values():
            if switch.ip == switch_ip:
                return switch

    def set_dut(self):
        """
        set the dut switch for the setup.
        :return: None
        """
        ips = self.get_switches_ips()
        sorted_switches_ip = sorted(ips, key=ipaddress.IPv4Address)
        switch_ip = min(sorted_switches_ip)
        self.dut = self.get_switch_by_ip(switch_ip)

    def set_setup_name(self, setup_name):
        """
        set the setup setup name.
        :param setup_name: a string specify setup name if setup name should be name differently
                            than sonic_<switch_type>_<switch_hostname>, or None value
        :return: None
        """
        if setup_name is not None:
            self.setup_name = setup_name
        else:
            self.setup_name = "sonic_{}_{}".format(self.dut.system_type, self.dut.hostname)

    def get_connectivity(self):
        """
        get the connectivities from all the setup entities.
        :return: None
        """
        for host_hostname, host_entity in self.hosts.items():
            self.get_host_connectivity(host_entity)
        for switch_hostname, switch_entity in self.switches.items():
            self.get_switch_connectivity(switch_entity)

    def get_host_connectivity(self, host_entity):
        """
        Updated the setup connectivity for the host entity.
        update the aliases for the host connectivity.
        :param host_entity: a HostTopologyEntity
        :return: None
        """
        for host_port, port_neighbor_info in host_entity.lldp_connectivity.items():
            neighbor_hostname = port_neighbor_info['neighbor_hostname']
            neighbor_port = port_neighbor_info['neighbor_port']
            neighbor_entity = self.setup_entities[neighbor_hostname]
            neighbor_port_alias = neighbor_entity.get_port_sonic_alias(neighbor_port) # will not work when neighbor is host
            self.update_connectivity(host_entity, host_port, neighbor_entity, neighbor_port_alias)
            connectivity_alias = self.get_connectivity_alias(host_entity, neighbor_entity, neighbor_port_alias)
            host_entity.update_port_alias(host_port, connectivity_alias)

    def get_switch_connectivity(self, switch_entity):
        """
        Updated the setup connectivity for the switch entity.
        update the aliases for the switch connectivity.
        :param switch_entity: a SwitchTopologyEntity
        :return: None
        """
        for switch_port, port_neighbor_info in switch_entity.lldp_connectivity.items():
            neighbor_hostname = port_neighbor_info['neighbor_hostname']
            neighbor_port = port_neighbor_info['neighbor_port']
            neighbor_entity = self.setup_entities[neighbor_hostname]
            self.update_connectivity(switch_entity, switch_port, neighbor_entity, neighbor_port)
            connection_port_alias = self.get_switch_connectivity_alias(switch_entity, switch_port,
                                                                       neighbor_entity, neighbor_port)
            switch_entity.update_port_alias(switch_port, connection_port_alias)

    def update_connectivity(self, entity_1, entity_1_port, entity_2, entity_2_port):
        """
        update the setup_connectivity dict, that contains all the conductivities of the setup.
        :param entity_1:  a TopologyEntity
        :param entity_1_port: entity 1 port name
        :param entity_2: a TopologyEntity
        :param entity_2_port: entity 2 port name
        :return: None
        Example of self.setup_connectivity = {
           "r-sonic-08-p1p1" : "r-tigris-06-etp64"
           ...
           }
        """
        connectivity_link_name_template = "{}-{}"
        entity_1_port_id = entity_1.ports_info[entity_1_port]['id']
        entity_2_port_id = entity_2.ports_info[entity_2_port]['id']
        entity_1_link = connectivity_link_name_template.format(entity_1.hostname, entity_1_port_id)
        entity_2_link = connectivity_link_name_template.format(entity_2.hostname, entity_2_port_id)
        if not self.is_connectivity_duplication(entity_1_link, entity_2_link):
            self.setup_connectivity[entity_1_link] = entity_2_link

    def is_connectivity_duplication(self, link_1, link_2):
        """
        checks if duplicates connectivity exist in self.setup_connectivity.
        for example: if self.setup_connectivity = { "r-tigris-06-etp64" :  "r-sonic-08-p1p1"}
        the function return False because there's no need to add {"r-sonic-08-p1p1" : "r-tigris-06-etp64"}
        to self.setup_connectivity.
        :param link_1: link name, e.g. "r-sonic-08-p1p1"
        :param link_2: link name, e.g. "r-tigris-06-etp64"
        :return: True if this connectivity duplication exist, otherwise false
        """
        return self.setup_connectivity.get(link_2) == link_1

    def get_connectivity_alias(self, main_entity, neighbor_entity, neighbor_port):
        """
        :param main_entity: a TopologyEntity
        :param neighbor_entity: a TopologyEntity
        :return: the connectivity alias between those entities. e.g "ha-hb-1"/"ha-sa-1"
        """
        connectivity_alias_prefix = "{}-{}".format(main_entity.alias, neighbor_entity.alias)
        neighbor_entity_port_info = neighbor_entity.ports_info[neighbor_port]
        neighbor_port_connection_alias = neighbor_entity_port_info.get('connection_alias')
        if neighbor_port_connection_alias:
            connection_alias_number_pattern = "{}-{}-(\d+)".format(neighbor_entity.alias, main_entity.alias)
            connection_alias_number = re.search(connection_alias_number_pattern, neighbor_port_connection_alias, re.IGNORECASE).group(1)
        else:
            connection_alias_number = self.get_and_inc_connectivity_alias_count(connectivity_alias_prefix)
        connectivity_alias = "{}-{}".format(connectivity_alias_prefix, connection_alias_number)
        return connectivity_alias

    def get_switch_connectivity_alias(self, switch_entity, switch_port_name, neighbor_entity, neighbor_port_name):
        """
        :param switch_entity:  a SwitchTopologyEntity
        :param switch_port_name: switch port name
        :param neighbor_entity: a TopologyEntity
        :param neighbor_port_name: neighbor port name
        :return: the alias for the switch port, e.g. "dut-lb4-1"/"dut-splt4-p1-1"..
        """
        switch_entity_port_info = switch_entity.ports_info[switch_port_name]
        neighbor_entity_port_info = neighbor_entity.ports_info[neighbor_port_name]
        if self.is_loopback_connectivity(switch_entity, neighbor_entity):
            if self.is_split_loopback_connectivity(switch_entity_port_info, neighbor_entity_port_info):
                connection_port_alias = self.get_split_loopback_connectivity_alias(switch_entity,
                                                                                   switch_entity_port_info,
                                                                                   neighbor_entity_port_info)
            else:
                connection_port_alias = self.get_loopback_connectivity_alias(switch_entity,
                                                                             switch_entity_port_info,
                                                                             neighbor_entity_port_info)
        elif isinstance(neighbor_entity, SwitchTopologyEntity):
            connection_port_alias = self.get_switches_connectivity_alias(switch_entity,
                                                                         switch_entity_port_info,
                                                                         neighbor_entity,
                                                                         neighbor_entity_port_info)
        else:
            connection_port_alias = self.get_connectivity_alias(switch_entity, neighbor_entity, neighbor_port_name)
        return connection_port_alias

    def get_split_loopback_connectivity_alias(self, switch_entity, switch_entity_port_info, neighbor_entity_port_info):
        """
        :param switch_entity: a SwitchTopologyEntity
        :param switch_entity_port_info: a dictionary with the switch port info
        :param neighbor_entity_port_info: a dictionary with the neighbor port info
        :return: the alias for the split loopback port, e.g "dut-splt4-p1-1"
        """
        split_loopback_template = "{}-lb{}-splt{}-p{}-{}"
        split_number = switch_entity_port_info['split_num']
        port_split_num = switch_entity_port_info['port_split_number']
        neighbor_port_connection_alias = neighbor_entity_port_info.get('connection_alias')
        if neighbor_port_connection_alias:
            loopback_number_pattern = "{}-lb(\d+)-splt{}".format(switch_entity.alias, split_number)
            lb_number = re.search(loopback_number_pattern, neighbor_port_connection_alias, re.IGNORECASE).group(1)
        else:
            loopback_alias_template = "{}-lb-splt{}-{}".format(switch_entity.alias, split_number, port_split_num)
            lb_number = self.get_and_inc_connectivity_alias_count(loopback_alias_template)
        lb_port_num = self.get_loopback_port_number(switch_entity_port_info, neighbor_entity_port_info)
        connection_port_alias = split_loopback_template.format(switch_entity.alias, lb_number, split_number,
                                                               lb_port_num, port_split_num)
        return connection_port_alias

    def get_loopback_connectivity_alias(self, switch_entity, switch_entity_port_info, neighbor_entity_port_info):
        """
        :param switch_entity: a SwitchTopologyEntity
        :param switch_entity_port_info: a dictionary with the switch port info
        :param neighbor_entity_port_info: a dictionary with the neighbor port info
        :return: the alias for the loopback port, e.g "dut-lb4-1"
        """
        loopback_template = "{}-lb{}-{}"
        neighbor_port_connection_alias = neighbor_entity_port_info.get('connection_alias')
        if neighbor_port_connection_alias:
            loopback_number_pattern = "{}-lb(\d+)".format(switch_entity.alias)
            lb_number = re.search(loopback_number_pattern, neighbor_port_connection_alias, re.IGNORECASE).group(1)
        else:
            loopback_alias_template = "{}-lb".format(switch_entity.alias)
            lb_number = self.get_and_inc_connectivity_alias_count(loopback_alias_template)
        lb_port_num = self.get_loopback_port_number(switch_entity_port_info, neighbor_entity_port_info)
        connection_port_alias = loopback_template.format(switch_entity.alias, lb_number, lb_port_num)
        return connection_port_alias

    def get_switches_connectivity_alias(self, switch_entity, switch_entity_port_info,
                                        neighbor_switch_entity, neighbor_switch_entity_port_info):
        """
        :param switch_entity: a SwitchTopologyEntity
        :param switch_entity_port_info:  a dictionary with the switch port info
        :param neighbor_switch_entity: a SwitchTopologyEntity of the neighbor switch.
        :param neighbor_switch_entity_port_info: a dictionary with the neighbor port info
        :return: the alias for the port connectivity between switches, e.g. "sr-sl-splt-1"/"sr-splt-2"
        """
        port_1_is_split = switch_entity_port_info.get('is_split')
        port_2_is_split = neighbor_switch_entity_port_info.get('is_split')
        if not port_1_is_split and not port_2_is_split:
            connectivity_alias = self.get_connectivity_alias(switch_entity, neighbor_switch_entity)
        elif port_1_is_split and not port_2_is_split:
            split_template = "{}-splt-{}"
            port_split_num = switch_entity_port_info['port_split_number']
            connectivity_alias = split_template.format(switch_entity.alias, port_split_num)
        else:
            # not port_1_is_split and port_2_is_split
            split_template = "{}-{}-splt-{}"
            port_split_num = switch_entity_port_info['port_split_number']
            connectivity_alias = split_template.format(switch_entity.alias,
                                                       neighbor_switch_entity.alias, port_split_num)
        return connectivity_alias

    @staticmethod
    def is_split_loopback_connectivity(entity_1_port_info, entity_2_port_info):
        """
        :param entity_1_port_info: a dictionary with the port info
        :param entity_2_port_info: a dictionary with the port info
        :return: True if both ports are split
        """
        port_1_is_split = entity_1_port_info.get('is_split')
        port_2_is_split = entity_2_port_info.get('is_split')
        return port_1_is_split and port_2_is_split

    @staticmethod
    def is_loopback_connectivity(switch_entity, neighbor_entity):
        """
        :param switch_entity: a SwitchTopologyEntity
        :param neighbor_entity: a TopologyEntity
        :return: True if the neighbor entity is the switch itself
        """
        return switch_entity is neighbor_entity

    @staticmethod
    def get_loopback_port_number(loopback_port_1_info, loopback_port_2_info):
        """
        :param loopback_port_1_info: a dictionary with the port info
        :param loopback_port_2_info: a dictionary with the port info
        :return: the port number in the loopback, for example,
        if Ethernet0 and Ethernet4 are connected loopback,
        Ethernet0 will be port 1 and Ethernet4 will be port 2.
        """
        lb_port_num_1 = int(loopback_port_1_info['port_num'])
        lb_port_num_2 = int(loopback_port_2_info['port_num'])
        if lb_port_num_1 < lb_port_num_2:
            return 1
        else:
            return 2

    def get_and_inc_connectivity_alias_count(self, connectivity_alias):
        """
        update the count for that alias and return the updated alias count.
        for example: if self.port_aliases_counter= {"ha-dut": 1, ... }
        for connectivity_alias "ha-dut" the function will update the count to 2,
        self.port_aliases_counter= {"ha-dut": 2, ... } and return 2.
        :param connectivity_alias: an alias for a port in setup, e.g. "dut-ha"
        :return: the count of this alias in the setup and update th
        """
        alias_count = self.port_aliases_counter.get(connectivity_alias)
        if alias_count is None:
            alias_count = 1
            self.port_aliases_counter[connectivity_alias] = alias_count
        else:
            alias_count += 1
            self.port_aliases_counter[connectivity_alias] = alias_count
        return alias_count

    def create_tmp_topology_dir(self):
        """
        creates a temporary dir for the topology setup files.
        :return: None
        """
        # change this file location to different shared location
        self.topology_dir_path = "/auto/sw_regression/system/SONIC/MARS/conf/topo/{}".format(self.setup_name)
        logger.info('Creating new topology files here: {0}'.format(os.path.join(os.getcwd(), self.topology_dir_path)))
        if not os.path.exists(self.topology_dir_path):
            os.system("sudo mkdir {}".format(self.topology_dir_path))
        os.system("sudo chmod 777 {}".format(self.topology_dir_path))

    def create_sonic_setup_dirs(self):
        """
        creates the dir for the sonic .setup file and the sonic topology setup file.
        :return: None
        """
        self.sonic_setup_dir = self.sonic_setup_dir.format(self.setup_name)
        self.sonic_topology_dir = self.sonic_topology_dir.format(self.setup_name)
        logger.info('Creating setup file here: {0}'.format(self.sonic_setup_dir))
        if not os.path.exists(self.sonic_setup_dir):
            os.system("sudo mkdir {}".format(self.sonic_setup_dir))
        os.system("sudo chmod 777 {}".format(self.sonic_setup_dir))
        logger.info('Creating setup topology file here: {0}'.format(self.sonic_topology_dir))
        if not os.path.exists(self.sonic_topology_dir):
            os.system("sudo mkdir {}".format(self.sonic_topology_dir))
        os.system("sudo chmod 777 {}".format(self.sonic_topology_dir))

    def create_topology_files(self):
        self.create_tmp_topology_dir()
        for entity_ip, entity in self.setup_entities.items():
            entity.create_entity_xml(self.topology_dir_path)
        self.create_topology_xml()

    def create_topology_xml(self):
        template = get_xml_template('topology_template.txt')
        connections = [{'link1': link1, 'link2': link2} for link1, link2 in self.setup_connectivity.items()]
        output = template.render(hosts=self.hosts.values(),
                                 switches=self.switches.values(),
                                 sonic_mgmt=self.setup_entities['sonic_mgmt'],
                                 connections=connections)
        new_topology_path = os.path.join(self.topology_dir_path, 'topology.xml')
        create_file(new_topology_path, output)

    def create_setup_files(self):
        self.create_sonic_setup_dirs()
        sonic_topology_template = get_xml_template('sonic_topology_template.txt')
        sonic_topology_output = sonic_topology_template.render(hosts=self.hosts.values(),
                                                               switches=self.switches.values(),
                                                               hypervisor=self.setup_entities['hypervisor'],
                                                               sonic_mgmt=self.setup_entities['sonic_mgmt'])
        new_setup_topology_file_path = os.path.join(self.sonic_topology_dir, 'topology.xml')
        create_file(new_setup_topology_file_path, sonic_topology_output, set_permission='666')
        setup_template_file = 'simx_setup_template.txt' if 'simx' in self.setup_name else 'setup_template.txt'
        sonic_setup_template = get_xml_template(setup_template_file)
        sonic_setup_output = sonic_setup_template.render(hypervisor=self.setup_entities['sonic_mgmt'], tm=self, dut=self.dut)
        new_setup_file_path = os.path.join(self.sonic_setup_dir, '{}.setup'.format(self.setup_name))
        create_file(new_setup_file_path, sonic_setup_output, set_permission='666')
        self.create_ci_build_setup_files()

    def create_ci_build_setup_files(self):
        if 'CI' in self.setup_name:
            switch_entity = list(self.switches.values()).pop()
            chip_type = switch_entity.chip_type
            chip_type = "{}1".format(chip_type) if chip_type == 'SPC' else chip_type
            ci_setup_template_file = 'ci_setup_template.txt'
            release_setup_template_file = 'release_setup_template.txt'
            if 'simx' in self.setup_name:
                ci_setup_template_file = 'simx_ci_setup_template.txt'
                release_setup_template_file = 'simx_release_setup_template.txt'
            ci_sonic_setup_template = get_xml_template(ci_setup_template_file)
            ci_sonic_setup_output = ci_sonic_setup_template.render(hypervisor=self.setup_entities['sonic_mgmt'],
                                                                   tm=self, dut=self.dut)
            new_setup_file_path = os.path.join(self.sonic_setup_dir, 'SONIC_{}_mini_mars_ci.setup'.format(chip_type))
            create_file(new_setup_file_path, ci_sonic_setup_output, set_permission='666')
            release_sonic_setup_template = get_xml_template(release_setup_template_file)
            release_sonic_setup_output = \
                release_sonic_setup_template.render(hypervisor=self.setup_entities['sonic_mgmt'],
                                                    tm=self, dut=self.dut)
            new_setup_file_path = os.path.join(self.sonic_setup_dir, 'SONIC_{}_mini_mars_release.setup'.format(chip_type))
            create_file(new_setup_file_path, release_sonic_setup_output, set_permission='666')


    def creat_json_file_to_noga(self):
        self.collect_data_for_noga()
        file_name = '/tmp/{}.json'.format(self.setup_name)
        with open(file_name, "w") as f:
            json.dump(self.noga_dict, f, indent=1)
        self.noga_json_file_path = file_name

    def collect_data_for_noga(self):
        """
        @summary: collection information about link host switches aliases, to be sent to NOGA
        :param topology: dictionary which is all results from create_topology. Based on lldp protocol.
        :return: dictionary with all info. In format
        {
        TopoDictConst.Switches: {TopoDictConst.Alias: value
                    TopoDictConst.Links:{name_of_link: alias}}
        TopoDictConst.Hosts: {TopoDictConst.Alias: value
                  TopoDictConst.Links:{name_of_link: alias}}
        }
        """
        self.noga_dict = {"switches": {}, "hosts": {}}
        self.get_devices_noga_data()

    def get_devices_noga_data(self):
        """
        @summary: Prepare information about link, host, switches, to be sent to NOGA
        :param topology: dictionary which is all results from create_topology. Based on lldp protocol. Onlu switch part
        :param self.noga_dict: dictionary with all data to be sent to noga
        :return: self.noga_dict
        """
        for switch in self.switches.values():
            self.noga_dict['switches'].update({switch.ip: {'alias': switch.alias, 'links': {}}})
            for port_alias, port_info_dict in switch.ports_info.items():
                self.noga_dict['switches'][switch.ip]['links']["{} - {}-{}".format(switch.ip, switch.hostname, port_alias)] = port_info_dict['connection_alias']
        for host in self.hosts.values():
            self.noga_dict['hosts'].update({host.hostname: {'alias': host.alias, 'links': {}}})
            for port_mac, port_info_dict in host.ports_info.items():
                self.noga_dict['hosts'][host.hostname]['links']["{} - {}-{}".format(host.ip, host.hostname, port_info_dict['if'])] = port_info_dict['connection_alias']
        hypervisor = self.setup_entities['hypervisor']
        sonic_mgmt = self.setup_entities['sonic_mgmt']
        self.noga_dict['hosts'].update({hypervisor.hostname: {'alias': hypervisor.alias, 'links': {}}})
        self.noga_dict['hosts'].update({sonic_mgmt.hostname: {'alias': sonic_mgmt.alias, 'links': {}}})

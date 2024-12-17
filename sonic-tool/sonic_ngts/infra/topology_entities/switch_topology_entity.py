import re
import logging
import json
import os
from infra.engines.ssh.ssh_engine import SSH
from infra.topology_entities.topology_entity_interface import TopologyEntityInterface
from infra.constants.chassis_consts import ChassisConst
from infra.exceptions.entity_exception import TopologyEntityError
from infra.utilities.topology_util import *
from infra.constants.constants import ConfigDbJsonConst, SonicConsts
#
# create a logger for this class
#
logger = logging.getLogger("switch_topology_entity")


class SwitchTopologyEntity(TopologyEntityInterface):
    """
    SwitchTopologyEntity
    Store all the information about the switch entity in sonic setup.
    creates the switch .xml file.
    """

    def __init__(self, ip, username, password, alias):
        self.ip = ip
        self.username = username
        self.password = password
        self.alias = alias
        self.engine = SSH(ip=self.ip, username=self.username, password=self.password)
        self.hostname = None
        self.system_type = None
        self.chip_type = None
        self.HwSKU = None
        self.mac = None
        self.config_db = None
        self.port_number = None
        self.ports_info = {}
        self.lldp_connectivity = {}
        self.set_entity_info()

    def set_entity_info(self):
        """
        set all the information for the switch entity.
        :return: None
        """
        logger.info("Starting setting switch entity {}.\n".format(self.ip))
        self.set_config_db()
        self.set_HwSKU()
        self.set_hostname()
        self.set_mac_address()
        self.set_switch_type()
        self.set_chip_type()
        self.set_switch_number_of_ports()
        self.verify_lldp()
        self.get_lldp_connectivity()

    def set_config_db(self):
        """
        set the json dict config_db of the switch.
        :return: None
        """
        logger.info("Take switch configuration from /etc/sonic/config_db.json")
        if not os.path.exists("/tmp"):
            os.system("sudo mkdir /tmp")
        os.system("sudo chmod 777 /tmp")
        self.engine.copy_file_from_host(src_path='/etc/sonic/config_db.json',dst_path="/tmp/config_db.json")
        with open("/tmp/config_db.json", 'r') as file:
            self.config_db = json.load(file)

    def set_HwSKU(self):
        """
        set the switch HwSKU.
        :return: None
        """
        self.HwSKU = self.config_db[ConfigDbJsonConst.DEVICE_METADATA][ConfigDbJsonConst.LOCALHOST][ConfigDbJsonConst.HWSKU]

    def set_hostname(self):
        """
        set the switch hostname.
        :return: None
        """
        self.hostname = self.engine.run_cmd('hostname')

    def set_mac_address(self):
        """
        set the switch mac address.
        :return: None
        """
        self.mac = self.config_db[ConfigDbJsonConst.DEVICE_METADATA][ConfigDbJsonConst.LOCALHOST][ConfigDbJsonConst.MAC]

    def set_switch_type(self):
        """
        find and set the switch type.
        :return: None. raise exception if the switch type was not found.
        """
        for switch_type, fru_list in ChassisConst.CHASSIS_TO_TYPE_DICT.items():
            for fru in fru_list:
                # Get FRU part. Ex. from ACS-MSN4600C get 4600C, Mellanox-SN4280-O28 get 4280
                current_hwsku_fru = re.search("SN(\d[^-]+)", self.HwSKU).group(1)
                if fru.lower() == current_hwsku_fru.lower():
                    logger.info('switch type found: {}'.format(switch_type))
                    self.system_type = switch_type
                    break
        if self.system_type is None:
            raise TopologyEntityError("System type for switch {} with HwSKU {} was not found."
                                      .format(self.ip, self.HwSKU))

    def set_chip_type(self):
        """
        set switch chip type.
        :return: None
        """
        self.chip_type = ChassisConst.MAIN_FRU_DIC[self.system_type]['chip_type']

    def set_switch_number_of_ports(self):
        """
        set switch number of ports.
        :return: None
        """
        self.port_number = ChassisConst.MAIN_FRU_DIC[self.system_type]['port_number']

    def verify_lldp(self):
        """
        verify lldp is configured on the switch.
        :return: None. raise exception if the switch lldp is not enabled.
        """
        lldp_state = self.config_db[ConfigDbJsonConst.FEATURE][ConfigDbJsonConst.LLDP][ConfigDbJsonConst.STATE]
        if lldp_state != 'enabled':
            raise TopologyEntityError("LLDP is not configured on switch {}.".format(self.ip))

    def get_lldp_connectivity(self):
        """
        update the lldp_connectivity dictionary.
        :return: None.
        example of self.lldp_connectivity =
        { 'etp62': {'neighbor_hostname': 'r-tigris-06',
                    'neighbor_port': 'etp61'},
          'etp64': {'neighbor_hostname': 'r-sonic-08',
                    'neighbor_port': '0c:42:a1:a9:72:f6'}}
        """
        lldp_dict_res = {}
        output_list = self.parse_lldp_table_output()
        for tuple_info in output_list:
            port_name, remote_device_hostname, remote_device_port = tuple_info
            port_alias = self.get_port_alias(port_name)
            lldp_dict_res[port_alias] = {"neighbor_hostname": remote_device_hostname,
                                         "neighbor_port": remote_device_port}
            self.update_port_info(port_name)

        self.lldp_connectivity = lldp_dict_res

    def get_port_alias(self, port_name):
        """
        :param port_name: the port name, e.g. Ethernet0
        :return: the port sonic alias, e.g. etp1
        """
        return self.config_db['PORT'][port_name]['alias']

    def parse_lldp_table_output(self):
        """
        parse the output of the "show lldp table" command.
        :return: return a list of tuples, where each tuple is (LocalPort,RemoteDevice,RemotePortID)
        based on the "show lldp table" output,
        e.g [(Ethernet0,r-tigris-06,etp2),(Ethernet248,r-sonic-08,0c:42:a1:a9:72:f7),..]
        """
        lldp_table_output = self.engine.run_cmd(SonicConsts.SHOW_LLDP_TABLE)
        output_list = []
        for line in lldp_table_output.splitlines():
            if line.startswith('Ethernet'):
                lldp_line_data = line.split()
                local_port, remote_device, remote_port = lldp_line_data[0:3]
                port_data = (local_port, remote_device, remote_port)
                output_list.append(port_data)

        return output_list

    def update_port_info(self, port_name):
        """
        update the ports_info dictionary.
        Example of self.ports_info =
        {'etp1': {'admin_status': 'up', 'alias': 'etp1', 'description': 'ARISTA01T0:Ethernet1', 'index': '1',
                  'lanes': '0,1,2,3', 'mtu': '9100', 'pfc_asym': 'off', 'speed': '10000', 'if': 'Ethernet0',
                  'port_num': '0', 'is_split': False, 'id': 'etp1'}, ...}

        :param port_name: the port interface name, e.g Ethernet0
        :return: None
        """
        port_info_dict = self.config_db[ConfigDbJsonConst.PORT][port_name]
        port_alias = port_info_dict['alias']
        self.ports_info[port_alias] = port_info_dict
        self.ports_info[port_alias]['if'] = port_name
        self.ports_info[port_alias]['port_num'] = self.get_switch_port_number(port_name)
        self.ports_info[port_alias]['is_split'] = bool(re.match('etp\d+([A-z])', port_alias))
        if self.ports_info[port_alias]['is_split']:
            self.ports_info[port_alias]['split_num'] = self.get_split_number(port_alias)
            self.ports_info[port_alias]['port_split_number'] = self.get_port_split_number(port_alias)
        self.ports_info[port_alias]['id'] = port_alias

    def get_split_number(self, port_alias):
        """
        return the port split number, as the port was split to 2/4/8.
        :param port_alias: the sonic port alias, e.g. 'etp1'
        :return: the number the port was split to, 2/4/8.
        """
        all_aliases = [port_info['alias'] for port_info in self.config_db[ConfigDbJsonConst.PORT].values()]
        port_alias_number = self.get_alias_number(port_alias)
        all_aliases_of_split_port = list(filter(lambda alias: re.search("etp{}[a-z]$".format(port_alias_number), alias), all_aliases))
        split_number = len(all_aliases_of_split_port)
        return split_number

    @staticmethod
    def get_switch_port_number(port_name):
        """
        :param port_name: the port interface name, e.g Ethernet0
        :return: the number of the port, e.g. 0
        """
        return re.search("Ethernet(\d+)", port_name, re.IGNORECASE).group(1)

    @staticmethod
    def get_alias_number(port_alias):
        """
        :param port_alias:  the sonic port alias, e.g. 'etp1'
        :return: the number in the alias, e.g. 1
        """
        return re.search('etp(\d*)', port_alias).group(1)

    @staticmethod
    def get_alias_letter(port_alias):
        """
        :param port_alias:  the sonic port alias, e.g. 'etp1a'
        :return: the letter in the alias, e.g. a/b/c/d/e/f/g/h
        """
        return re.search('etp\d+([A-z])', port_alias).group(1)

    def get_port_split_number(self, port_alias):
        alias_letter = self.get_alias_letter(port_alias)
        if alias_letter == 'a':
            return 1
        elif alias_letter == 'b':
            return 2
        elif alias_letter == 'c':
            return 3
        elif alias_letter == 'd':
            return 4
        elif alias_letter == 'e':
            return 5
        elif alias_letter == 'f':
            return 6
        elif alias_letter == 'g':
            return 7
        elif alias_letter == 'h':
            return 8

    def update_port_alias(self, port, connection_port_alias):
        """
        update the port connection alias.
        :param port: port name. e.g "Ethernet0"
        :param connection_port_alias: port connection alias. e.g "dut-ha-1"
        :return: None.
        """
        self.ports_info[port]['connection_alias'] = connection_port_alias

    def get_port_sonic_alias(self, port_name):
        """
        :param port_name: port name. e.g "Ethernet0"
        :return: the sonic port alias, e.g. 'etp1'
        """
        for port_alias, port_info in self.ports_info.items():
            if port_info['if'] == port_name:
                return port_alias
        raise TopologyEntityError("Could not find the sonic alias for port {}\n".format(port_name))

    def create_entity_xml(self, path):
        """
        create the SWITCH .xml file in path.
        :param path: the path where the entity xml file will be.
        :return: None
        """
        template = get_xml_template('switch_template.txt')
        output = template.render(switch=self, ports=self.ports_info.values())
        new_entity_xml_file_path = os.path.join(path, '{}.xml'.format(self.hostname))
        create_file(new_entity_xml_file_path, output)

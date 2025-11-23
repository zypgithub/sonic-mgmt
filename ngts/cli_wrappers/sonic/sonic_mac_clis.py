import re

from ngts.cli_wrappers.common.mac_clis_common import MacCliCommon
from ngts.cli_wrappers.sonic.sonic_multi_asic_cli import SonicMultiAsicCli
from ngts.helpers.network import generate_mac
from ngts.cli_util.cli_parsers import generic_sonic_output_parser

FDB_AGING_TIME_FILE = "/etc/swss/config.d/switch.json"


class SonicMacCli(MacCliCommon, SonicMultiAsicCli):

    def __init__(self, engine, asic_id=None):
        SonicMultiAsicCli.__init__(self, engine, asic_id)

    def show_mac(self):
        """
        This method runs 'show mac' command
        :return: command output
        """
        return self.engine.run_cmd(f'show mac {self.multi_asic_config_cmd_ext}')

    @staticmethod
    def generate_fdb_config(entries_num, vlan_id, iface, op, fdb_type="dynamic"):
        """ Generate FDB config.
        Generated config template:
        [
            {
                "FDB_TABLE:Vlan[VID]:XX-XX-XX-XX-XX-XX": {
                    "port": [Interface],
                    "type": "dynamic"
                },
                "OP": ["SET"|"DEL"]
            }
        ]
        :param entries_num: number of fdb entries
        :param vlan_id: VLAN name
        :param iface: interface name
        :param op: config DEL or SET operation
        :param fdb_type: fdb type (dynamic/static)
        """
        fdb_config_json = []
        entry_key_template = "FDB_TABLE:Vlan{vid}:{mac}"

        for mac_address in generate_mac(entries_num):
            fdb_entry_json = {entry_key_template.format(vid=vlan_id, mac=mac_address):
                              {"port": iface, "type": fdb_type},
                              "OP": op
                              }
            fdb_config_json.append(fdb_entry_json)
        return fdb_config_json

    def clear_fdb(self):
        """
        This method is to clear fdb table
        :return: command output
        """
        return self.engine.run_cmd('sudo sonic-clear fdb all', validate=True)

    def set_fdb_aging_time(self, fdb_aging_time):
        """
        This method is to set fdb aging time
        :param fdb_aging_time: fdb aging time
        :return: command output
        """
        cmd_copy_file_from_swss_to_switch = f"docker cp swss{self.multi_asic_docker_cmd_ext}:{FDB_AGING_TIME_FILE} /tmp/"
        self.engine.run_cmd(cmd_copy_file_from_swss_to_switch)

        replace_fdb_aging_time = f"sudo sed -i 's/ \"fdb_aging_time\": \".*\"/\"fdb_aging_time\": \"{fdb_aging_time}\"/' /tmp/switch.json"
        self.engine.run_cmd(replace_fdb_aging_time)

        cmd_copy_file_from_switch_to_swss = f"docker cp /tmp/switch.json swss{self.multi_asic_docker_cmd_ext}:{FDB_AGING_TIME_FILE}"
        self.engine.run_cmd(cmd_copy_file_from_switch_to_swss)
        cmd_config_swss_config = f'docker exec swss{self.multi_asic_docker_cmd_ext} bash -c "swssconfig {FDB_AGING_TIME_FILE}"'
        self.engine.run_cmd(cmd_config_swss_config)

    def get_fdb_aging_time(self):
        """
        This method is to set fdb aging time
        :return: fdb aging time
        """
        regrex_time = re.compile(r"[\"']?(?P<time>\d+)[\"']?")
        if self.asic_id is not None:
            cmd_get_fdb_aging_time = f'sonic-db-cli {self.multi_asic_config_cmd_ext} APPL_DB hget "SWITCH_TABLE:switch" "fdb_aging_time"'
        else:
            cmd_get_fdb_aging_time = 'redis-cli -n 0 hget "SWITCH_TABLE:switch" fdb_aging_time'
        output = self.engine.run_cmd(cmd_get_fdb_aging_time, validate=True)
        fdb_aging_time = regrex_time.search(output)
        return fdb_aging_time.groupdict()["time"] if fdb_aging_time else "nil"

    def parse_mac_table(self, option=""):
        """
        This method is to parse mac table info
        e.g.:
        No.    Vlan  MacAddress         Port         Type
        -----  ------  -----------------  -----------  -------
        1      40  98:03:9B:9B:3B:22  Ethernet248  Dynamic
        2      40  98:03:9B:9B:3B:23  Ethernet0    Dynamic
        3      40  0C:42:A1:C0:99:2E  Ethernet504  Dynamic

        :param option: show mac option, such as -v or -p
        :return: command output like below
        {'1': {'No.': '1', 'Vlan': '40', 'MacAddress': '0C:42:A1:B4:CC:E8', 'Port': 'Ethernet0', 'Type': 'Dynamic'},
         '2': {'No.': '2', 'Vlan': '40', 'MacAddress': '0C:42:A1:B4:D7:E8', 'Port': 'Ethernet40', 'Type': 'Dynamic'},
         '3': {'No.': '3', 'Vlan': '40', 'MacAddress': '00:00:00:00:00:01', 'Port': 'Ethernet0', 'Type': 'Dynamic'},
        }
        """
        mac_table = self.engine.run_cmd(f'sudo show mac {self.multi_asic_config_cmd_ext} {option}', validate=True)
        mac_table_dict = generic_sonic_output_parser(mac_table,
                                                     headers_ofset=0,
                                                     len_ofset=1,
                                                     data_ofset_from_start=2,
                                                     data_ofset_from_end=-1,
                                                     column_ofset=2,
                                                     output_key='No.')
        return mac_table_dict

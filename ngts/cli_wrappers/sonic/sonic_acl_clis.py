from ngts.cli_util.cli_parsers import generic_sonic_output_parser
from jinja2 import Environment, FileSystemLoader
import json
import os


class SonicAclCli:

    def __init__(self, engine):
        self.engine = engine

    def create_table(self, tbl_name, tbl_type, description, stage, ports=None):
        """
        Creates ACL table from SONIC
        :param tbl_name: ACL table name
        :param tbl_type: ACL table type [L3, MIRROR, MIRROR_DSCP, etc.]
        :param description: ACL table description
        :param stage: ACL table stage [ingress|egress]
        :param ports: The list of ports to which this ACL table is applied, if None - all ports will be used
        :return: command output
        """
        cmd = f'sudo config acl add table {tbl_name} {tbl_type} --description={description} --stage={stage}'
        if ports:
            ports = ','.join(ports)
            cmd += f' --ports={ports}'

        return self.engine.run_cmd(cmd)

    def remove_table(self, tbl_name):
        """
        Creates ACL table from SONIC
        :param tbl_name: ACL table name
        :return: command output
        """
        cmd = f'sudo config acl remove table {tbl_name}'

        return self.engine.run_cmd(cmd)

    def apply_config(self, cfg_path):
        """
        On DUT applies ACL config defined in file 'cfg_path'
        :param cfg_path: Path to the ACL config file stored on DUT
        :return: command output
        """
        return self.engine.run_cmd(f"acl-loader update full {cfg_path}")

    def apply_acl_rules(self, cfg_path):
        """
        On DUT applies ACL config defined in file 'cfg_path'
        :param cfg_path: Path to the ACL config file stored on DUT
        :return: command output
        """
        return self.engine.run_cmd(f'sonic-cfggen -j {cfg_path} --write-to-db')

    def delete_config(self):
        """
        On DUT removes current ACL configuration
        :return: command output
        """
        return self.engine.run_cmd('acl-loader delete')

    def config_null_route_helper(self, tbl_name, src_ip, action):
        """
        Block/unblock src_ip
        :param tbl_name: ACL table name
        :param src_ip: src ip address
        :param action: block/unblock
        :return: command output
        """
        return self.engine.run_cmd(f'sudo null_route_helper {tbl_name} {src_ip} {action}')

    def show_acl_table(self):
        """
        Show acl tables
        :return: command output
        """
        return self.engine.run_cmd('show acl table')

    def show_and_parse_acl_table(self):
        """
        Show acl tables
        :return: dictionary with table name as key
                    Example: return of the 'show acl table':
                        Name                   Type    Binding      Description            Stage
                        ---------------------  ------  -----------  ---------------------  -------
                        DATA_EGRESS_L3TEST     L3      Ethernet236  DATA_EGRESS_L3TEST     egress
                        DATA_INGRESS_L3V6TEST  L3V6    Ethernet236  DATA_INGRESS_L3V6TEST  ingress
                    output:
                    {
                        'DATA_EGRESS_L3TEST':{
                            'Name': 'DATA_EGRESS_L3TEST',
                            'Type'; 'L3',
                            'Binding': 'Ethernet236',
                            'Description': 'DATA_EGRESS_L3TEST',
                            'Stage': 'egress'
                        },
                        'DATA_INGRESS_L3V6TEST':{
                            Name': 'DATA_INGRESS_L3V6TEST',
                            'Type'; 'L3V6',
                            'Binding': 'Ethernet236',
                            'Description': 'DATA_INGRESS_L3V6TEST',
                            'Stage': 'ingress'
                        }
                    }
        """
        acl_tables = self.show_acl_table()
        if not acl_tables:
            return {}
        acl_tables = generic_sonic_output_parser(acl_tables, headers_ofset=0, data_ofset_from_end=None, column_ofset=2,
                                                 output_key="Name")
        return acl_tables

    def show_acl_rule(self):
        """
        Show acl rules
        :return: command output
        """
        return self.engine.run_cmd('show acl rule')

    def show_and_parse_acl_rule(self):
        """
        Show acl rules
        :return: dictionary of the acl rules,
                examples: output of "show acl rule":
                        Table                  Rule    Priority    Action    Match
                        ---------------------  ------  ----------  --------  --------------------------
                        DATA_INGRESS_L3TEST    RULE_1  9999        FORWARD   ETHER_TYPE: 2048
                                                                             SRC_IP: 10.0.1.2/32
                        DATA_EGRESS_L3V6TEST   RULE_1  9999        FORWARD   SRC_IPV6: 80c0:a800::2/128
                the return dictionary:
                    {
                        'DATA_INGRESS_L3TEST': [
                            {'Table': 'DATA_INGRESS_L3TEST',
                            'Rule': 'RULE_1',
                            'Priority': '9999',
                            'Action': 'FORWARD',
                            'Match': ['ETHER_TYPE: 2048', 'SRC_IP: 10.0.1.2/32']}],
                        'DATA_EGRESS_L3V6TEST': [
                            {'Table': 'DATA_EGRESS_L3V6TEST',
                            'Rule': 'RULE_1',
                            'Priority': '9999',
                            'Action': 'FORWARD',
                            'Match': ['SRC_IPV6: 80c0:a800::2/128']}]
                    }

        """
        acl_rules = self.show_acl_rule()
        if not acl_rules:
            return []
        acl_rules = generic_sonic_output_parser(acl_rules, headers_ofset=0, data_ofset_from_end=None, column_ofset=2)
        acl_table_rules = {}
        for acl_rule in acl_rules:
            table_name = acl_rule['Table']
            if table_name not in acl_table_rules:
                acl_table_rules[table_name] = []
            if isinstance(acl_rule["Match"], str):
                acl_rule["Match"] = [acl_rule["Match"]]
            acl_table_rules[table_name].append(acl_rule)
        return acl_table_rules

    def show_acl_rules_counters(self, tbl_name):
        """
        Show acl rules
        :param tbl_name: ACL table name
        :return: command output
        """
        tbl = ''
        if tbl_name:
            tbl = f'-t {tbl_name}'

        return self.engine.run_cmd(f'sudo aclshow -a {tbl}')

    def show_and_parse_acl_rules_counters(self, tbl_name):
        """
        Show acl rules
        :param tbl_name: ACL table name
        :return: dictionary
                example:
                  the output of "aclshow -a":
                    RULE NAME    TABLE NAME               PRIO    PACKETS COUNT    BYTES COUNT
                    -----------  ---------------------  ------  ---------------  -------------
                    RULE_1       DATA_EGRESS_L3TEST       9999                0              0
                    RULE_1       DATA_EGRESS_L3V6TEST     9999                0              0
                  the return dictionary:
                    {
                        'DATA_EGRESS_L3TEST': [
                            {'RULE NAME': 'RULE_1',
                            'TABLE NAME': 'DATA_EGRESS_L3TEST',
                            'PRIO': '9999',
                            'PACKETS COUNT': '0',
                            'BYTES COUNT': '0'}],
                        'DATA_EGRESS_L3V6TEST': [
                            {'RULE NAME': 'RULE_1',
                            'TABLE NAME': 'DATA_EGRESS_L3V6TEST',
                            'PRIO': '9999',
                            'PACKETS COUNT': '0',
                            'BYTES COUNT': '0'}]
                    }
        """
        acl_rules = self.show_acl_rules_counters(tbl_name)
        if not acl_rules:
            return []
        acl_rules = generic_sonic_output_parser(acl_rules, headers_ofset=0, data_ofset_from_end=None, column_ofset=2)
        acl_table_rules = {}
        for acl_rule in acl_rules:
            table_name = acl_rule['TABLE NAME']
            if table_name not in acl_table_rules:
                acl_table_rules[table_name] = []
            acl_table_rules[table_name].append(acl_rule)
        return acl_table_rules

    def clear_acl_counters(self, tbl_name):
        """
        Show acl tables
        :param tbl_name: acl table name
        :return: command output
        """
        tbl = ''
        if tbl_name:
            tbl = f'-t {tbl_name}'

        return self.engine.run_cmd(f'sudo aclshow -c {tbl}')

    def remove_table_type(self, tbl_type_name):
        """
        Remove ACL table type from SONIC
        :param tbl_type_name: ACL table type name
        :return: command output
        """

        cmd = f'sonic-db-cli CONFIG_DB del "ACL_TABLE_TYPE|{tbl_type_name}"'
        return self.engine.run_cmd(cmd)

    def load_acl_rules_from_template(self, template_path, template_name, ports_list):
        """
        Load ACL rules from jinja template
        :param template_path: template path
        :param template_name: template name
        :param ports_list: ports list to apply the acl rules
        :return: command output
        """
        env = Environment(loader=FileSystemLoader(template_path))
        jinja_template = env.get_template(template_name)
        template_string = jinja_template.render(ports_list=ports_list)
        acl_conf = json.loads(template_string)
        acl_file_name = "acl.json"
        full_path = os.path.join("/tmp", acl_file_name)
        with open(full_path, 'w') as f:
            json.dump(acl_conf, f)
        self.engine.copy_file(source_file=full_path,
                              dest_file=acl_file_name,
                              file_system='/tmp',
                              direction='put'
                              )
        output = self.engine.run_cmd(f"sonic-cfggen -j /tmp/{acl_file_name}")
        return output

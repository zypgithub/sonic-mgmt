#!/usr/bin/local/python2.7

"""
Owner               : Sviatoslav Nastasiak <sviatoslavn@mellanox.com>

Created on          : Sep, 2018

Description         : Update noga setups with aliases.
                      Currently, aliasses are used for devsa
"""

#######################################################################
# global imports
#######################################################################

import argparse
import sys
import os
import socket
import json
import traceback

NOGA_API_LIB = "/.autodirect/sw_tools/Internal/Noga/RELEASE/latest/import/lib"


try:
    sys.path.append(NOGA_API_LIB)
    from noga_api import Noga_DB_API

except Exception as e:
    traceback.print_exc()


#######################################################################
# Functions
#######################################################################

#######################################################################
# Classes
#######################################################################

class GeneralResource(object):
    """
    @summary: abstract class which represent resource record in Noga database. Contain general methods
    Manages host and link type of devices.
    Please do not use inherited class for switch editing.
    """

    def __init__(self, name, device_type, alias, ip=None):
        """

        :param name: Name of a resource given from res_dict
        :param device_type: type of resource like: switch, host, link
        :param alias: alias getted from res_dict for current resource name
        """
        self.name = name
        self.type = device_type
        self.transaction_obj = Noga_DB_API()
        self.transaction_obj.set_cursor()
        self.alias = alias
        self.ip = ip
        self.custom_params = {}
        print("New GeneralResource: name: %s, type %s, alias %s" % (self.name, self.type, self.alias))

    def _collect_transaction_device_info(self):
        """
        @summary: collecting required information to edit Noga page. Like record id, record type id, etc.
        :return: tuple with a record id and record type id (Noga databases required values.)
        """
        rec_type = self.transaction_obj.res_type_by_name(self.type)
        rec_id = self.transaction_obj.find_matching_ids_by_attr(rec_type, "ip address", self.ip)[0]
        return (rec_type, rec_id)

    def import_alias(self):
        """
        @summary: will make an transaction to Noga.
        """
        # use description for backward compatability
        print("Import %s. type %s, alias %s" % (self.name, self.type, self.alias))
        res_params = {"name": self.name,
                      "Free_text": self.alias}
        res_params["description"] = self.alias
        for key, value in self.custom_params.items():
            if value is not None and value != "":
                res_params[key] = value
        (rec_id, rec_type) = self._collect_transaction_device_info()
        print("  record id %s record type id %s" % (rec_id, rec_type))
        print("  Update params params: %s" % res_params)
        self.transaction_obj.update_record_params(rec_type, rec_id, res_params)

    def set_custom_params(self, custom_params):
        self.custom_params = custom_params


class LinkResource(GeneralResource):
    """
    @summary: class inherited from Resource, with redefined method.
    """

    def __init__(self, name, alias):
        GeneralResource.__init__(self, name, "Port", alias)

    def _collect_transaction_device_info(self):
        rec_type = self.transaction_obj.res_type_by_name(self.type)
        rec_id = self.transaction_obj.find_matching_ids(self.name)[0]
        return (rec_id, rec_type)


class HostResource(GeneralResource):
    """
    @summary: class inherited from Resource, with redefined method.
    """

    def __init__(self, name, alias, ip):
        GeneralResource.__init__(self, name, "vm", alias, ip)

    def _collect_transaction_device_info(self):
        rec_type = self.transaction_obj.res_type_by_name(self.type)

        # TODO: Some VMs defined as server in noga. remove 'except' when fixing that issue
        try:
            rec_id = self.transaction_obj.find_matching_ids_by_attr(rec_type, "ip", self.ip)[0]
        except BaseException:
            print("Exception occurred while collecting host info")
            print("(PATCH): retry with \'server\' name....")
            rec_type = self.transaction_obj.res_type_by_name("server")
            rec_id = self.transaction_obj.find_matching_ids_by_attr(rec_type, "ip", self.ip)[0]

        return (rec_id, rec_type)


class SwitchResource(GeneralResource):
    """
    @summary: class inherited from Resource, with redefined method.
    """

    def __init__(self, name, alias, ip):
        GeneralResource.__init__(self, name, "switch", alias, ip)

    def _collect_transaction_device_info(self):
        rec_type = self.transaction_obj.res_type_by_name(self.type)
        rec_id = self.transaction_obj.find_matching_ids_by_attr(rec_type, "ip address", self.ip)[0]
        return (rec_id, rec_type)


def deserialize_json(json_file_path):
    """
    @summary: convert json dumped file into dictionary
    :param json_file_path: path to dictionary to edit.
    :return:
    """
    print("Deserialize Json. path: %s" % json_file_path)
    try:
        with open(json_file_path[0]) as f:
            data = json.load(f)
        if debug_en:
            print(json.dumps(data, indent=4, sort_keys=True))
        return data
    except OSError as e:
        print("%s. Can not open %s file\n"
                  "Additional debug info(working directory:)" % (e, json_file_path))
        os.system("pwd")


def fill_hosts(hosts_dict):
    """
    @summary: create a list of objects to move data to noga.
    :param hosts_dict: host part of data dictionary with aliases
    :return: list of objects
    """
    list_to_return = []
    for host in hosts_dict.keys():
        host_resource = HostResource(host, hosts_dict[host]['alias'], hosts_dict[host]['ip'])
        host_resource.set_custom_params(hosts_dict[host]['custom_params'])
        list_to_return.append(host_resource)
    return list_to_return


def fill_switches(switches_dict):
    """
    @summary: create a list of objects (SwitchResource) to move data to noga.
    :param switches_dict: switch part of data dictionary with aliases
    :return: list of objects.
    """
    list_to_return = []
    for ip in switches_dict.keys():
        switch_resource = SwitchResource(ip, switches_dict[ip]['alias'], switches_dict[ip]['ip'])
        switch_resource.set_custom_params(switches_dict[ip]['custom_params'])
        list_to_return.append(switch_resource)
    return list_to_return


def fill_links(data):
    """
    @summary: create a list of objects (GeneralResource) to move data to noga.
    :param data: data dictionary with aliases
    :return: list of objects.
    """
    list_to_return = []
    for device_name in data['hosts'].keys():
        for link_name in data['hosts'][device_name]['links'].keys():
            list_to_return.append(LinkResource(link_name, data['hosts'][device_name]['links'][link_name]))
    for device_name in data['switches'].keys():
        for link_name in data['switches'][device_name]['links'].keys():
            list_to_return.append(LinkResource(link_name, data['switches'][device_name]['links'][link_name]))
    return list_to_return


def import_all_aliases(objects_list):
    """
    @summary: trigger import_alias method of all the resource classes to insert values to Noga.
    :param objects_list: list of objects to insert alias.
    """
    print("Import all aliases")
    for obj in objects_list:
        obj.import_alias()


def create_objects_list(data):
    """
    @summary: will create objects of a related classes.
    :param data: dictionary with aliases
    """
    print("Create object list")
    list_of_hosts = fill_hosts(data['hosts'])
    list_of_switches = fill_switches(data['switches'])
    list_of_links = fill_links(data)

    objects_list = list_of_hosts + list_of_links + list_of_switches
    return objects_list



if __name__ == '__main__':
    try:
        # parser definition
        description_str = ('Importing aliases for canonical setup, for devts targets.'
                           'Using json/pickle which is given as a parameter to script'
                           'Gets all the data by deserializing it.'
                           'Please NOTE, that this script can be used only on device '
                           'with installed Oracle client, to access Noga database tables.')

        cmdline = argparse.ArgumentParser(description=description_str,
                                          formatter_class=argparse.RawDescriptionHelpFormatter)
        cmdline.add_argument('-j', '--json', action='append', required=True,
                             help='Path to the json file, which contain aliases to be imported.')
        cmdline.add_argument('--debug_log', action='store_true', default=False,
                             help='Enable debug print')

        print("Start importing to Noga")

        # parse args
        cmdline_args, unknown = cmdline.parse_known_args()
        if unknown:
            raise Exception("unknown argument(s): %s" % unknown)

        # set debug logger
        debug_en = cmdline_args.debug_log

        # Import to Noga
        data = deserialize_json(cmdline_args.json)
        objects_list = create_objects_list(data)
        import_all_aliases(objects_list)

        print("End importing to Noga successfully")

    except Exception:
        traceback.print_exc()
        sys.exit(1)

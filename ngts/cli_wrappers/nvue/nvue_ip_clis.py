import netaddr
import re
import json
import logging
from ngts.cli_wrappers.common.ip_clis_common import IpCliCommon


class NvueIpCli(IpCliCommon):
    def __init__(self, engine):
        self.engine = engine

    def show_ip_interfaces(self):
        """
        This method shows ip configuration on interfaces
        :return: the output of the command "show ip interfaces"
        """
        return self.engine.run_cmd('nv sh interface -o json')

    def add_ip_to_interface(self, interface, ip, mask):
        raise NotImplementedError

    def del_ip_from_interface(self, interface, ip, mask):
        raise NotImplementedError

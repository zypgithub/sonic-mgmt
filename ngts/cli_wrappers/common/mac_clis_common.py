from ngts.cli_wrappers.interfaces.interface_mac_clis import MacCliInterface


class MacCliCommon(MacCliInterface):
    """
    This class hosts methods which are implemented identically for Linux and SONiC
    """

    def __init__(self, engine):
        self.engine = engine
        self.ip_netns_prefix = getattr(self, 'ip_netns_prefix', "sudo ")

    def get_mac_address_for_interface(self, interface):
        """
        Method for get mac address for interface
        :param interface: interface name
        :return: mac address
        """
        return self.engine.run_cmd(f"{self.ip_netns_prefix}cat /sys/class/net/{interface}/address")

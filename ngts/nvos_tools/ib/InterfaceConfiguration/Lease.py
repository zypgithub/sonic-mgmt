import logging

from ngts.nvos_tools.infra.BaseComponent import BaseComponent

logger = logging.getLogger()


class Lease(BaseComponent):
    """
    DHCP lease information class for accessing lease data
    from /var/lib/dhcp/dhclient.eth0/1.leases
    """

    def __init__(self, parent_obj=None, protocol='ipv4'):
        BaseComponent.__init__(self, parent=parent_obj, path='/lease')
        self.protocol = protocol

    def has_active_lease(self):
        """
        Check if there's an active lease based on lease data
        Replaces the deprecated 'has-lease' field
        """
        try:
            lease_data = self.show()
            if isinstance(lease_data, dict):
                # Check for key indicators of active lease
                if self.protocol == 'ipv4':
                    return 'fixed-address' in lease_data and lease_data.get('fixed-address')
                elif self.protocol == 'ipv6':
                    return 'ia-na' in lease_data and lease_data.get('ia-na')
            return False
        except Exception as e:
            logger.info(f"Error checking lease status: {e}")
            return False

    def get_lease_info(self):
        """
        Get comprehensive lease information
        Replaces the deprecated 'is-running' field logic
        """
        try:
            return self.show()
        except Exception as e:
            logger.info(f"Error getting lease info: {e}")
            return {}

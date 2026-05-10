"""PhotonicsTool - Utilities for ELS/OE transceiver operations."""

ELS_PREFIX = 'els'


class PhotonicsTool:
    """Static utility methods for photonics/transceiver operations."""

    @staticmethod
    def get_mst_device_for_els_index(device, els_index):
        """
        Get MST device path for a given ELS index.
        Delegates to the device's platform-specific mapping.

        Args:
            device: Device object with get_mst_device_for_els_index method
            els_index: ELS index (e.g. 1-18 for Taipan)

        Returns:
            str: MST device path
        """
        return device.get_mst_device_for_els_index(els_index)

    @staticmethod
    def get_els_for_traffic_ports(device, traffic_ports):
        """
        Find ELS transceiver that has the given traffic ports.

        Args:
            device: Device object with els_port_mapping attribute
            traffic_ports: List of port names (e.g., ['sw5p1', 'sw6p1'])

        Returns:
            tuple: (els_name, matching_ports, channel_indices) or (None, [], []) if not found
        """
        for els_name, els_ports in device.els_port_mapping.items():
            matching = [p for p in traffic_ports if p in els_ports]
            if matching:
                indices = [els_ports.index(p) + 1 for p in matching]
                return els_name, matching, indices
        return None, [], []

    @staticmethod
    def get_oe_list_for_els(device, els_name):
        """Get list of OE transceivers mapped to an ELS.

        Args:
            device: Device object with els_oe_mapping attribute
            els_name: ELS transceiver name (e.g. 'els1')
        """
        return device.els_oe_mapping.get(els_name, [])

    @staticmethod
    def get_ports_for_els(device, els_name):
        """Get list of ports mapped to an ELS.

        Args:
            device: Device object with els_port_mapping attribute
            els_name: ELS transceiver name (e.g. 'els1')
        """
        return device.els_port_mapping.get(els_name, [])

    @staticmethod
    def get_els_index(els_name):
        """Extract numeric index from ELS name (e.g., 'els18' -> 18)."""
        if not els_name.startswith(ELS_PREFIX):
            raise ValueError(f"Expected ELS name starting with '{ELS_PREFIX}', got: {els_name}")
        return int(els_name.removeprefix(ELS_PREFIX))

    @staticmethod
    def get_traffic_channel_indices(port_list, traffic_ports):
        """
        Find 1-based channel indices for traffic ports within a port list.

        Args:
            port_list: List of port names from OE port-mapping
            traffic_ports: List of traffic port names to find

        Returns:
            list: 1-based channel indices for matching ports
        """
        return [port_list.index(p) + 1 for p in traffic_ports if p in port_list]

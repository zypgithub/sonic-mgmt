"""PhotonicsTool - Utilities for ELS/OE transceiver operations on Taipan systems."""

from ngts.tests_nvos.platform.constants import TransceiversConsts


class PhotonicsTool:
    """Static utility methods for photonics/transceiver operations."""

    # ELS index to GA mapping for MST device selection
    ELS_INDEX_TO_GA = {
        1: 1, 2: 2, 3: 1, 4: 2, 5: 1, 6: 2, 7: 1, 8: 2,
        9: 1, 10: 3, 11: 0, 12: 3, 13: 0, 14: 3, 15: 0, 16: 3, 17: 0, 18: 3
    }

    @staticmethod
    def get_mst_device_for_els_index(els_index):
        """
        Get MST device path for a given ELS index.

        Args:
            els_index: ELS index (1-18)

        Returns:
            str: MST device path '/dev/mst/mt54004_pciconf{i}'

        Raises:
            ValueError: If els_index not in valid range
        """
        if els_index not in PhotonicsTool.ELS_INDEX_TO_GA:
            raise ValueError(f"Invalid ELS index: {els_index}. Valid range is 1-18")

        ga_value = PhotonicsTool.ELS_INDEX_TO_GA[els_index]
        return f"/dev/mst/mt54004_pciconf{(ga_value + 1) % 4}"

    @staticmethod
    def get_els_for_traffic_ports(traffic_ports):
        """
        Find ELS transceiver that has the given traffic ports.

        Args:
            traffic_ports: List of port names (e.g., ['sw5p1', 'sw6p1'])

        Returns:
            tuple: (els_name, matching_ports, channel_indices) or (None, [], []) if not found
        """
        for els_name, els_ports in TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING.items():
            matching = [p for p in traffic_ports if p in els_ports]
            if matching:
                # Channel index is 1-based position in the port list
                indices = [els_ports.index(p) + 1 for p in matching]
                return els_name, matching, indices
        return None, [], []

    @staticmethod
    def get_oe_list_for_els(els_name):
        """Get list of OE transceivers mapped to an ELS."""
        return TransceiversConsts.TRANSCEIVERS_ELS_OE_MAPPING.get(els_name, [])

    @staticmethod
    def get_ports_for_els(els_name):
        """Get list of ports mapped to an ELS."""
        return TransceiversConsts.TRANSCEIVERS_ELS_PORT_MAPPING.get(els_name, [])

    @staticmethod
    def get_els_index(els_name):
        """Extract numeric index from ELS name (e.g., 'els18' -> 18)."""
        return int(els_name.replace('els', ''))

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

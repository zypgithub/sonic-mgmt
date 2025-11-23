"""
Base class for Sonic CLI classes that handle multi-ASIC command formatting
"""


class SonicMultiAsicCli:
    """
    Base class for Sonic CLI implementations that need to handle multi-ASIC systems.
    Provides common initialization for ASIC management and multi-ASIC command formatting.
    Subclasses must explicitly choose which format to use:
      - multi_asic_config_cmd_ext : For SONiC config commands (e.g., "-n asic0")
      - multi_asic_service_cmd_ext : For systemd service commands (e.g., "bgp@0")
      - multi_asic_docker_cmd_ext : For docker commands (e.g., "0")
    """

    def __init__(self, engine, asic_id=None):
        """
        Initialize multi-ASIC CLI handler
        :param engine: CLI engine instance
        :param asic_id: ASIC ID (defaults to None (single-ASIC) if not provided)
        """
        self.engine = engine
        self.asic_id = asic_id
        self.multi_asic_config_cmd_ext = "-n asic{}".format(self.asic_id) if self.asic_id is not None else ""
        self.multi_asic_service_cmd_ext = "@{}".format(self.asic_id) if self.asic_id is not None else ""
        self.multi_asic_docker_cmd_ext = "{}".format(self.asic_id) if self.asic_id is not None else ""
        self.multi_asic_namespace_cmd_ext = "asic{}".format(self.asic_id) if self.asic_id is not None else ""
        self.ip_netns_prefix = f"sudo ip netns exec {self.multi_asic_namespace_cmd_ext} " if self.asic_id is not None else "sudo "

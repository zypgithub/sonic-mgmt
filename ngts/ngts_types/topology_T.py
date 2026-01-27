from typing import Any, Dict
from dotted_dict import DottedDict


class TopologyT(DottedDict):
    # First-level structure only (do not model nested keys here).
    players: Dict[str, Any]
    ports: Dict[str, Any]
    ports_interconnects: Dict[str, Any]
    players_all_ports: Dict[str, Any]

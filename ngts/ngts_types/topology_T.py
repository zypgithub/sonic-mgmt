from __future__ import annotations

from typing import Any, TYPE_CHECKING
from dotted_dict import DottedDict

if TYPE_CHECKING:
    from infra.tools.topology_tools.player_attributes import PlayerAttributes
    from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine


class TopologyT(DottedDict):
    # First-level structure only (do not model nested keys here).
    players: dict[str, dict[str, PlayerAttributes | ProxySshEngine]]
    ports: dict[str, Any]
    ports_interconnects: dict[str, Any]
    players_all_ports: dict[str, Any]

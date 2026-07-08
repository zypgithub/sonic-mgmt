from __future__ import annotations

from dotted_dict import DottedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devts.infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine


class EnginesT(DottedDict):
    dut: LinuxSshEngine
    ha: object | None
    ha_attr: object | None
    hb: object | None
    hb_attr: object | None
    server: object | None
    sonic_mgmt: LinuxSshEngine | None

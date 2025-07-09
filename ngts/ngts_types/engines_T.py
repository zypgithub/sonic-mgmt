from dotted_dict import DottedDict
from typing import Optional

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine


class EnginesT(DottedDict):
    dut: LinuxSshEngine
    ha: Optional[object]
    ha_attr: Optional[object]
    hb: Optional[object]
    hb_attr: Optional[object]
    server: Optional[object]
    sonic_mgmt: Optional[LinuxSshEngine]

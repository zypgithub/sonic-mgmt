from __future__ import annotations

from dotted_dict import DottedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ngts.nvos_tools.Devices.IbDevice import IbSwitch, NvLinkSwitch, JulietScaleoutSwitch


class DevicesT(DottedDict):
    dut: IbSwitch | NvLinkSwitch | JulietScaleoutSwitch

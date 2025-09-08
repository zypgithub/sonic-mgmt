from typing import Union
from dotted_dict import DottedDict

from ngts.nvos_tools.Devices.IbDevice import IbSwitch, NvLinkSwitch


class DevicesT(DottedDict):
    dut: Union[IbSwitch, NvLinkSwitch]

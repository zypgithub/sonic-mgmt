import logging

from ngts.cli_wrappers.nvue.nvue_chassis_clis import NvueChassisCli
from ngts.cli_wrappers.sonic.sonic_hw_mgmt_cli import SonicHwMgmtCli
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.cli_wrappers.sonic.sonic_interface_clis import SonicInterfaceCli
from ngts.cli_wrappers.sonic.sonic_im_clis import SonicImClis

logger = logging.getLogger()


class NvueCli():
    def __init__(self, topology):
        # self.branch = topology.players['dut'].get('branch')
        self.engine = topology.players['dut']['engine']
        self.chassis = NvueChassisCli(engine=self.engine)
        self._general = None
        self._hw_mgmt = None
        self._interface = None
        self._im = None

    @property
    def general(self):
        if self._general is None:
            self._general = NvueGeneralCli(engine=self.engine, device=None)
        return self._general

    @property
    def hw_mgmt(self):
        if self._hw_mgmt is None:
            self._hw_mgmt = SonicHwMgmtCli(engine=self.engine)
        return self._hw_mgmt

    @property
    def interface(self):
        if self._interface is None:
            self._interface = SonicInterfaceCli(engine=self.engine, cli_obj=self)
        return self._interface

    @property
    def im(self):
        if self._im is None:
            self._im = SonicImClis(engine=self.engine, cli_obj=self)
        return self._im

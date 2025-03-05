import logging

from ngts.cli_wrappers.nvue.nvue_chassis_clis import NvueChassisCli
from ngts.cli_wrappers.sonic.sonic_hw_mgmt_cli import SonicHwMgmtCli
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.cli_wrappers.sonic.sonic_im_clis import SonicImClis
from ngts.cli_wrappers.nvue.nvue_ip_clis import NvueIpCli
from ngts.cli_wrappers.nvue.nvue_performance_clis import NvuePerformanceCli
from ngts.cli_wrappers.nvue.nvue_interface_clis import NvueInterfaceCli

logger = logging.getLogger()


class NvueCli:
    def __init__(self, topology, engine, dut_alias):
        # self.branch = topology.players['dut'].get('branch')
        self.topology = topology
        self.dut_alias = dut_alias
        self.engine = engine
        self.chassis = NvueChassisCli(engine=self.engine)
        self._general = None
        self._hw_mgmt = None
        self._interface = None
        self._im = None
        self._ip = None
        self._performance = None

    @property
    def general(self):
        if self._general is None:
            self._general = NvueGeneralCli(engine=self.engine, device=None, cli_obj=self, dut_alias=self.dut_alias)
        return self._general

    @property
    def hw_mgmt(self):
        if self._hw_mgmt is None:
            self._hw_mgmt = SonicHwMgmtCli(engine=self.engine)
        return self._hw_mgmt

    @property
    def interface(self):
        if self._interface is None:
            self._interface = NvueInterfaceCli(engine=self.engine, cli_obj=self)
        return self._interface

    @property
    def im(self):
        if self._im is None:
            self._im = SonicImClis(engine=self.engine, cli_obj=self)
        return self._im

    @property
    def ip(self):
        if self._ip is None:
            self._ip = NvueIpCli(engine=self.engine)
        return self._ip

    @property
    def performance(self):
        if self._performance is None:
            self._performance = NvuePerformanceCli(topology_obj=self.topology, engine=self.engine,
                                                   dut_alias=self.dut_alias, cli_obj=self)
        return self._performance

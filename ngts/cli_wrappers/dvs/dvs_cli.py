from ngts.cli_wrappers.dvs.dvs_general_cli import DvsGeneralCli
from ngts.cli_wrappers.dvs.dvs_performance import DvsPerformance


class DvsCli:
    def __init__(self, topology, dut_alias='dut'):
        self.dut_alias = dut_alias
        self.engine = topology.players[self.dut_alias]['engine']
        self.topology = topology
        self._general = None
        self._performance = None

    @property
    def general(self):
        if self._general is None:
            self._general = DvsGeneralCli(self.engine, self.dut_alias)
        return self._general

    @property
    def performance(self):
        if self._performance is None:
            self._performance = DvsPerformance(self.topology)

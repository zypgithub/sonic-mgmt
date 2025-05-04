from ngts.cli_wrappers.dvs.dvs_general_clis import DvsGeneralCli
from ngts.cli_wrappers.dvs.dvs_performance_clis import DvsPerformance
from ngts.cli_wrappers.dvs.dvs_chassis_clis import DvsChassisCli
from ngts.cli_wrappers.dvs.dvs_interface_clis import DvsInterfaceCli


class DvsCli:
    def __init__(self, topology, dut_alias='dut'):
        self.dut_alias = dut_alias
        self.engine = topology.players[self.dut_alias]['engine']
        self.topology = topology
        self._general = None
        self._performance = None
        self._chassis = None
        self._interface = None

    @property
    def general(self):
        if self._general is None:
            self._general = DvsGeneralCli(self.engine, self.dut_alias)
        return self._general

    @property
    def performance(self):
        if self._performance is None:
            self._performance = DvsPerformance(self.topology, self.engine, self.dut_alias, cli_obj=self)
        return self._performance

    @property
    def chassis(self):
        if self._chassis is None:
            self._chassis = DvsChassisCli(engine=self.engine)
        return self._chassis

    @property
    def interface(self):
        if self._interface is None:
            self._interface = DvsInterfaceCli(self.engine, self.dut_alias)
        return self._interface

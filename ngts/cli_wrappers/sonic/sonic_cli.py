import logging

from ngts.cli_wrappers.sonic.sonic_ip_clis import SonicIpCli
from ngts.cli_wrappers.sonic.sonic_lag_lacp_clis import SonicLagLacpCli
from ngts.cli_wrappers.sonic.sonic_interface_clis import SonicInterfaceCli
from ngts.cli_wrappers.sonic.sonic_lldp_clis import SonicLldpCli
from ngts.cli_wrappers.sonic.sonic_mac_clis import SonicMacCli
from ngts.cli_wrappers.sonic.sonic_vlan_clis import SonicVlanCli
from ngts.cli_wrappers.sonic.sonic_route_clis import SonicRouteCli
from ngts.cli_wrappers.sonic.sonic_vrf_clis import SonicVrfCli
from ngts.cli_wrappers.sonic.sonic_chassis_clis import SonicChassisCli
from ngts.cli_wrappers.sonic.sonic_general_clis import SonicGeneralCli
from ngts.cli_wrappers.sonic.sonic_dhcp_relay_clis import SonicDhcpRelayCli
from ngts.cli_wrappers.sonic.sonic_ifconfig_clis import SonicIfconfigCli
from ngts.cli_wrappers.sonic.sonic_crm_clis import SonicCrmCli
from ngts.cli_wrappers.sonic.sonic_acl_clis import SonicAclCli
from ngts.cli_wrappers.sonic.sonic_vxlan_clis import SonicVxlanCli
from ngts.cli_wrappers.sonic.sonic_frr_cli import SonicFrrCli
from ngts.cli_wrappers.sonic.sonic_bgp_clis import SonicBgpCli
from ngts.cli_wrappers.sonic.sonic_counterpoll_clis import SonicCounterpollCli
from ngts.cli_wrappers.sonic.sonic_flowcnt_clis import SonicFlowcntCli
from ngts.cli_wrappers.sonic.sonic_app_extension_clis import SonicAppExtensionCli
from ngts.cli_wrappers.sonic.sonic_arp_clis import SonicArpCli
from ngts.cli_wrappers.sonic.sonic_p4_sampling_clis import P4SamplingCli
from ngts.cli_wrappers.sonic.sonic_p4_examples_clis import P4GTPParserCli, P4VxlanBMCli, P4ExamplesCli
from ngts.cli_wrappers.sonic.sonic_sfputil_clis import SonicSfputilCli
from ngts.cli_wrappers.sonic.sonic_qos_clis import SonicQosCli
from ngts.cli_wrappers.sonic.sonic_ztp import SonicZtpCli
from ngts.cli_wrappers.sonic.sonic_sflow_clis import SonicSflowCli
from ngts.cli_wrappers.sonic.sonic_doroce_clis import SonicDoroceCli
from ngts.cli_wrappers.sonic.sonic_watermark_clis import SonicWatermarkCli
from ngts.cli_wrappers.sonic.sonic_ar_clis import SonicAdaptiveRoutingCli
from ngts.cli_wrappers.sonic.sonic_fwutil_clis import SonicFwutilCli
from ngts.cli_wrappers.sonic.sonic_im_clis import SonicImClis
from ngts.cli_wrappers.sonic.sonic_hw_mgmt_cli import SonicHwMgmtCli
from ngts.cli_wrappers.sonic.sonic_wcmp_clis import SonicWcmpCli
from ngts.cli_wrappers.sonic.sonic_performance_clis import SonicPerformanceCli
from ngts.cli_wrappers.sonic.sonic_trimming_clis import SonicTrimmingCli
from ngts.cli_util.stub_engine import StubEngine
from dotted_dict import DottedDict
logger = logging.getLogger()


class SonicCli:
    def __init__(self, topology, dut_alias='dut'):
        self.topology = topology
        self.dut_alias = dut_alias
        self.branch = topology.players['dut'].get('branch')
        self.engine = topology.players[self.dut_alias]['engine']

        self._ip = None
        self._arp = None
        self._lldp = None
        self._mac = None
        self._vlan = None
        self._lag = None
        self._interface = None
        self._route = None
        self._vrf = None
        self._chassis = None
        self._general = None
        self._dhcp_relay = None
        self._ifconfig = None
        self._crm = None
        self._acl = None
        self._vxlan = None
        self._frr = None
        self._bgp = None
        self._counterpoll = None
        self._flowcnt = None
        self._app_ext = None
        self._p4_sampling = None
        self._p4_gtp = None
        self._p4_examples = None
        self._p4_vxlan_bm = None
        self._sfputil = None
        self._qos = None
        self._doroce = None
        self._watermark = None
        self._ztp = None
        self._sflow = None
        self._ar = None
        self._hw_mgmt = None
        self._wcmp = None
        self._im = None
        self._performance = None
        self._trimming = None

    @property
    def ip(self):
        if self._ip is None:
            self._ip = SonicIpCli(engine=self.engine)
        return self._ip

    @property
    def arp(self):
        if self._arp is None:
            self._arp = SonicArpCli(engine=self.engine)
        return self._arp

    @property
    def lldp(self):
        if self._lldp is None:
            self._lldp = SonicLldpCli(engine=self.engine)
        return self._lldp

    @property
    def mac(self):
        if self._mac is None:
            self._mac = SonicMacCli(engine=self.engine)
        return self._mac

    @property
    def vlan(self):
        if self._vlan is None:
            self._vlan = SonicVlanCli(branch=self.branch, engine=self.engine)
        return self._vlan

    @property
    def lag(self):
        if self._lag is None:
            self._lag = SonicLagLacpCli(engine=self.engine)
        return self._lag

    @property
    def interface(self):
        if self._interface is None:
            self._interface = SonicInterfaceCli(engine=self.engine, cli_obj=self)
        return self._interface

    @property
    def route(self):
        if self._route is None:
            self._route = SonicRouteCli(engine=self.engine)
        return self._route

    @property
    def vrf(self):
        if self._vrf is None:
            self._vrf = SonicVrfCli(engine=self.engine)
        return self._vrf

    @property
    def chassis(self):
        if self._chassis is None:
            self._chassis = SonicChassisCli(engine=self.engine)
        return self._chassis

    @property
    def general(self):
        if self._general is None:
            self._general = SonicGeneralCli(branch=self.branch, engine=self.engine, cli_obj=self,
                                            dut_alias=self.dut_alias)
        return self._general

    @property
    def dhcp_relay(self):
        if self._dhcp_relay is None:
            self._dhcp_relay = SonicDhcpRelayCli(branch=self.branch, engine=self.engine, cli_obj=self)
        return self._dhcp_relay

    @property
    def ifconfig(self):
        if self._ifconfig is None:
            self._ifconfig = SonicIfconfigCli(engine=self.engine)
        return self._ifconfig

    @property
    def crm(self):
        if self._crm is None:
            self._crm = SonicCrmCli(engine=self.engine)
        return self._crm

    @property
    def acl(self):
        if self._acl is None:
            self._acl = SonicAclCli(engine=self.engine)
        return self._acl

    @property
    def vxlan(self):
        if self._vxlan is None:
            self._vxlan = SonicVxlanCli(engine=self.engine)
        return self._vxlan

    @property
    def frr(self):
        if self._frr is None:
            self._frr = SonicFrrCli(engine=self.engine)
        return self._frr

    @property
    def bgp(self):
        if self._bgp is None:
            self._bgp = SonicBgpCli(engine=self.engine)
        return self._bgp

    @property
    def counterpoll(self):
        if self._counterpoll is None:
            self._counterpoll = SonicCounterpollCli(engine=self.engine)
        return self._counterpoll

    @property
    def flowcnt(self):
        if self._flowcnt is None:
            self._flowcnt = SonicFlowcntCli(engine=self.engine)
        return self._flowcnt

    @property
    def app_ext(self):
        if self._app_ext is None:
            self._app_ext = SonicAppExtensionCli(engine=self.engine)
        return self._app_ext

    @property
    def p4_sampling(self):
        if self._p4_sampling is None:
            self._p4_sampling = P4SamplingCli(engine=self.engine)
        return self._p4_sampling

    @property
    def p4_gtp(self):
        if self._p4_gtp is None:
            self._p4_gtp = P4GTPParserCli(engine=self.engine)
        return self._p4_gtp

    @property
    def p4_examples(self):
        if self._p4_examples is None:
            self._p4_examples = P4ExamplesCli(engine=self.engine)
        return self._p4_examples

    @property
    def sflow(self):
        if self._sflow is None:
            self._sflow = SonicSflowCli(engine=self.engine)
        return self._sflow

    @property
    def p4_vxlan_bm(self):
        if self._p4_vxlan_bm is None:
            self._p4_vxlan_bm = P4VxlanBMCli(engine=self.engine)
        return self._p4_vxlan_bm

    @property
    def sfputil(self):
        if self._sfputil is None:
            self._sfputil = SonicSfputilCli(engine=self.engine)
        return self._sfputil

    @property
    def qos(self):
        if self._qos is None:
            self._qos = SonicQosCli(engine=self.engine)
        return self._qos

    @property
    def doroce(self):
        if self._doroce is None:
            self._doroce = SonicDoroceCli(engine=self.engine, cli_obj=self)
        return self._doroce

    @property
    def watermark(self):
        if self._watermark is None:
            self._watermark = SonicWatermarkCli(engine=self.engine)
        return self._watermark

    @property
    def ztp(self):
        if self._ztp is None:
            self._ztp = SonicZtpCli(engine=self.engine)
        return self._ztp

    @property
    def hw_mgmt(self):
        if self._hw_mgmt is None:
            self._hw_mgmt = SonicHwMgmtCli(engine=self.engine)
        return self._hw_mgmt

    @property
    def fwutil(self):
        if self._fwutil is None:
            self._fwutil = SonicFwutilCli(engine=self.engine)
        return self._fwutil

    @property
    def ar(self):
        if self._ar is None:
            self._ar = SonicAdaptiveRoutingCli(engine=self.engine)
        return self._ar

    @property
    def wcmp(self):
        if self._wcmp is None:
            self._wcmp = SonicWcmpCli(engine=self.engine)
        return self._wcmp

    @property
    def im(self):
        if self._im is None:
            self._im = SonicImClis(engine=self.engine, cli_obj=self)
        return self._im

    @property
    def performance(self):
        if self._performance is None:
            self._performance = SonicPerformanceCli(topology_obj=self.topology, engine=self.engine,
                                                    dut_alias=self.dut_alias, cli_obj=self)
        return self._performance

    @property
    def trimming(self):
        if self._trimming is None:
            self._trimming = SonicTrimmingCli(topology_obj=self.topology, engine=self.engine,
                                              dut_alias=self.dut_alias, cli_obj=self)
        return self._trimming


class SonicCliStub(SonicCli):
    def __init__(self, topology):
        stub_topo = DottedDict()
        stub_topo.players = {'dut': {'engine': StubEngine()}}
        super().__init__(stub_topo)

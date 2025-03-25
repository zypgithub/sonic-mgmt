import os
import json
import allure
import logging
import pytest
from ngts.helpers.system_helpers import copy_files_to_syncd
from ngts.helpers.performance.traffic_helpers import is_ipv6, generate_mac_range
from ngts.helpers.performance.performance_setup_helpers import (ValidationConfig, run_traffic, run_validation,
                                                                skip_test_on_unsupported_os, add_test_mongo_metadata)
from ngts.constants.constants import CliType, InfraConst
from ngts.constants.performance_constants import PerfConsts, MongoDbConsts, MRCConsts, ValidationConsts
from ngts.performance_tests.srv6.conftest import get_workload_method
from ngts.performance_tests.srv6.conftest import (get_upstream_downstream_port_group_df, get_round_robin_traffic)

logger = logging.getLogger()


class TestSRv6Base:

    @pytest.fixture(autouse=True)
    def setup(self, players, engines, cli_objects, is_ipv6, chip_type, conf_args, power_thresholds_by_chip_type):
        self.players = players
        self.engines = engines
        self.cli_objects = cli_objects
        self.engine = engines['dut']
        self.cli_object = self.cli_objects['dut']
        self.tg_cli_object = self.cli_objects[PerfConsts.LEFT_TG_ALIAS]
        self.ip = InfraConst.IPV6 if is_ipv6 else InfraConst.IPV4
        self.chip_type = chip_type
        self.scenario = "srv6"
        self.conf_args = conf_args
        self.hwsku = conf_args["hwsku"]
        self.power_thresholds_by_chip_type = power_thresholds_by_chip_type
        self.dut_interfaces_ipv6_configuration_dict = {}
        self.vlan_interface_configuration_dict = {}

    def round_robin_traffic_test_runner(self, test_name, traffic_type, workload,
                                        upstream, downstream, packet_size=4096):
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.NVUE)
        skip_test_on_unsupported_os(cli_obj=self.cli_object, unsupported_os=CliType.DVS)

        with allure.step(f"Run {packet_size}B packet Traffic on all the ports"):
            traffic_jsons = get_round_robin_traffic(self.players, self.conf_args, traffic_type,
                                                    upstream, downstream,
                                                    self.dut_interfaces_ipv6_configuration_dict,
                                                    create_workload_stream=get_workload_method(workload))
            run_traffic(self.players, self.scenario, traffic_jsons, attach_traffic_json=False)

        with allure.step(f"Verifying the traffic for packet size {packet_size}"):
            half_ports_num = (len(upstream) + len(downstream)) // 2
            round_robin_occ_th_dict = {ValidationConsts.TC_OCC_AVG: 11 * half_ports_num,
                                       ValidationConsts.TC_OCC_99: 22 * half_ports_num}
            config = ValidationConfig(players=self.players, test_name=test_name, scenario=self.scenario,
                                      chip_type=self.chip_type,
                                      bw_threshold=MRCConsts.DUT_TX_UTIL_TH,
                                      tc_occ_threshold=round_robin_occ_th_dict,
                                      power_threshold=self.power_thresholds_by_chip_type,
                                      counters_list=MRCConsts.COUNTERS_WITH_ECN,
                                      run_validate_counters=False)
            run_validation(config)

    def configure_interfaces_mac_neighbor(self):
        """
        TODO: Should be done via BGP - this is temporary
        Configure static route on dut, however this configuration eventually will be done via BGP
        """
        dut_ports = self.cli_object.performance.get_dut_ports()
        mac_range = generate_mac_range("00:11:22:33:44:55", count=len(dut_ports))
        fdb_discard_conf = []
        cmd_list = []
        for idx, port in enumerate(dut_ports):
            port_ipv6_address = self.dut_interfaces_ipv6_configuration_dict[port].replace("aaaa", "bbbb")
            port_neighbor_mac = mac_range[idx]
            vlan = self.vlan_interface_configuration_dict[port]
            cmd_list.append(f"sudo ip -6 route add {port_ipv6_address}/48 dev {port}")
            cmd_list.append(f"sudo ip -6 neigh add {port_ipv6_address} lladdr {port_neighbor_mac} dev {port}")
            fdb_discard_conf.append([self.cli_object.performance.get_hex_int_sdk_port(port), port_neighbor_mac, vlan])
        self.engine.run_cmd_set(cmd_list)
        self.configure_fdb_discard(fdb_discard_conf)

    def configure_fdb_discard(self, fdb_discard_conf):
        """
        TODO: should be removed with correct ACL - this is temporary

        All egress traffic going into the tg should be dropped, this should be done by ACL
        However currently this is being done by adding correct FDB discard entries via sdk.
        """
        conf_file = "fdb_discard_conf.json"
        full_path = os.path.join(PerfConsts.CONFIG_FILES_DIR, conf_file)
        with open(full_path, 'w') as f:
            json.dump(fdb_discard_conf, f)
        for alias in PerfConsts.PERF_SETUP_TG_ALIASES:
            copy_files_to_syncd(self.engines[alias], [conf_file], PerfConsts.CONFIG_FILES_DIR)
        for alias in PerfConsts.PERF_SETUP_TG_ALIASES:
            tg_cli = self.cli_objects[alias]
            tg_cli.performance.fdb_discard_creation()

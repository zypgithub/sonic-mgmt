import allure
import logging
import pytest
import copy
import re

from ngts.tests.nightly.ecmp_calculator.ecmp_calculator_helper import calculate_ecmp_egress_port, Traffic, \
    get_host_name_and_receive_port_as_egress_port, gen_packet_json_file, load_packet_json, \
    copy_packet_json_to_syncd, gen_test_data
from ngts.tests.nightly.ecmp_calculator.constants import V4_CONFIG

logger = logging.getLogger()

NEGATIVE_CASE_TYPE = ["invalid_json_format", "invalid_data_type", "no_outer_dip", "invalid_ip", "invalid_mac",
                      "non_physical_ingress_port", "ipv4_ipv6_coexist", "no_proto_for_v4", "no_next_header_for_v6"]
NEGATIVE_CASE_EXPECTED_MSG = {"invalid_json_format": r".*Value error: Failed to load JSON file.*, error: 'Extra data: line.*",
                              "invalid_data_type": r".*Value error: Json validation failed: 'tcp' is not of type 'number'.*",
                              "no_outer_dip": r".*Value error: Json validation failed: 'dip' is a required property.*",
                              "invalid_ip": r".*Value error: Json validation failed: invalid IP.*",
                              "invalid_mac": r".*Value error: Json validation failed: invalid mac.*",
                              "non_physical_ingress_port": r".*Value error: Invalid interface.*",
                              "ipv4_ipv6_coexist": r".*Value error: Json validation failed: IPv4 and IPv6 headers can not co-exist.*",
                              "no_proto_for_v4": r".*Value error: Json validation failed: transport protocol \(proto\) is mandatory when transport layer port exists.*",
                              "no_next_header_for_v6": r".*Value error: Json validation failed: transport protocol \(next_header\) is mandatory when transport layer port exists.*",
                              }


class TestEcmpCalcBase:

    @pytest.fixture(autouse=True)
    def setup_param(self, topology_obj, engines, cli_objects, interfaces, players, dut_ha_1_mac):
        self.topology_obj = topology_obj
        self.engines = engines
        self.dut_engine = engines.dut
        self.interfaces = interfaces
        self.players = players
        self.cli_objects = cli_objects
        self.ingress_port = self.interfaces.dut_ha_1
        self.ecmp_traffic = Traffic()
        self.dut_mac = dut_ha_1_mac

    def calculate_egress_port_and_verify_by_sending_packet(self, packet, packet_type, packet_json_file_name,
                                                           ingress_port, vrf=""):
        with allure.step(f'Gen packet json and copy to syncd container'):
            gen_packet_json_file(packet_type, packet, packet_json_file_name)
            copy_packet_json_to_syncd(self.dut_engine, packet_json_file_name)

        with allure.step(f'calculate egress port'):
            egress_ports = calculate_ecmp_egress_port(self.engines.dut, self.interfaces.dut_ha_1,
                                                      packet_json_file_name, vrf)

        with allure.step(f'send packet to verify packets are sent out from egress port {egress_ports[0]}'):
            packet_info = load_packet_json(packet_json_file_name)["packet_info"]
            send_packet_number = 200
            host_name, receive_port = get_host_name_and_receive_port_as_egress_port(
                self.interfaces, egress_ports[0])
            traffic_filter = f" src {packet['outer_sip']} and dst {packet['outer_dip']}"
            receive_packet_info = [{"receiver": host_name, "interface": receive_port,
                                    "counter": send_packet_number, "filter": traffic_filter}]
            self.ecmp_traffic.traffic_validation(players=self.players, ingress_port=ingress_port,
                                                 packet_info=packet_info, packet_type=packet_type,
                                                 send_packet_count=send_packet_number,
                                                 receive_packet_info=receive_packet_info)

    def verify_egress_ports_include_all_members_and_packet_is_flooding(self, packet, packet_type, packet_json_file_name,
                                                                       ingress_port, vrf=""):

        with allure.step(f'calculate egress port'):
            egress_ports = calculate_ecmp_egress_port(self.engines.dut, self.interfaces.dut_ha_1,
                                                      packet_json_file_name, vrf)
            if len(egress_ports) != 2:
                raise Exception(f"egress ports doesn't include all members: {egress_ports}")

        with allure.step(f'Verify packet are flooding '):
            packet_info = load_packet_json(packet_json_file_name)["packet_info"]
            send_packet_number = 2

            if vrf:
                ha_dut_2_receive_num = 0
                hb_dut_1_receive_num = send_packet_number
                hb_dut_2_receive_num = send_packet_number
            else:
                ha_dut_2_receive_num = send_packet_number
                hb_dut_1_receive_num = 0
                hb_dut_2_receive_num = 0
                for egress_port in egress_ports:
                    if egress_port == self.interfaces.dut_hb_1:
                        hb_dut_1_receive_num = send_packet_number
                    elif egress_port == self.interfaces.dut_hb_2:
                        hb_dut_2_receive_num = send_packet_number

            traffic_filter = f" src {packet['outer_sip']} and dst {packet['outer_dip']}"
            receive_packet_info = [{"receiver": 'hb', "interface": self.interfaces.hb_dut_1,
                                    "counter": hb_dut_1_receive_num, "filter": traffic_filter},
                                   {"receiver": 'hb', "interface": self.interfaces.hb_dut_2,
                                    "counter": hb_dut_2_receive_num, "filter": traffic_filter},
                                   {"receiver": 'ha', "interface": self.interfaces.ha_dut_2,
                                    "counter": ha_dut_2_receive_num, "filter": traffic_filter},
                                   ]
            self.ecmp_traffic.traffic_validation(players=self.players, ingress_port=ingress_port,
                                                 packet_info=packet_info, packet_type=packet_type,
                                                 send_packet_count=send_packet_number,
                                                 receive_packet_info=receive_packet_info)

    def find_egress_port_is_one_member_in_lag_or_vlan(self, packet_json_file_name, vrf=""):
        with allure.step("Generate test data"):
            packet_type = "outer_only"
            test_data = gen_test_data("outer_dip", packet_type, self.dut_mac)[0]
            test_data_list = []
            for i in range(1, 100):
                test_data["packet"]["outer_dip"] = f"50.50.50.{i}"
                test_data_list.append(copy.deepcopy(test_data))
        for test_data in test_data_list:
            packet = test_data["packet"]
            with allure.step(f'Gen packet json and copy to syncd container'):
                gen_packet_json_file(packet_type, packet, packet_json_file_name)
                copy_packet_json_to_syncd(self.dut_engine, packet_json_file_name)

            with allure.step(f'calculate egress port'):
                egress_ports = calculate_ecmp_egress_port(self.engines.dut, self.interfaces.dut_ha_1,
                                                          packet_json_file_name, vrf)
                if egress_ports[0] in [self.interfaces.dut_hb_1, self.interfaces.dut_hb_1]:
                    return test_data, egress_ports
        raise Exception("Not find egress port which is one member in lag or vlan")

    def case_without_fdb(self, vrf=""):
        """
        1. Find one egress port which is one vlan member or lag member, and generate test data
        2. Generate static arp
        3. Verify the calculated egress port include 2 ports, and all packet will be flooded from the calculated ports
        """
        try:
            with allure.step("Find one egress port which is one vlan member or lag member, and generate test data"):
                packet_json_file_name = f"packet_without_fdb_{vrf}.json"
                test_data, egress_port = self.find_egress_port_is_one_member_in_lag_or_vlan(packet_json_file_name, vrf)

            with allure.step("Generate static arp"):
                if vrf:
                    self.cli_objects.dut.ip.add_ip_neigh(
                        V4_CONFIG["hb_dut_1"], "0c:12:01:01:10:01", "Vlan300", action="replace")
                    self.cli_objects.dut.ip.add_ip_neigh(
                        V4_CONFIG["vlan_300_dut_hb_2"], "0c:12:01:01:10:02", "Vlan300", action="replace")

                else:
                    self.cli_objects.dut.ip.add_ip_neigh(
                        V4_CONFIG["ha_dut_2"], "0c:12:01:01:10:01", "Vlan200", action="replace")
                    self.cli_objects.dut.ip.add_ip_neigh(
                        V4_CONFIG["vlan_200_bond1"], "0c:12:01:01:10:02", "Vlan200", action="replace")

            with allure.step(f"Verify packet is flooding. {test_data['packet']['outer_dip']}"):
                self.verify_egress_ports_include_all_members_and_packet_is_flooding(
                    test_data["packet"], test_data["packet_type"],
                    packet_json_file_name=packet_json_file_name,
                    ingress_port=self.interfaces.ha_dut_1, vrf=vrf)
        except Exception as err:
            raise AssertionError(err)
        finally:
            with allure.step("Del arp"):
                self.cli_objects.dut.ip.del_static_neigh()


class TestInterfaceDefaultVrf(TestEcmpCalcBase):

    @pytest.mark.push_gate
    @pytest.mark.build
    @pytest.mark.physical_coverage
    @allure.title('Test ECMP Calculator default vrf')
    def test_ecmp_calculator_interface_default_vrf(self, pre_configure_for_interface_default_vrf):
        """
        This test is to verify the calculated interface is same as the actual one for interface with default vrf
        1. Calculate the egress port
        2. Verify the egress port is same as the actual port by sending traffic
        """
        with allure.step("Generate test data"):
            test_data_list = gen_test_data("outer_dip", "outer_only", self.dut_mac)

        with allure.step("Calculate egress port and verify it by sending packet"):
            self.calculate_egress_port_and_verify_by_sending_packet(
                test_data_list[0]["packet"], test_data_list[0]["packet_type"],
                packet_json_file_name="packet_int_default_vrf.json",
                ingress_port=self.interfaces.ha_dut_1)


class TestInterfaceVrf(TestEcmpCalcBase):

    @pytest.mark.parametrize("field, packet_type",
                             [("outer_dip", "outer_inner"),
                              ("outer_sip", "outer_only")])
    @allure.title('Test ECMP Calculator for interface vrf')
    def test_ecmp_calculator_interface_vrf(self, pre_configure_for_interface_vrf, field, packet_type):
        """
        This test is to verify the calculated interface is same as the actual one for interface vrf
        1. Calculate the egress port
        2. Verify the egress port is same as the actual port by sending traffic
        3. Repeat it with different field and packet
        """
        with allure.step("Generate test data"):
            test_data_list = gen_test_data(field, packet_type, self.dut_mac)

        for i, test_data in enumerate(test_data_list):
            with allure.step(
                    f"Calculate egress port and verify it by sending packet. Field is {field}, and the counter is {i}"):
                self.calculate_egress_port_and_verify_by_sending_packet(
                    test_data["packet"], test_data["packet_type"],
                    packet_json_file_name=f"packet_int_vrf_{field}_{i}.json",
                    ingress_port=self.interfaces.ha_dut_1, vrf="Vrf_ecmp")


class TestInterfaceVlanVrf(TestEcmpCalcBase):

    @pytest.mark.parametrize("field, packet_type",
                             [("outer_dport", "outer_only"), ("outer_sport", "outer_inner")])
    @allure.title('Test ECMP Calculator for vlan vrf')
    def test_ecmp_calculator_vlan_vrf(self, pre_configure_for_interface_vlan_vrf, field, packet_type):
        """
        This test is to verify the calculated interface is same as the actual one for ecmp for vlan vrf
        1. Calculate the egress port
        2. Verify the egress port is same as the actual port by sending traffic
        3. Repeat it with different field and packet
        """

        with allure.step("Generate test data"):
            test_data_list = gen_test_data(field, packet_type, self.dut_mac)

        for i, test_data in enumerate(test_data_list):
            with allure.step(
                    f"Calculate egress port and verify it by sending packet. Field is {field}, and the counter is {i}"):
                self.calculate_egress_port_and_verify_by_sending_packet(
                    test_data["packet"], test_data["packet_type"],
                    packet_json_file_name=f"packet_vlan_vrf_{field}_{i}.json",
                    ingress_port=self.interfaces.ha_dut_1, vrf="Vrf_ecmp")

    @allure.title('Test ecmp calculator vlan interface without fdb')
    def test_ecmp_calculator_vlan_int_without_fdb(self, pre_configure_for_interface_vlan_vrf):
        """
        This test is to verify calculated egress ports are two vlan members,
        and all packets will be flooded from the two ports, when fdb entry doesn't exist
        """
        self.case_without_fdb("Vrf_ecmp")

    @pytest.mark.parametrize("negative_case_type", NEGATIVE_CASE_TYPE)
    @allure.title('Test ECMP Calculator negative case')
    def test_ecmp_calculator_negative_case(self, pre_configure_for_interface_vlan_vrf, copy_negative_json_to_syncd,
                                           negative_case_type):
        """
        This test is to verify the return msg is correct or not when packet is not correct
        and ingress port is not physical port
        """
        packet_json_file_name = f'{negative_case_type}.json'
        msg_pattern = NEGATIVE_CASE_EXPECTED_MSG[negative_case_type]
        ingress_port = self.interfaces.dut_ha_1 if negative_case_type != "non_physical_ingress_port" else "Vlan200"
        with allure.step(f"Verify packet file {packet_json_file_name}"):
            cmd = f"docker exec syncd bash -c '/usr/bin/ecmp_calc.py -i {ingress_port} -p ./{packet_json_file_name} -v Vrf_ecmp'"
            calc_res = self.dut_engine.run_cmd(cmd)
            if not re.match(msg_pattern, calc_res):
                raise Exception(f"Return error is not correct. The expected msg:{msg_pattern}, the actual one is {calc_res}")


class TestSubInterface(TestEcmpCalcBase):

    @pytest.mark.parametrize("field, packet_type",
                             [("outer_smac", "outer_only"), ("inner_sip", "outer_inner")])
    @allure.title('Test ECMP Calculator for sub interface')
    def test_ecmp_calculator_sub_interface(self, pre_configure_for_sub_interface, field, packet_type):
        """
        This test is to verify the calculated interface is same as the actual one for sub interface
        1. Calculate the egress port
        2. Verify the egress port is same as the actual port by sending traffic
        3. Repeat it with different field and packet
        """
        with allure.step("Generate test data"):
            test_data_list = gen_test_data(field, packet_type, self.dut_mac)

        for i, test_data in enumerate(test_data_list):
            with allure.step(
                    f"Calculate egress port and verify it by sending packet. Field is {field}, and the counter is {i}"):
                self.calculate_egress_port_and_verify_by_sending_packet(
                    test_data["packet"], test_data["packet_type"],
                    packet_json_file_name=f"packet_sub_int_{field}_{i}.json",
                    ingress_port=f"{self.interfaces.ha_dut_1}.100")


class TestLag(TestEcmpCalcBase):

    @pytest.mark.parametrize("field, packet_type",
                             [("inner_proto", "outer_inner"), ("inner_dip", "outer_inner")])
    @allure.title('Test ECMP Calculator for lag')
    def test_ecmp_calculator_lag(self, pre_configure_for_lag, field, packet_type):
        """
        This test is to verify the calculated interface is same as the actual one for lag
        1. Calculate the egress port
        2. Verify the egress port is same as the actual port by sending traffic
        3. Repeat it with different field and packet
        """
        with allure.step("Generate test data"):
            test_data_list = gen_test_data(field, packet_type, self.dut_mac)

        for i, test_data in enumerate(test_data_list):
            with allure.step(
                    f"Calculate egress port and verify it by sending packet. Field is {field}, and the counter is {i}"):
                self.calculate_egress_port_and_verify_by_sending_packet(
                    test_data["packet"], test_data["packet_type"],
                    packet_json_file_name=f"packet_lag_{field}_{i}.json",
                    ingress_port=self.interfaces.ha_dut_1)


class TestVlanLag(TestEcmpCalcBase):

    @pytest.mark.parametrize("field, packet_type",
                             [("inner_next_header", "outer_inner"), ("inner_sip", "outer_inner")])
    @allure.title('Test ECMP Calculator for vlan lag')
    def test_ecmp_calculator_vlan_lag(self, pre_configure_for_vlan_lag, field, packet_type):
        """
        This test is to verify the calculated interface is same as the actual one for vlan lag
        1. Calculate the egress port
        2. Verify the egress port is same as the actual port by sending traffic
        3. Repeat it with different field and packet
        """
        with allure.step("Generate test data"):
            test_data_list = gen_test_data(field, packet_type, self.dut_mac)

        for i, test_data in enumerate(test_data_list):
            with allure.step(
                    f"Calculate egress port and verify it by sending packet. Field is {field}, and the counter is {i}"):
                self.calculate_egress_port_and_verify_by_sending_packet(
                    test_data["packet"], test_data["packet_type"],
                    packet_json_file_name=f"packet_vlan_lag_{field}_{i}.json",
                    ingress_port=self.interfaces.ha_dut_1)

    @allure.title('Test ecmp calculator vlan lag without fdb')
    def test_ecmp_calculator_vlan_lag_without_fdb(self, pre_configure_for_vlan_lag):
        """
        This test is to verify calculated egress ports are one interface member and one lag member,
        and all packets will be flooded from the two ports when fdb entry doesn't exist
        """
        self.case_without_fdb()


class TestSubInterfaceLag(TestEcmpCalcBase):

    @pytest.mark.parametrize("field, packet_type",
                             [("outer_smac", "outer_only"), ("inner_sip", "outer_inner")])
    @allure.title('Test ECMP Calculator for sub interface lag')
    def test_ecmp_calculator_sub_interface_lag(self, pre_configure_for_sub_interface_lag, field, packet_type):
        """
        This test is to verify the calculated interface is same as the actual one for sub interface lag
        1. Calculate the egress port
        2. Verify the egress port is same as the actual port by sending traffic
        3. Repeat it with different field and packet
        """
        with allure.step("Generate test data"):
            test_data_list = gen_test_data(field, packet_type, self.dut_mac)

        for i, test_data in enumerate(test_data_list):
            with allure.step(
                    f"Calculate egress port and verify it by sending packet. Field is {field}, and the counter is {i}"):
                self.calculate_egress_port_and_verify_by_sending_packet(
                    test_data["packet"], test_data["packet_type"],
                    packet_json_file_name=f"packet_sub_int_lag_{field}_{i}.json",
                    ingress_port=self.interfaces.ha_dut_1)

import allure
import logging
import pytest
import time

from ngts.tests.nightly.fdb.fdb_helper import traffic_validation, gen_test_interface_data, \
    DUMMY_MACS, verify_mac_saved_to_fdb_table, verify_mac_not_in_fdb_table
from infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker
from ngts.cli_wrappers.sonic.sonic_mac_clis import SonicMacCli
from ngts.cli_util.sonic_docker_utils import SwssContainer
from infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from retry.api import retry_call
from ngts.tests.nightly.fdb.fdb_helper import FDB_AGING_TIME

logger = logging.getLogger()

PKT_TYPE_LIST = ["arp_req", "arp_resp", "lldp", "icmp"]


@pytest.mark.usefixtures('pre_configure_for_fdb_basic')
class TestFdbBasic:

    @pytest.fixture(autouse=True)
    def setup(self, topology_obj, engines, cli_objects, interfaces, players, tested_asic_index):
        self.topology_obj = topology_obj
        self.engines = engines
        self.interfaces = interfaces
        self.players = players
        self.cli_objects = cli_objects
        self.src_mac = DUMMY_MACS[0]
        self.vlan_id = "40"
        self.receive_packet_counts = [1]
        self.port1 = self.interfaces.dut_ha_1
        self.port2 = self.interfaces.dut_ha_2
        self.tested_asic_index = tested_asic_index

    @pytest.mark.parametrize("pkt_type", PKT_TYPE_LIST)
    @allure.title('Test dynamic mac is learned')
    def test_dynamic_mac_learning(self, pkt_type):
        """
        Verify that dynamic mac can be learned for different packets.
        1. Clear fdb table
        2. Host A sends packet to Host B
        3. Verify source mac will be saved into fdb table
        :param pkt_type: packet type
        """
        with allure.step(f'Host A sends {pkt_type} packet to Host B'):
            interface_data = gen_test_interface_data(self.cli_objects, self.interfaces, self.vlan_id)
            for src_mac in DUMMY_MACS:
                traffic_validation(self.players, self.interfaces, interface_data, src_mac, pkt_type, self.receive_packet_counts)

        with allure.step(f"Verify source mac is saved into fdb table"):
            for src_mac in DUMMY_MACS:
                verify_mac_saved_to_fdb_table(self.cli_objects.dut, self.vlan_id, src_mac, self.port1)

    @allure.title('Test fdb aging time expire')
    def test_fdb_aging_time_expire(self, set_fdb_aging_time):
        """
        Verify after fdb aging time expire the corresponding fdb items will be cleared
        1. Clear fdb table
        2. Generate some fdb items
        3. Once fdb aging time expires, check the corresponding fdb items will be cleared
        :param set_fdb_aging_time: set_fdb_aging_time fixture
        """
        with allure.step(f'Generate some fdb items'):
            pkt_type = "icmp"
            with allure.step(f'Host A sends {pkt_type} packet to Host B'):
                interface_data = gen_test_interface_data(self.cli_objects, self.interfaces, self.vlan_id)
                for src_mac in DUMMY_MACS:
                    traffic_validation(self.players, self.interfaces, interface_data, src_mac, pkt_type, self.receive_packet_counts)

        with allure.step(f"Once fdb aging time expires, check the corresponding fdb items will be cleared"):
            fdb_aging_time = int(FDB_AGING_TIME) * 2
            logging.info(f" Sleep {fdb_aging_time} to wait fdb aging time expire.....")
            time.sleep(fdb_aging_time)
            for src_mac in DUMMY_MACS:
                verify_mac_not_in_fdb_table(self.cli_objects.dut, self.vlan_id, src_mac, self.port1)

    @allure.title('Test mac move')
    def test_mac_move(self):
        """
        Verify fdb table will updated when mac move
        1. Clear fdb table
        2. Host A sends packet to Host B from ha-dut-1 with tested mac
        3. Verify tested mac has been save into the fdb table with the port dut-ha-1
        4. Host A sends packet to Host B from ha-dut-2 with the same mac
        5. Verify tested mac has been updated into the fdb table with port dut-ha-2
        """
        with allure.step(f'Host A sends packet to Host B from ha-dut-1 with tested mac'):
            self.generate_dynamic_fdb_item()
        with allure.step(f'Verify tested mac has been saved into the fdb table with the port dut-ha-1'):
            verify_mac_saved_to_fdb_table(self.cli_objects.dut, self.vlan_id, self.src_mac, self.port1)

        with allure.step(f"Host A sends packet to Host B from ha-dut-2 with the same mac"):
            interface_data = gen_test_interface_data(self.cli_objects, self.interfaces, self.vlan_id)
            interface_data["sender_interface"] = self.interfaces.ha_dut_2
            traffic_validation(self.players, self.interfaces, interface_data, self.src_mac, "icmp", self.receive_packet_counts)

        with allure.step(f"Verify tested mac has been updated into the fdb table with port dut-ha-2"):
            verify_mac_saved_to_fdb_table(self.cli_objects.dut, self.vlan_id, self.src_mac, self.port2)

    @allure.title('Test fdb forwarding when destination mac in fdb table')
    def test_fdb_forwarding_with_destination_mac_in_fdb_table(self):
        """
        Verify the corresponding packets will be forwarded from the specified port when destination mac is in fdb table
        1. Clear fdb table
        2. Generate destination mac of Host B in fdb table
        3. Host A send packet to Host B
        4. Verify the packet will forward from the corresponding port
        """
        with allure.step('Generate destination mac of Host B in fdb table'):
            self.generate_destination_fdb_item()
        with allure.step('Host A send packet to Host B'):
            interface_data = gen_test_interface_data(self.cli_objects, self.interfaces, self.vlan_id)
            receive_packet_counts = [1, 0]
            traffic_validation(self.players, self.interfaces, interface_data, self.src_mac, "icmp", receive_packet_counts)

    @allure.title('Test fdb forwarding without destination mac in fdb table')
    def test_fdb_forwarding_without_destination_mac_in_fdb_table(self):
        """
        Verify the corresponding packets will be broadcast when destination mac is not in fdb table
        1. Clear fdb table
        2. Host A send packet to Host B
        3. Verify the packet will broadcast
        """
        with allure.step("Verify the packet will be broadcast from the corresponding port"):
            interface_data = gen_test_interface_data(self.cli_objects, self.interfaces, self.vlan_id)
            interface_data["dst_mac"] = DUMMY_MACS[1]
            receive_packet_counts = [1, 1]
            traffic_validation(self.players, self.interfaces, interface_data, self.src_mac, "icmp", receive_packet_counts)

    @allure.title('Test static fdb override dynamic fdb')
    def test_static_fdb_override_dynamic_fdb(self):
        """
        Verify static fdb will override dynamic fdb
        1. Clear fdb table
        2. Generate one dynamic fdb item
        3. Write static fdb to override dynamic fdb
        4. Verify static fdb take effect by sending traffic
        """
        try:
            with allure.step('Generate one dynamic fdb item'):
                self.generate_dynamic_fdb_item()
            with allure.step("Write static fdb to override dynamic fdb"):
                self.generate_static_fdb_item()
            with allure.step("Verify static fdb take effect by  sending traffic"):
                self.send_packet_from_hb()

        except Exception as err:
            raise AssertionError(err)
        finally:
            self.delete_static_fdb_item()

    @allure.title('Test dynamic fdb cannot override static fdb')
    def test_dynamic_fdb_cannot_override_static_fdb(self):
        """
        Verify static fdb will override dynamic_fdb
        1. Clear fdb table
        2. Generate one static fdb item
        3. Generate one dynamic fdb item with the same mac
        4. Verify static fdb is not updated
        """
        try:
            with allure.step('Generate one static fdb item'):
                self.generate_static_fdb_item()
            with allure.step("Generate one dynamic fdb item with the same mac"):
                self.generate_dynamic_fdb_item()
            with allure.step("Verify static fdb is not updated"):
                verify_mac_saved_to_fdb_table(self.cli_objects.dut, self.vlan_id, self.src_mac, self.port2, fdb_type="static")

        except Exception as err:
            raise AssertionError(err)
        finally:
            self.delete_static_fdb_item()

    def generate_destination_fdb_item(self):
        """
        Generate destination fdb item in fdb table
        """
        dst_ip = "40.0.0.1"
        src_iface = self.interfaces.hb_dut_1
        with allure.step('hb ping ha'):
            validation = {'sender': 'hb', 'args': {'interface': src_iface, 'count': 3, 'dst': dst_ip}}
            ping = PingChecker(self.players, validation)
            logger.info('Sending 3 ping packets to {} from interface {}'.format(dst_ip, src_iface))
            ping.run_validation()

        with allure.step(f'Verify tested mac has been save into the fdb table with the port dut-ha-1'):
            port = self.interfaces.dut_hb_1
            cli_obj = self.topology_obj.players['hb']['cli']
            src_mac = cli_obj.mac.get_mac_address_for_interface(self.interfaces.hb_dut_1)
            verify_mac_saved_to_fdb_table(self.cli_objects.dut, self.vlan_id, src_mac, port)

    def send_packet_from_hb(self):
        """
        Send icmp packet from hb, and check ha receive the packet on ha_dut_2, and doesn't receive the packet on ha_dut_1
        """
        pkt = f'Ether(dst="{self.src_mac}")/IP(dst="40.0.0.2")/ICMP()'
        tcpdump_filter = '{} && (ether dst host {})'
        validation = {'sender': "hb",
                      'send_args': {'interface': self.interfaces.hb_dut_1,
                                    'packets': pkt, 'count': 1},
                      'receivers':
                          [
                              {'receiver': "ha",
                               'receive_args': {'interface': self.interfaces.ha_dut_1,
                                                'filter': tcpdump_filter.format("icmp", self.src_mac),
                                                'count': 0,
                                                'timeout': 20}},
                              {'receiver': "ha",
                               'receive_args': {'interface': self.interfaces.ha_dut_2,
                                                'filter': tcpdump_filter.format("icmp", self.src_mac),
                                                'count': 1,
                                                'timeout': 20}},
                      ]
                      }

        logger.info('Hb Sending traffic')
        scapy_checker = ScapyChecker(self.players, validation)
        retry_call(scapy_checker.run_validation, fargs=[], tries=3, delay=10, logger=logger)

    def generate_static_fdb_item(self):
        """
        Generate static fdb item
        """
        fdb_conf_set = SonicMacCli.generate_fdb_config(1, self.vlan_id, self.port2, "SET", fdb_type="static")
        SwssContainer.apply_config(self.engines.dut, fdb_conf_set, asic_id_extension=self.cli_objects.dut.multi_asic_cli.multi_asic_docker_cmd_ext)
        verify_mac_saved_to_fdb_table(self.cli_objects.dut, self.vlan_id, self.src_mac, self.port2, fdb_type="static")

    def generate_dynamic_fdb_item(self):
        """
        Generate dynamic fdb item
        """
        interface_data = gen_test_interface_data(self.cli_objects, self.interfaces, self.vlan_id)
        traffic_validation(self.players, self.interfaces, interface_data, self.src_mac, "icmp", self.receive_packet_counts)

    def delete_static_fdb_item(self):
        """
        Delete static fdb item
        """
        fdb_conf_set = SonicMacCli.generate_fdb_config(1, self.vlan_id, self.port2, "DEL", fdb_type="static")
        SwssContainer.apply_config(self.engines.dut, fdb_conf_set, asic_id_extension=self.cli_objects.dut.multi_asic_cli.multi_asic_docker_cmd_ext)
        verify_mac_not_in_fdb_table(self.cli_objects.dut, self.vlan_id, self.src_mac, self.port2, fdb_type="static")

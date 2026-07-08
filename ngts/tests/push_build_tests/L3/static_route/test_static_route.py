import allure
import logging
import pytest

from devts.infra.tools.validations.traffic_validations.ping.ping_runner import PingChecker
from devts.infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from ngts.cli_util.verify_cli_show_cmd import verify_show_cmd
from retry.api import retry_call
from ngts.config_templates.route_config_template import RouteConfigTemplate

"""

 Static Route Test Cases

 Documentation: https://wikinox.mellanox.com/display/SW/SONiC+NGTS+Static+Routes+Documentation

"""

logger = logging.getLogger()


@pytest.fixture(autouse=True)
def static_route_configuration(topology_obj):
    static_route_config_dict = {
        'dut': [{'dst': '20.0.0.10', 'dst_mask': 32, 'via': ['69.0.0.2']},
                {'dst': '20.0.0.1', 'dst_mask': 32, 'via': ['PortChannel0001']},
                {'dst': '20.0.0.0', 'dst_mask': 24, 'via': ['30.0.0.2']},
                {'dst': '2000::10', 'dst_mask': 128, 'via': ['6900::2']},
                {'dst': '2000::1', 'dst_mask': 128, 'via': ['Vlan69']},
                {'dst': '2000::', 'dst_mask': 64, 'via': ['3000::2']}
                ]
    }

    RouteConfigTemplate.configuration(topology_obj, static_route_config_dict)

    yield

    RouteConfigTemplate.cleanup(topology_obj, static_route_config_dict)


@pytest.mark.build
@pytest.mark.push_gate
@allure.title('Test Basic Static Route')
def test_basic_static_route(is_simx, cli_objects, interfaces, players):
    """
    This test will check basic static route functionality.
    :return: raise assertion error in case when test failed
    """

    try:
        # TODO: Workaround for bug https://redmine.mellanox.com/issues/2350931
        validation_create_arp_1_ipv4 = {'sender': 'hb', 'args': {'interface': 'bond0.69', 'count': 3, 'dst': '69.0.0.1'}}
        ping_checker_hb = PingChecker(players, validation_create_arp_1_ipv4)
        retry_call(ping_checker_hb.run_validation, fargs=[], tries=3, delay=10, logger=logger)

        validation_create_arp_1_ipv6 = {'sender': 'hb', 'args': {'interface': 'bond0.69', 'count': 3, 'dst': '6900::1'}}
        ping_checker_hb_v6 = PingChecker(players, validation_create_arp_1_ipv6)
        retry_call(ping_checker_hb_v6.run_validation, fargs=[], tries=3, delay=10, logger=logger)

        validation_create_arp_2_ipv4 = {'sender': 'ha', 'args': {'interface': 'bond0', 'count': 3, 'dst': '30.0.0.1'}}
        ping_checker_ha = PingChecker(players, validation_create_arp_2_ipv4)
        retry_call(ping_checker_ha.run_validation, fargs=[], tries=3, delay=10, logger=logger)

        validation_create_arp_2_ipv6 = {'sender': 'ha', 'args': {'interface': 'bond0', 'count': 3, 'dst': '3000::1'}}
        ping_checker_ha_v6 = PingChecker(players, validation_create_arp_2_ipv6)
        retry_call(ping_checker_ha_v6.run_validation, fargs=[], tries=3, delay=10, logger=logger)
        # TODO: End workaround for bug https://redmine.mellanox.com/issues/2350931

        # Test started here
        with allure.step('Check that static routes IPv4 on switch using CLI'):
            verify_show_cmd(cli_objects.dut.route.show_ip_route(route='20.0.0.10/32'),
                            expected_output_list=[(r'\*\s69.0.0.2, via Vlan69', True)])
            verify_show_cmd(cli_objects.dut.route.show_ip_route(route='20.0.0.1'),
                            expected_output_list=[(r'\*\s+directly connected, PortChannel0001', True)])
            verify_show_cmd(cli_objects.dut.route.show_ip_route(route='20.0.0.0'),
                            expected_output_list=[(r'\*\s30.0.0.2, via PortChannel0001', True)])

        with allure.step('Check that static routes IPv6 on switch using CLI'):
            verify_show_cmd(cli_objects.dut.route.show_ip_route(route='2000::10/128', ipv6=True),
                            expected_output_list=[(r'\*\s6900::2, via Vlan69', True)])
            verify_show_cmd(cli_objects.dut.route.show_ip_route(route='2000::1', ipv6=True),
                            expected_output_list=[(r'\* directly connected, Vlan69', True)])
            verify_show_cmd(cli_objects.dut.route.show_ip_route(route='2000::', ipv6=True),
                            expected_output_list=[(r'\*\s3000::2, via PortChannel0001', True)])

        dut_mac = cli_objects.dut.mac.get_mac_address_for_interface(interfaces.dut_ha_1)
        hadut2_mac = cli_objects.ha.mac.get_mac_address_for_interface(interfaces.ha_dut_2)
        sender_interface = '{}.40'.format(interfaces.ha_dut_2)
        receiver_interface_ha = 'bond0'
        receiver_interface_hb = 'bond0.69'
        pkt_ipv4 = 'Ether(dst="{}", src="{}")/IP(dst="{}", src="1.2.3.4")/TCP()'
        pkt_ipv6 = 'Ether(dst="{}", src="{}")/IPv6(dst="{}", src="1234::5678")/TCP()'
        validation_tries_num = 3 if is_simx else 1

        with allure.step('Functional check IPv4 static route via Interface'):
            logger.info('Functional checking IPv4 static route via Interface')
            dst_ip = '20.0.0.1'
            pkt = pkt_ipv4.format(dut_mac, hadut2_mac, dst_ip)
            # Filter below will catch ARP packet with DST IP 20.0.0.1(Who has 20.0.0.1 ....)
            tcpdump_filter = 'arp[24:4]==0x14000001'
            validation_1 = {'sender': 'ha',
                            'send_args': {'interface': sender_interface, 'packets': pkt, 'count': 3},
                            'receivers':
                                [
                                    {'receiver': 'ha', 'receive_args': {'interface': receiver_interface_ha,
                                                                        'filter': tcpdump_filter,
                                                                        'count': 1}}
                            ]
                            }
            ipv4_iface_route = ScapyChecker(players, validation_1)
            retry_call(ipv4_iface_route.run_validation, fargs=[], tries=validation_tries_num, delay=5, logger=logger)

        with allure.step('Functional check IPv4 /32 static route'):
            logger.info('Functional checking IPv4 /32 static route')
            dst_ip = '20.0.0.10'
            pkt = pkt_ipv4.format(dut_mac, hadut2_mac, dst_ip)
            tcpdump_filter = 'host 20.0.0.10'
            validation_2 = {'sender': 'ha',
                            'send_args': {'interface': sender_interface, 'packets': pkt, 'count': 3},
                            'receivers':
                                [
                                    {'receiver': 'ha', 'receive_args': {'interface': receiver_interface_ha,
                                                                        'filter': tcpdump_filter, 'count': 0}},
                                    {'receiver': 'hb', 'receive_args': {'interface': receiver_interface_hb,
                                                                        'filter': tcpdump_filter,
                                                                        'count': 1}}
                            ]
                            }
            ipv4_32_route = ScapyChecker(players, validation_2)
            retry_call(ipv4_32_route.run_validation, fargs=[], tries=validation_tries_num, delay=5, logger=logger)

        with allure.step('Functional check IPv4 /24 static route'):
            logger.info('Functional checking IPv4 /24 static route')
            dst_ip = '20.0.0.100'
            pkt = pkt_ipv4.format(dut_mac, hadut2_mac, dst_ip)
            tcpdump_filter = 'host 20.0.0.100'
            validation_3 = {'sender': 'ha',
                            'send_args': {'interface': sender_interface, 'packets': pkt, 'count': 3},
                            'receivers':
                                [
                                    {'receiver': 'ha', 'receive_args': {'interface': receiver_interface_ha,
                                                                        'filter': tcpdump_filter, 'count': 1}}
                            ]
                            }
            ipv4_24_route = ScapyChecker(players, validation_3)
            retry_call(ipv4_24_route.run_validation, fargs=[], tries=validation_tries_num, delay=5, logger=logger)

        with allure.step('Functional check IPv6 static route via Interface'):
            logger.info('Functional checking IPv6 static route via Interface')
            dst_ip = '2000::1'
            pkt = pkt_ipv6.format(dut_mac, hadut2_mac, dst_ip)
            # Filter below fill catch Neighbour Solicitation message TODO: need to make it more precise
            tcpdump_filter = 'icmp6 && ip6[40]==135'
            validation_4 = {'sender': 'ha',
                            'send_args': {'interface': sender_interface, 'packets': pkt, 'count': 3},
                            'receivers':
                                [
                                    {'receiver': 'hb', 'receive_args': {'interface': receiver_interface_hb,
                                                                        'filter': tcpdump_filter, 'count': 1}}
                            ]
                            }
            ipv6_iface_route = ScapyChecker(players, validation_4)
            retry_call(ipv6_iface_route.run_validation, fargs=[], tries=validation_tries_num, delay=5,
                       logger=logger)

        with allure.step('Functional check IPv6 /128 static route'):
            logger.info('Functional checking IPv6 /128 static route')
            dst_ip = '2000::10'
            pkt = pkt_ipv6.format(dut_mac, hadut2_mac, dst_ip)
            tcpdump_filter = 'host 2000::10'
            validation_5 = {'sender': 'ha',
                            'send_args': {'interface': sender_interface, 'packets': pkt, 'count': 3},
                            'receivers':
                                [
                                    {'receiver': 'ha', 'receive_args': {'interface': receiver_interface_ha,
                                                                        'filter': tcpdump_filter, 'count': 0}},
                                    {'receiver': 'hb', 'receive_args': {'interface': receiver_interface_hb,
                                                                        'filter': tcpdump_filter, 'count': 1}}
                            ]
                            }
            ipv6_128_route = ScapyChecker(players, validation_5)
            retry_call(ipv6_128_route.run_validation, fargs=[], tries=validation_tries_num, delay=5, logger=logger)

        with allure.step('Functional check IPv6 /64 static route'):
            logger.info('Functional checking IPv6 /64 static route')
            dst_ip = '2000::100'
            pkt = pkt_ipv6.format(dut_mac, hadut2_mac, dst_ip)
            tcpdump_filter = 'host 2000::100'
            validation_6 = {'sender': 'ha',
                            'send_args': {'interface': sender_interface, 'packets': pkt, 'count': 3},
                            'receivers':
                                [
                                    {'receiver': 'ha', 'receive_args': {'interface': receiver_interface_ha,
                                                                        'filter': tcpdump_filter, 'count': 1}}
                            ]
                            }
            ipv6_64_route = ScapyChecker(players, validation_6)
            retry_call(ipv6_64_route.run_validation, fargs=[], tries=validation_tries_num, delay=5, logger=logger)

    except Exception as err:
        raise AssertionError(err)

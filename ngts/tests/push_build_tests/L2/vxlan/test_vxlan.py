import allure
import pytest
import logging

from retry.api import retry_call
from infra.tools.validations.traffic_validations.scapy.scapy_runner import ScapyChecker
from ngts.tests.push_build_tests.conftest import is_vxlan_evpn_configuration_supported

logger = logging.getLogger()

"""

 VXLAN L2 Test Cases

 Documentation: https://wikinox.mellanox.com/pages/viewpage.action?spaceKey=SW&title=SONiC+NGTS+L2+VXLAN+Documentation

"""


@pytest.mark.build
@pytest.mark.physical_coverage
@pytest.mark.push_gate
@allure.title('VXLAN Decap test case')
def test_vxlan_decap(engines, players, cli_objects, upgrade_params):
    """
    Test checks that encapsulated VXLAN traffic pass via VXLAN tunnel from HA via DUT and decapsulated to HB
    Test has next steps:
    1. Check that tunnel configured using command "show vxlan tunnel"
    2. Check mapping VLAN to VNI using command "show vxlan vlanvnimap"
    3. Send VXLAN VNI 76543 encapsulated traffic from HA and check that traffic arrived to HB without VXLAN header

                                            dut
                                       -------------------------------
             ha                        | Loopback0 10.1.0.32/32      |                                  hb
      ---------------------------      |                             |               ----------------------------
      | bond0 30.0.0.2/24       |------| PortChannel0001 30.0.0.1/24 |               |                          |
      |                         |      |                             |               |                          |
      |                         |      |                             |               |                          |
      |                         |      |              PortChannel0002|---------------| bond0.69                 |
      ---------------------------      |                    Vlan69   |               ----------------------------
                                       |                             |
                                       -------------------------------
    """
    if upgrade_params.is_upgrade_required:
        pytest.skip('PushGate with upgrade executed. Test not supported on branch 201911 which used as base version')
    if not is_vxlan_evpn_configuration_supported():
        pytest.skip('VXLAN EVPN configuration is not supported')

    vlan = '69'
    vni = '76543'
    loopback_ip = '10.1.0.32'

    # TODO: temporary removed, once EVPN VXLAN support implemented - need to restore and fix
    # with allure.step('Checking that VXLAN tunnel configured'):
    #     expected_tunnel_info = {'vxlan tunnel name': 'vtep101032',
    #                             'source ip': loopback_ip,
    #                             'destination ip': '',
    #                             'tunnel map name': 'map_{}_Vlan{}'.format(vni, vlan),
    #                             'tunnel map mapping(vni -> vlan)': '{} -> Vlan{}'.format(vni, vlan)}
    #
    #     cli_objects.dut.vxlan.check_vxlan_tunnels(engines.dut, expected_tunnels_info_list=[expected_tunnel_info])

    with allure.step('Checking VLAN {} mapping to VNI {}'.format(vlan, vni)):
        cli_objects.dut.vxlan.check_vxlan_vlanvnimap(vlan_vni_map_list=[(vlan, vni)])

    with allure.step('Validate decapsulation of VXLAN traffic. Send traffic from HA with VNI {}'.format(vni)):
        main_src_mac = cli_objects.ha.mac.get_mac_address_for_interface('bond0')
        main_dst_mac = cli_objects.dut.mac.get_mac_address_for_interface('PortChannel0001')
        encap_src_mac = '0e:2e:96:af:9d:c0'

        pkt = 'Ether(dst="{}", src="{}")/IP(dst="{}", src="10.1.1.32")/' \
              'UDP()/VXLAN(vni=76543, flags=8)/Ether(dst="ff:ff:ff:ff:ff:ff", src="{}")/' \
              'ARP()'.format(main_dst_mac, main_src_mac, loopback_ip, encap_src_mac)

        validation = {'sender': 'ha', 'send_args': {'interface': 'bond0',
                                                    'packets': pkt,
                                                    'count': 3},
                      'receivers':
                          [
                              {'receiver': 'hb', 'receive_args': {'interface': 'bond0.{}'.format(vlan),
                                                                  'filter': 'ether host {}'.format(encap_src_mac),
                                                                  'count': 3}}
        ]
        }
        logger.info('Validate decapsulation of VXLAN traffic. '
                    'Sending 3 untagged packets from HA vxlan {} to HB bond0.{}'.format(vni, vlan))
        scapy_checker = ScapyChecker(players, validation)
        retry_call(scapy_checker.run_validation, fargs=[], tries=3, delay=5, logger=logger)

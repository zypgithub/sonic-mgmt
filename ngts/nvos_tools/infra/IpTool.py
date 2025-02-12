import logging
import random
import re
from typing import List

import allure

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import IbConsts, IpConsts
from ngts.nvos_tools.infra import ExceptionTool
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.infra.NvCommand import NvCommand
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj

logger = logging.getLogger()


class IpTool:
    @staticmethod
    def select_random_ipv4_address():
        """
        generate random ip, no multicast, no loopback, changed func to generate ip, not related to NVOS  Lab ip's,
        details in https://redmine.mellanox.com/issues/3242156
        :return: IP as a string (all the fields are 1-254)
        """
        with allure.step('Select random ipv4_address'):
            result_obj = ResultObj(True, "")
            msb_list = list(range(14, 127)) + list(range(128, 200))
            msb = random.choice(msb_list)
            result_obj.returned_value = ('{0}.{1}.{2}.{3}/{4}'.format(msb, random.randint(1, 254),
                                                                      random.randint(1, 254), random.randint(1, 254),
                                                                      random.randint(8, 32)))
            return result_obj

    @staticmethod
    def select_random_ipv6_address():
        """
        generate random ip, no multicast, no loopback
        :return: IP as a string (all the fields are 1-254)
        """
        with allure.step('Select random ipv4_address'):
            result_obj = ResultObj(True, "")
            ip_addr = ':'.join('{:x}'.format(random.
                                             randint(IpConsts.MIN_IPV6_GROUP_VALUE, IpConsts.MAX_IPV6_GROUP_VALUE))
                               for _ in range(8))

            result_obj.returned_value = ip_addr + ('/{0}'.format(random.randint(1, 128)))
            return result_obj

    @staticmethod
    def hex_to_ipv4(hex_address):
        """
        @Summary:
            Given hex string, convert it to ip address (ipv4)
        @param hex_address:
            hex address, eg. 0x0a07903e
        @return:
            ipv4 address - eg. -> 0x0a07903e --> 10.7.144.62
        """
        hex_address = hex_address.split(IpConsts.HEX_PREFIX)[-1]
        hex_address = [hex_address[i:i + 2] for i in range(0, len(hex_address), 2)]
        digits = []
        for num in hex_address:
            digits.append(str(int(num, 16)))
        ip_address = '.'.join(digits)
        return ip_address

    @staticmethod
    def hex_to_ipv6(hex_address):
        """
        @Summary:
            This function will convert hex string to ipv6 address
        @param hex_address:
            Hex address:  0xfdfdfdfd000701450000000010002295
        @return:
            IPV6 String: fdfd:fdfd:7:145::1000:2295
        """
        hex_address = hex_address.split(IpConsts.HEX_PREFIX)[-1]
        if hex_address == IpConsts.IPV6_HEX_ZERO:
            ipv6_address = IpConsts.IPV6_ZERO
        else:
            hex_address = [hex_address[i:i + 4] for i in range(0, len(hex_address), 4)]
            ipv6_address = ':'.join(hex_address)
            address = ":".join('' if i == '0000' else i.lstrip('0') for i in ipv6_address.split(':'))
            ipv6_address = (re.sub(r'(:)\1+', r'\1\1', address).lower())
        return ipv6_address

    @staticmethod
    def send_ufm_mad(host_obj, directory, modifier='0'):
        """
        @Summary: This function will send a MAD from the host to the wanted asic by LID
        @param host_obj: Host object.
        @param directory: location to run nvmad
        @param modifier: '0' for eth0, '1' for eth1
        @return: The MAD's output - > example:
            -I- received response length:256
            LID                                               : 1
            QPN                                               : 0x000001
            MAD.base_version                                  : 0x01
            MAD.mgmt_class                                    : 0x0a
            MAD.class_version                                 : 0x01
            MAD.method                                        : 0x81
            MAD.status                                        : 0x0000
            MAD.tid                                           : 0x00009e5500000002
            MAD.attr_id                                       : 0x0053
            MAD.modifier                                      : 0x00000000
            MAD.Vend_Key                                      : 0x0000000000000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv4[0].ipv4         : 0x00000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv4[0].netmask      : 0x00000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv4[1].ipv4         : 0x00000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv4[1].netmask      : 0x00000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv4[2].ipv4         : 0x00000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv4[2].netmask      : 0x00000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv4[3].ipv4         : 0x00000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv4[3].netmask      : 0x00000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv6[0].ipv6         : 0x00000000000000000000000000000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv6[0].netmask      : 0x00000000000000000000000000000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv6[1].ipv6         : 0x00000000000000000000000000000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv6[1].netmask      : 0x00000000000000000000000000000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv6[2].ipv6         : 0x00000000000000000000000000000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv6[2].netmask      : 0x00000000000000000000000000000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv6[3].ipv6         : 0x00000000000000000000000000000000
            MAD.GMP.VS.SwitchNetworkInfo.IPv6[3].netmask      : 0x00000000000000000000000000000000
        """
        result_obj = ResultObj(True, "")

        with allure.step("find card to host - e.g. mlx5_8"):
            card = host_obj.run_cmd(IbConsts.IB_DEV_2_NET_DEV, validate=True).split()
            hca = card[0]
            port_state = card[-1].strip('()')

        if port_state != IpConsts.PORT_STATE_UP:
            result_obj.result = False
            result_obj.info = f"Host ib port state is {port_state} instead of {IpConsts.PORT_STATE_UP}"
        else:
            with allure.step("find lid"):
                # LID assigned by SM. The mad will be sent to this lid value
                lid = host_obj.run_cmd(IbConsts.IBSWITCHES, validate=True).split('lid')[-1].split()[0]

            with allure.step("Sending MAD to lid: {}".format(lid)):
                result_obj.returned_value = host_obj.run_cmd(
                    IpConsts.MAD_TEMPLATE.format(python_path=IpConsts.PYTHON_PATH, nvmad_path=directory, lid=lid,
                                                 card=hca, modifier=modifier),
                    validate=True)

        return result_obj

    @staticmethod
    def parse_mad_output(mad_output):
        """
        @Summary:
            This function will parse the Mad output and return a dict of the required fields.
            IPV4, IPV6 And their netmasks
        @param mad_output: The output of the UFM MAD output.
        @return: Dict:
            {'ipv4': '10.7.144.153',
            'ipv6': 'fdfd:fdfd:7:145::1000:4804',
            'ipv4_netmask': '255.255.248.0',
            'ipv6_netmask': 'ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff'}
        """
        dispatcher = {IpConsts.HEX_TO_IPV4: IpTool.hex_to_ipv4, IpConsts.HEX_TO_IPV6: IpTool.hex_to_ipv6}
        mad_output_list = mad_output.split('\n')
        mad_output_list.reverse()
        ips_dict = {}
        for out in mad_output_list:
            for prefix, prop in IpConsts.MAD_DICT.items():
                if prefix in out:
                    out = out.split(":")[-1]
                    ips_dict[prop[IpConsts.ADDR]] = dispatcher[prop[IpConsts.FUNC]](out)
                    break
            if len(ips_dict) == IpConsts.NUMBER_OF_ADDRESSES_IN_MAD_RESPONSE:
                break
        return ips_dict

    @staticmethod
    def get_mac_address(host_obj, interface: str) -> str:
        command = "cat /sys/class/net/{}/address".format(interface)
        mac_address = host_obj.run_cmd(command)
        return mac_address

    @staticmethod
    def run_tcpdump(engine, interface: str, filter: str, params: str = '') -> str:
        command = "sudo tcpdump -i {0} {1} {2}".format(interface, filter, params)
        tcpdump_output = engine.run_cmd(command)
        return tcpdump_output

    @staticmethod
    def get_player_ipv4_addr(dut_engine) -> str:
        ipv4_pattern = 'src\\s+(\\d+\\.\\d+\\.\\d+\\.\\d+)'
        output = CmdRunner('IpTool').run_cmd(f'ip -o route get {dut_engine.ip}')
        matches = re.findall(ipv4_pattern, output)
        assert matches, f'could not find ipv4 address of the player.\nip route output: {output}'
        return matches[0]

    @staticmethod
    def get_dut_ipv6_addr_of_given_eth_interface_using_nv_cli(eth_interface_name: str, dut_engine: LinuxSshEngine = None) -> str:
        try:
            ipv6_pattern = r'([0-9a-fA-F:]+)/64'
            out = dut_engine.run_cmd(f'nv show interface {eth_interface_name} ip address -o json', validate=True)
            no_cli_msgs = ['Error', 'NVOS CLI is unavailable', 'System is initializing', 'This may take a few minutes']
            if any(msg in out for msg in no_cli_msgs):
                return ''
            out_dict = OutputParsingTool.parse_json_str_to_dictionary(out).get_returned_value()
            addresses = list(out_dict.keys())
            for address in addresses:
                matches = re.findall(ipv6_pattern, address)
                if matches:
                    return matches[0]
            return ''
        except Exception as e:
            logging.warning(f'failed to get ipv6 address for interface {eth_interface_name}: {ExceptionTool.format_traceback()}')
            return ''

    @staticmethod
    def get_player_ipv6_addr(player_ipv4_addr: str, player_engine: LinuxSshEngine = None) -> str:
        ipv6_pattern = r'inet6\s+([0-9a-fA-F:]+)/64'

        def _is_interface_line(s: str) -> bool:
            return bool(re.match(r'^\d+: ', s))

        def _split_interfaces(all_lines: List[str]) -> List[str]:
            interfaces = []
            for line in all_lines:
                if _is_interface_line(line):
                    interfaces.append([line])
                else:
                    assert isinstance(interfaces[-1],
                                      list), f'cannot add the line to any added interface.\noutput:\n{all_lines}'
                    interfaces[-1].append(line)
            return ['\n'.join(interface) for interface in interfaces]

        player_engine = player_engine or CmdRunner('IpTool')
        out_lines = player_engine.run_cmd('ip addr').split('\n')
        interfaces = _split_interfaces(out_lines)

        for interface in interfaces:
            if player_ipv4_addr not in interface:
                continue
            interface_ipv6_addresses = re.findall(ipv6_pattern, interface)
            if not interface_ipv6_addresses:
                logging.warning(f'interface of {player_ipv4_addr} has no inet6 records.\n\ninterface:\n{interface}\n\nall output:\n{interfaces}')
                return ''
            # assert interface_ipv6_addresses, f'interface of {player_ipv4_addr} has no inet6 records.\n\ninterface:\n{interface}\n\nall output:\n{interfaces}'
            logging.info(f'ipv6 address of interface: {interface_ipv6_addresses[0]}')
            return interface_ipv6_addresses[0]

        raise ValueError(
            f'could not find ipv6 address that is attached to same interface as given ipv4 address: {player_ipv4_addr}')

    @staticmethod
    def is_address_ipv6(address: str) -> bool:
        pattern = r'^(?:[A-F0-9]{1,4}:){7}[A-F0-9]{1,4}$'
        return bool(re.match(pattern, address, re.IGNORECASE))

    @staticmethod
    def is_dhcp_client6_has_lease(engine: LinuxSshEngine = None) -> bool:
        with allure.step('Run show command on mgmt port and verify that each field has an appropriate value'):
            output_dictionary = OutputParsingTool.parse_show_output_to_dict(
                NvCommand().port['eth0'].interface.ip.dhcp_client6.show(dut_engine=engine)).get_returned_value()
            return output_dictionary['has-lease'] == 'yes'

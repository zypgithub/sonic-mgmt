#!/usr/bin/env python
from scapy.all import *
import scapy.all as scapy
import sys
import argparse
import random


def SetPacketSize(p, size):
    currentSize = len(p)
    if currentSize < size:
        padding = size - currentSize
        p = p / Raw(RandString(size=padding))
    return p


def get_route_from_tg_type(tg_type):
    if tg_type == "left_tg":
        route_ip = "130.130.130.0/24"
    elif tg_type == "right_tg":
        route_ip = "110.110.110.0/24"
    else:
        raise AssertionError(f"Wrong traffic generator type was provided - {tg_type} is invalid traffic generator")

    return route_ip


def get_ids_from_tg_type(tg_type):
    if tg_type == "left_tg":
        start_id = 256
    elif tg_type == "right_tg":
        start_id = 0
    else:
        raise AssertionError(f"Wrong traffic generator type was provided - {tg_type} is invalid traffic generator")

    return start_id


def get_jump(packets_num):
    if packets_num == 64:
        jump = 4
    elif packets_num == 128:
        jump = 2
    else:
        return AssertionError(f"Ports number should be 64 or 128, but got {packets_num}")
    return jump


def main():
    parser = argparse.ArgumentParser(description='Packet generator script')
    parser.add_argument('-s', '--size', type=int, help='Packet size', required=True)
    parser.add_argument('-n', '--packets_num', type=int, help='Number of Packets', required=True)
    parser.add_argument('-m', '--destination_mac', type=str, help='Destination MAC address', required=True)
    parser.add_argument('-g', '--traffic_generator_type', type=str, help='IP of the route on DUT', required=True)
    parser.add_argument('-p', '--ports_num', type=int, help='Number of ports on the traffic generator',
                        required=True)
    args = parser.parse_args()
    PACKET_SIZE = args.size
    PACKETS_PER_PORT = args.packets_num
    TG_TYPE = args.traffic_generator_type
    PORTS_NUM = args.ports_num
    ipSrc = scapy.RandIP("1.1.1.1/24")
    ethDstMac = args.destination_mac
    ethSrcMac = "94:6d:ae:ab:00:a2"
    ipTOS = 24 * 4
    ipTTL = 10
    roce_payload = "b8cef6b6184d1c34da16f5000800450e043c82cb40003d116b650202f74b02025023daaf12b7042800000a40ffff000001ad40d8c5dc00007f0f670f3400001be1e5000004004c5ae6db190a85c463b2105a80d69e161b5496cc24b1a14f91bf53580aea7a574461325d6bb821ce6a3128eb07c601221b97ee3f488f8fd94fe23259ccacb0100de36d789b8e4605c06ef0c735f1ea5088d88fd0681eaab701dc10cd88c1de96a44b0e3fda55449ac33561f8264b48af24d87f8cf62943f70553c58e14a324b8ee32f7c8873c624b71c443970f8c463364c6bf5aef0252f55617836abaa723a8d91a716156d3acc797ef5fa77ba5dadf6b9a3a5b9c8c50f2a3d35d5d7a8005539a76b4f14a60b8e1501788cbbd63ab28fde5839971d38c14a6e9712069767403ed28f43789ad18d9c4a1a481044faa01342d9aa50126b9a70f2ac878a13c7c8e6470c5ed1dddc6e27e6b6382ba0d83ef3b1e943c444ee35478abcc19e748a74cb96c39d64a00b8c86b1c4b2529ce1464eca9a031f784856f2f5189179a3063539d9c29e79ce2af07fefa2d27c9418cb5ea2ce6e1b06b51e0bddaf7570a5aaaa7f6d38e93b53e9ab338c7db010967b7f3939dd544092624c6001b1d0a75c7b26b9a40fe507e9903b760deb869456f5dd90d321d165841dc585cf962d1c0143c5a553baad3d4ae8a348c439ed2b2fbabbf2dc8d58509b1dd65aa3f366a5472c5a9ad6f7c811d07b6aa4a547cfc4f27bc7cef9101f843de5ded1d935871051d1ab38c9734aa9eea54e83ed0e48df7a009e6320ade75e83b6206ceba77d3d792866429bb0ec7a562afe432937129347b0f6685eddb6e283d74f6f8ebc9cf7d5033a60b416db0a31c94d5b006fee4810d4a06fa25742262e8185ad4e22a51325df83d9f65ed42828218328816160924600f1e858441e76c5942403b6c926dc98aaa68ef98ab711ac3a3a2d9b9abfd19ba1c9e3e5d86abb6c8ebf2347d5ffd070a66f7a21168bcd40c5eadc509abdfc3c77d022403addacb98ccff162cfd1d366314d8747d944889f2f54efba02dbe67abc08bae6d667a0632791c5e763994d94e6c4dcb009554f28ba2ed2bd0ac937b6c1e29da84a3e0b71dfc159335aa6d8316ba4e1750a209db45f70615a399900fb8b9e93c5dc9f37ac5090dfbb37a7ec935cde0856fea60b4e166c984005993b8137df47046e8ea0cf1f707a472856da7524e2cc2388c7619f2409df29930aaacad9f1cf487060078fe071c708c8917dfd743a10fcf1728c157c5b4f1f65e9da3fdba9784c097fcbe9e182e2ba2450a7988ab8957c2b1191a77cd0b6d2ba8102962a8ad233faae1dec21009645513dedebe673580184e9a8f1ba5fc474e0d70b0b51dd3f4c7b5d28ac5dbee1aeeccf8ac332e2d4c7cc7db986dd8dfbbe54f6b9a6c3f8e34f461beb93cacd32b79ccd7acfa04f876ccd40e39acedf4913c5f2ba99eb9dd921a9b4b57471f82c0eb596de55e655b2a396a63e557577694b6a13d555b1ae775b533ccfc524ebd3da82a22068f7d30aad5168e"
    p = Ether(bytearray.fromhex(roce_payload))
    p[Ether].src = ethSrcMac
    p[Ether].dst = ethDstMac
    p[IP].src = ipSrc
    p[IP].tos = ipTOS
    p = SetPacketSize(p, PACKET_SIZE)

    route_ip = get_route_from_tg_type(TG_TYPE)
    start_id = get_ids_from_tg_type(TG_TYPE)
    i = start_id
    jump = get_jump(PORTS_NUM)
    end_id = i + PORTS_NUM * jump - 1
    while i <= end_id:
        ipDst = scapy.RandIP(route_ip)
        p[IP].dst = ipDst
        interface = 'Ethernet{}'.format(i)
        del p[IP].chksum
        del p[UDP].chksum
        sendp(p, iface=interface, verbose=False, count=PACKETS_PER_PORT)
        i += jump


if __name__ == '__main__':
    main()

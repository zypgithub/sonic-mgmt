#!/usr/bin/env python3

import json
from typing import List


class PacketGenerator:
    """
    A generic packet generator for creating packets with customizable headers and payloads.
    This class allows for the configuration of common network headers (IP, VLAN, TCP, UDP)
    and a RAW payload. The payload can be automatically adjusted to fit the specified
    packet size. The packet data can then be exported to a JSON file for further processing.
    Attributes:
        ports: List of integers specifying the ports involved in the packet.
        packet_size: Integer representing the total size of the packet.
        headers: Dictionary containing the packet headers and their respective configurations.
    """

    def __init__(self, ports: List[int], packet_size: int, num_packets: int):
        """
        Initializes a PacketGenerator instance with specified ports and packet size.
        Args:
            ports: A list of integers representing the network ports.
            packet_size: An integer specifying the desired total packet size.
            num_packets: Num of packets to send from each port
        """
        self.ports = ports
        self.packet_size = packet_size
        self.headers = {}
        self.num_packets = num_packets

    def get_json(self) -> dict:
        """
        returns the packet data JSON obj.
        """
        packet_data = {
            "ports": self.ports,
            "num_packets": self.num_packets,
            "packet_size": self.packet_size,
            "headers": self.headers,
        }
        return packet_data

    def add_ip_header(self, src: str, dst: str, ttl: int = 64, tos: int = 96) -> None:
        """
        Adds an IP header to the packet configuration.
        Args:
            src: The source IP address as a string.
            dst: The destination IP address as a string.
            ttl: The time-to-live value for the IP packet. Defaults to 64.
            tos: Type of service, defaults to 96 for default ROCE Lossless Traffic.
        """
        self.headers["IP"] = {"src": src, "dst": dst, "ttl": ttl, "tos": tos}

    def add_ipv6_header(self, src: str, dst: str, hlim: int = 64) -> None:
        """
        Adds an IPv6 header to the packet configuration.
        Args:
            src: The source IP address as a string.
            dst: The destination IP address as a string.
            hlim: The hop limit value for the IPv6 packet. Defaults to 64.
        """
        self.headers["IPv6"] = {"src": src, "dst": dst, "hlim": hlim}

    def add_ether_header(self, src: str, dst: str) -> None:
        """
        Adds an Ether header to the packet configuration.
        Args:
            src: The source IP address as a string.
            dst: The destination IP address as a string.
        """
        self.headers["Ether"] = {"src": src, "dst": dst}

    def add_vlan_header(self, vlan_id: int, priority: int = 0) -> None:
        """
        Adds a VLAN header to the packet configuration.
        Args:
            vlan_id: An integer representing the VLAN ID.
            priority: An integer specifying the VLAN priority. Defaults to 0.
        """
        self.headers["VLAN"] = {"id": vlan_id, "priority": priority}

    def add_tcp_header(self, source_port: int, dest_port: int, seq: int = 0, ack: int = 0) -> None:
        """
        Adds a TCP header to the packet configuration.
        Args:
            source_port: The source port as an integer.
            dest_port: The destination port as an integer.
            seq: The sequence number for the TCP packet. Defaults to 0.
            ack: The acknowledgment number for the TCP packet. Defaults to 0.
        """
        self.headers["TCP"] = {"source_port": source_port, "dest_port": dest_port, "seq": seq, "ack": ack}

    def add_udp_header(self, source_port: int, dest_port: int) -> None:
        """
        Adds a UDP header to the packet configuration.
        Args:
            source_port: The source port as an integer.
            dest_port: The destination port as an integer.
        """
        self.headers["UDP"] = {"sport": source_port, "dport": dest_port}

    def add_bth_header(self, opcode: int = 0, solicited_event: int = 0, mig_reg: int = 0,
                       pad_count: int = 0, header_version: int = 0, partition_key: int = 0xffff,
                       F_div_R: int = 0, B_div_R: int = 0, reserved: int = 0, dest_qp: int = 0,
                       ack_request: int = 0, ar: int = 0, reserved_2: int = 0,
                       packet_sequence_number: int = 0, padding: int = 0, i_crc: int = 0) -> None:
        """
        Adds a BTH (Base Transport Header) to the packet configuration with specified bit fields.
        Args:
            opcode: Integer indicating the IBA packet type.
            solicited_event: Integer flag for generating a responder event.
            mig_reg: Integer flag for migration state.
            pad_count: Integer indicating payload padding.
            header_version: Integer specifying the transport header version.
            partition_key: Integer partition key for logical partitions.
            F_div_R: Integer indicating congestion status.
            B_div_R: Integer indicating forward congestion.
            reserved: Integer reserved field, should be zero.
            dest_qp: Integer indicating the destination queue pair.
            ack_request: Integer flag for acknowledgment request.
            ar: Integer acknowledgment request.
            reserved_2: Integer reserved field for invariant CRC.
            packet_sequence_number: Integer for packet sequencing.
            padding: Integer padding, should be zero.
            i_crc: Integer for invariant CRC checksum.
        """
        self.headers["BTH"] = {
            "opcode": opcode,
            "solicited_event": solicited_event,
            "mig_reg": mig_reg,
            "pad_count": pad_count,
            "header_version": header_version,
            "partition_key": partition_key,
            "F_div_R": F_div_R,
            "B_div_R": B_div_R,
            "reserved": reserved,
            "dest_qp": dest_qp,
            "ack_request": ack_request,
            "ar": ar,
            "reserved_2": reserved_2,
            "packet_sequence_number": packet_sequence_number,
            "padding": padding,
            "i_crc": i_crc
        }

    def add_payload_header(self, data: str) -> None:
        """
        Adds a RAW payload to the packet, ensuring that the entire packet matches the specified packet size.
        This method should be called after all other headers have been added, as it calculates
        the remaining space and adjusts the payload to fit exactly.
        Args:
            data: A string representing the payload data.
        Raises:
            ValueError: If the specified packet size is too small to fit the headers and payload.
        """
        header_size = len(json.dumps(self.headers))
        available_payload_size = self.packet_size - header_size
        if available_payload_size <= 0:
            raise ValueError("Packet size is too small to fit headers and payload.")
        if len(data) > available_payload_size:
            self.headers["Raw"] = {"load": data[:available_payload_size]}
        else:
            repeated_payload = (data * (available_payload_size // len(data))) + data[:available_payload_size % len(data)]
            self.headers["Raw"] = {"load": repeated_payload}

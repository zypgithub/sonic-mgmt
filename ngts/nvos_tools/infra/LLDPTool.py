import time
import re

from retry import retry
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.connection_tools.pexpect_serial_engine import PexpectSerialEngine
from ngts.nvos_constants.constants_nvos import TcpDumpConsts
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure


class LLDPTool:
    file_path = "/tmp/lldp_packets.txt"
    lldp_proto = '0x88cc'

    lldp_output_pattern = {
        TcpDumpConsts.LLDP_CHASIS_ID: re.compile(
            r"Chassis ID TLV \(1\), length \d+\s+Subtype MAC address \(\d+\): ([\w:]+)"),
        TcpDumpConsts.LLDP_PORT_ID: re.compile(r"Port ID TLV \(2\), length \d+\s+Subtype Local \(\d+\): (\w+)"),
        TcpDumpConsts.LLDP_TIME_TO_LIVE: re.compile(r"Time to Live TLV \(3\), length \d+: TTL (\d+)s"),
        TcpDumpConsts.LLDP_SYSTEM_NAME: re.compile(r"System Name TLV \(5\), length \d+: ([\w-]+)"),
        TcpDumpConsts.LLDP_SYSTEM_DESCRIPTION: re.compile(r"System Description TLV \(6\), length \d+\s+([\w\s\-\.:]+)"),
        TcpDumpConsts.LLDP_SYSTEM_CAPABILITIES: re.compile(
            r"System Capabilities TLV \(7\), length \d+\s+System\s+Capabilities \[([\w\s,]+)\]"),
        TcpDumpConsts.LLDP_ENABLED_CAPABILITIES: re.compile(r"Enabled Capabilities \[([\w\s,]+)\]"),
        TcpDumpConsts.LLDP_IPV4: re.compile(
            r"Management Address TLV \(8\), length \d+\s+Management Address length \d+, AFI IPv4 \(\d+\): ([\d\.]+)"),
        TcpDumpConsts.LLDP_IPV6: re.compile(
            r"Management Address TLV \(8\), length \d+\s+Management Address length \d+, AFI IPv6 \(\d+\): ([\w:]+)"),
        TcpDumpConsts.LLDP_PORT_DESCRIPTION: re.compile(r"Port Description TLV \(4\), length \d+: (\w+)")
    }

    @staticmethod
    def start_dump_lldp_packets(engine: LinuxSshEngine, interface="eth0"):
        with allure.step(f"Dump lldp {interface} packets into {LLDPTool.file_path}"):
            engine.run_cmd(f"sudo rm -rf {LLDPTool.file_path}")
            engine.run_cmd(
                f'sudo tcpdump -Q out -lne -i {interface} -vv ether proto {LLDPTool.lldp_proto} > {LLDPTool.file_path} &')

    @staticmethod
    @retry(AssertionError, 10, 5)
    def verify_mgmt_ports_are_up(engine: PexpectSerialEngine):
        with allure.step("verify mgmt ports are up using ifconfig via serial engine"):
            for mgmt_port in ['eth0', 'eth1']:
                ifconfig_output = engine.run_cmd_and_get_output(f"sudo ifconfig {mgmt_port}")
                ValidationTool.verify_expected_output(ifconfig_output, 'UP').verify_result()

    @staticmethod
    def finish_dump_lldp_packets(engine: LinuxSshEngine):
        with allure.step(f"Kill tcpdump instances"):
            engine.run_cmd("sudo killall tcpdump")

    @staticmethod
    def get_lldp_frames(engine: LinuxSshEngine, interface="eth0", interval=30):
        LLDPTool.start_dump_lldp_packets(engine, interface)
        time.sleep(interval + 1)
        LLDPTool.finish_dump_lldp_packets(engine)
        with allure.step("Get lldp frames output"):
            output = str(engine.run_cmd(f'cat {LLDPTool.file_path}'))
            return output

    @staticmethod
    def parse_lldp_dump(lldp_dump):
        res = dict()
        for key, pattern in LLDPTool.lldp_output_pattern.items():
            match = pattern.search(lldp_dump)
            if match:
                res[key] = match.group(1)
        return res

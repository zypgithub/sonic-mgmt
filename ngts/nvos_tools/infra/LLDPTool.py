import logging
import re
import time

from retry import retry
from devts.infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from devts.infra.tools.connection_tools.pexpect_serial_engine import PexpectSerialEngine
from ngts.nvos_constants.constants_nvos import TcpDumpConsts
from ngts.nvos_tools.infra.EngineAdapterTool import EngineAdapterTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port

# Sudo prints one of these strings to stderr/stdout when `-n` is used and a
# password would be required. We detect them to fall back to `sudo -S` with the
# engine's password instead of silently failing the test.
_SUDO_NEEDS_PASSWORD_MARKERS = (
    "a password is required",
    "sudo: a terminal is required",
    "sudo: no tty present",
)


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
    def _sudo_run(engine, cmd):
        """
        Run `sudo -n <cmd>` and return its output. If sudo refuses non-interactively
        because a password is required, fall back to `echo '<pw>' | sudo -S <cmd>`
        using the engine's password attribute (set on both LinuxSshEngine and
        PexpectSerialEngine).

        This is needed for serial-console paths where the default user does not
        have NOPASSWD in sudoers; without the fallback `sudo -n` immediately fails
        and the caller observes an empty/error output unrelated to the actual
        command result.
        """
        non_interactive = f"sudo -n {cmd}"
        output = engine.run_cmd_and_get_output(non_interactive) \
            if hasattr(engine, "run_cmd_and_get_output") else engine.run_cmd(non_interactive)
        output_str = output if isinstance(output, str) else str(output)
        if not any(marker in output_str for marker in _SUDO_NEEDS_PASSWORD_MARKERS):
            return output_str
        password = getattr(engine, "password", None)
        if not password:
            raise AssertionError(
                f"`sudo -n {cmd}` failed because sudo requires a password and no "
                f"password is available on the engine. Configure NOPASSWD for this "
                f"command in /etc/sudoers or use an engine that exposes `password`. "
                f"Output was: {output_str}"
            )
        interactive = f"echo '{password}' | sudo -S {cmd}"
        output = engine.run_cmd_and_get_output(interactive) \
            if hasattr(engine, "run_cmd_and_get_output") else engine.run_cmd(interactive)
        return output if isinstance(output, str) else str(output)

    @staticmethod
    def start_dump_lldp_packets(engine: LinuxSshEngine, interface="eth0"):
        with allure.step(f"Dump lldp {interface} packets into {LLDPTool.file_path}"):
            engine.run_cmd(f"sudo -n rm -rf {LLDPTool.file_path}")
            engine.run_cmd(
                f'sudo -n tcpdump -Q out -lne -i {interface} -vv ether proto {LLDPTool.lldp_proto} > {LLDPTool.file_path} &')

    @staticmethod
    @retry(AssertionError, 10, 5)
    def verify_mgmt_ports_are_up(engine: PexpectSerialEngine, device):
        """Verify all mgmt ports reported by the device are up (ifconfig UP) via serial engine."""
        with allure.step("verify mgmt ports are up using ifconfig via serial engine"):
            mgmt_ports = device.get_mgmt_ports()
            if not mgmt_ports:
                raise ValueError("Device has no mgmt ports")
            for mgmt_port in mgmt_ports:
                ifconfig_output = LLDPTool._sudo_run(engine, f"ifconfig {mgmt_port}")
                ValidationTool.verify_expected_output(ifconfig_output, 'UP').verify_result()

    @staticmethod
    def finish_dump_lldp_packets(engine: LinuxSshEngine):
        with allure.step("Kill tcpdump instances"):
            # `|| true` so a "no process found" exit from killall does not propagate
            # as a command failure on engines that validate exit codes.
            engine.run_cmd("sudo -n killall tcpdump || true")

    # Matches bash job-control notifications like:
    #   "[1]+  Done                    sudo tcpdump ..."
    #   "[1]+  Terminated  sudo tcpdump ..."
    # These leak into the cat output because tcpdump is backgrounded and bash flushes
    # the notification into the SSH stream around the time of the next command.
    _bash_job_notification_re = re.compile(r'^\s*\[\d+\][+-]?\s+(Done|Terminated|Exit\s+\d+|Killed)\b.*$')

    @staticmethod
    def get_lldp_frames(engine: LinuxSshEngine, interface="eth0", interval=30):
        LLDPTool.start_dump_lldp_packets(engine, interface)
        wait_sec = interval + 1
        logging.info("Waiting %s seconds to capture LLDP frames on %s", wait_sec, interface)
        time.sleep(wait_sec)
        LLDPTool.finish_dump_lldp_packets(engine)
        with allure.step("Get lldp frames output"):
            # Use EngineAdapterTool so serial-engine outputs (tuple returns,
            # echoed command, shell prompt lines, embedded \r) are normalized
            # before regex-based LLDP parsing. Without this, parse_lldp_dump
            # can miss TLVs on the serial path.
            output = EngineAdapterTool.run_cmd(engine, f'cat {LLDPTool.file_path}')
            filtered = "\n".join(
                line for line in output.splitlines()
                if not LLDPTool._bash_job_notification_re.match(line)
            )
            return filtered.strip()

    @staticmethod
    def parse_lldp_dump(lldp_dump):
        res = dict()
        for key, pattern in LLDPTool.lldp_output_pattern.items():
            match = pattern.search(lldp_dump)
            if match:
                res[key] = match.group(1)
        return res

    @staticmethod
    @retry(AssertionError, 10, 5)
    def verify_ip_address_is_set(engine: PexpectSerialEngine, mgmt_interface: Port, ip_address: str, is_ipv6: bool = False):
        """
        Verify IP address is set on the interface.

        :param engine: Serial engine to use for verification
        :param mgmt_interface: Management interface Port object
        :param ip_address: IP address to verify (with or without prefix)
        :param is_ipv6: If True, verify IPv6 address; if False, verify IPv4 address
        """
        with allure.step(f"Verify {'IPv6' if is_ipv6 else 'IPv4'} address {ip_address} is set"):
            if is_ipv6:
                ip_address_output = mgmt_interface.interface.ipv6.address.show(dut_engine=engine)
            else:
                ip_address_output = mgmt_interface.interface.ipv4.address.show(dut_engine=engine)
            ValidationTool.verify_expected_output(ip_address_output, ip_address).verify_result()

"""
IPoIB feature coverage beyond the basic ping-and-check flow in
test_basic_traffic.py::test_basic_ipoib_traffic.

Tests in this module configure the IPoIB IPs once on both hosts (avoiding
the per-direction ifconfig cycling that triggers spurious multicast-relay
counter increments), wait for the SM multicast tree to stabilize, then
clear counters BEFORE running the assertions. The final
verify_no_link_errors call therefore reflects only data-plane behavior.

Tests:
  - test_basic_ipoib_mtu_handling           : MTU boundary + IP fragmentation
  - test_basic_ipoib_arp_resolution         : 20-byte IB neighbor lladdr
  - test_basic_ipoib_concurrent_bidirectional : both directions in parallel
"""
import logging
import re
import threading
import time
import pytest
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.Tools import Tools

logger = logging.getLogger()


# Shared IPoIB test configuration
HA_IP = '192.192.192.2'
HB_IP = '192.192.192.1'
NETMASK = '255.255.255.0'
SETTLE_SECONDS = 5  # Time for SM to push updated MFTs after multicast joins


def _setup_ipoib(ha_engine, hb_engine, ha_iface, hb_iface):
    """Configure IPoIB IPs once on both hosts and let the fabric settle."""
    ha_engine.run_cmd(f'ifconfig {ha_iface} {HA_IP} netmask {NETMASK}')
    hb_engine.run_cmd(f'ifconfig {hb_iface} {HB_IP} netmask {NETMASK}')
    time.sleep(SETTLE_SECONDS)


def _cleanup_ipoib(ha_engine, hb_engine, ha_iface, hb_iface):
    """Best-effort: unset IPs on both hosts. Logs but does not raise on failure."""
    for engine, iface in ((ha_engine, ha_iface), (hb_engine, hb_iface)):
        try:
            engine.run_cmd(f'ifconfig {iface} 0.0.0.0 up')
        except Exception as ex:
            logger.warning(f'Cleanup of {iface} failed: {ex}')


@pytest.mark.general
@pytest.mark.skynet
def test_basic_ipoib_mtu_handling(engines, devices, players, interfaces, start_sm):
    """
    Verify IPoIB MTU enforcement and IP fragmentation behavior.

    The standard test_basic_ipoib_traffic only sends default-size pings
    (~64 byte payload). This test exercises packet sizes around the MTU
    boundary to validate fragmentation/reassembly and DF (Don't Fragment)
    enforcement over IPoIB:

      A. payload == MTU - headers, default frag       -> success
      B. payload == MTU - headers + 1, default frag   -> success (fragments)
      C. payload ~= 2 * MTU, default frag             -> success (multi-fragment)
      D. payload >  MTU, DF set (-M do)               -> local error
                                                         "message too long, mtu=<MTU>"
      E. payload == MTU - headers, DF set             -> success (no frag needed)

    Reads the host MTU from /sys/class/net/<iface>/mtu so the test is
    platform-agnostic (datagram MTU 2044, jumbo, or connected-mode).
    """
    PING_COUNT = 5
    PING_INTERVAL = 0.2
    PING_TIMEOUT = 2
    IP_HDR_BYTES = 20
    ICMP_HDR_BYTES = 8

    ha_engine = players['ha']['engine']
    hb_engine = players['hb']['engine']
    ha_iface = interfaces.ha_dut_1
    hb_iface = interfaces.hb_dut_1

    def ping_cmd(payload_size, df=False):
        df_flag = '-M do ' if df else ''
        return (f'ping -c {PING_COUNT} -i {PING_INTERVAL} -W {PING_TIMEOUT} '
                f'-s {payload_size} {df_flag}-I {ha_iface} {HB_IP}')

    try:
        with allure.step(f'Configure IPs once: {ha_iface}={HA_IP}, {hb_iface}={HB_IP}'):
            _setup_ipoib(ha_engine, hb_engine, ha_iface, hb_iface)

        with allure.step('Read host IPoIB MTU and derive boundary payloads'):
            ha_mtu = int(ha_engine.run_cmd(f'cat /sys/class/net/{ha_iface}/mtu').strip())
            hb_mtu = int(hb_engine.run_cmd(f'cat /sys/class/net/{hb_iface}/mtu').strip())
            assert ha_mtu == hb_mtu, f'Symmetric MTU required: ha={ha_mtu}, hb={hb_mtu}'
            mtu = ha_mtu
            payload_at_mtu = mtu - IP_HDR_BYTES - ICMP_HDR_BYTES
            payload_above_mtu = payload_at_mtu + 1
            payload_well_above_mtu = mtu * 2
            logger.info(f'IPoIB MTU={mtu}; ICMP payloads: at_mtu={payload_at_mtu}, '
                        f'above_mtu={payload_above_mtu}, well_above_mtu={payload_well_above_mtu}')

        with allure.step('Clear counters AFTER setup churn (final assertion reflects data plane only)'):
            Tools.TrafficValidatorTool.clear_traffic_port_counters(engines.dut).verify_result()

        with allure.step(f'Case A: payload={payload_at_mtu} (at MTU), default frag - expect success'):
            output = ha_engine.run_cmd(ping_cmd(payload_at_mtu))
            assert '0% packet loss' in output, f'Case A failed: {output}'

        with allure.step(f'Case B: payload={payload_above_mtu} (1 byte over MTU), default frag - expect success (fragments)'):
            output = ha_engine.run_cmd(ping_cmd(payload_above_mtu))
            assert '0% packet loss' in output, f'Case B failed: {output}'

        with allure.step(f'Case C: payload={payload_well_above_mtu} (~2*MTU), default frag - expect success (multi-fragment)'):
            output = ha_engine.run_cmd(ping_cmd(payload_well_above_mtu))
            assert '0% packet loss' in output, f'Case C failed: {output}'

        with allure.step(f'Case D: payload={payload_above_mtu} with DF (-M do) - expect "message too long, mtu={mtu}"'):
            output = ha_engine.run_cmd(ping_cmd(payload_above_mtu, df=True))
            assert 'message too long' in output, (
                f'Case D: expected "message too long" with DF set, got: {output}'
            )
            assert f'mtu={mtu}' in output, (
                f'Case D: expected reported mtu={mtu} in error, got: {output}'
            )
            assert '100% packet loss' in output, (
                f'Case D: expected 100% loss when DF set on oversize packet, got: {output}'
            )

        with allure.step(f'Case E: payload={payload_at_mtu} with DF (-M do) - expect success (no frag needed)'):
            output = ha_engine.run_cmd(ping_cmd(payload_at_mtu, df=True))
            assert '0% packet loss' in output, f'Case E failed: {output}'

        with allure.step('Verify zero link errors across all MTU/fragmentation cases'):
            Tools.TrafficValidatorTool.verify_no_link_errors(engines.dut, devices.dut).verify_result()

    finally:
        with allure.step('Cleanup: unset IPs on both hosts'):
            _cleanup_ipoib(ha_engine, hb_engine, ha_iface, hb_iface)


@pytest.mark.general
@pytest.mark.skynet
def test_basic_ipoib_arp_resolution(engines, devices, players, interfaces, start_sm):
    """
    Verify IPoIB neighbor (ARP) resolution.

    Unlike Ethernet (6-byte MAC), IPoIB uses 20-byte hardware addresses
    that include the QPN and full GID. This test:
      1. Flushes the neighbor cache to force fresh resolution.
      2. Triggers resolution via a single ping.
      3. Reads the neighbor table and verifies:
         - Peer IP is present.
         - lladdr is a 20-octet IB hardware address (not the 6-byte Ethernet form).
         - lladdr is non-zero.
         - State is REACHABLE / STALE / DELAY (i.e. resolution succeeded).
    """
    IB_LLADDR_REGEX = re.compile(r'lladdr ((?:[0-9a-f]{2}:){19}[0-9a-f]{2})')
    VALID_NEIGH_STATES = ('REACHABLE', 'STALE', 'DELAY', 'PROBE')

    ha_engine = players['ha']['engine']
    hb_engine = players['hb']['engine']
    ha_iface = interfaces.ha_dut_1
    hb_iface = interfaces.hb_dut_1

    try:
        with allure.step(f'Configure IPs once: {ha_iface}={HA_IP}, {hb_iface}={HB_IP}'):
            _setup_ipoib(ha_engine, hb_engine, ha_iface, hb_iface)

        with allure.step('Clear counters AFTER setup churn'):
            Tools.TrafficValidatorTool.clear_traffic_port_counters(engines.dut).verify_result()

        with allure.step(f'Flush neighbor cache on HA for {ha_iface}'):
            ha_engine.run_cmd(f'ip neigh flush dev {ha_iface}')

        with allure.step(f'Trigger neighbor resolution via single ping HA -> {HB_IP}'):
            output = ha_engine.run_cmd(f'ping -c1 -W2 -I {ha_iface} {HB_IP}')
            assert '0% packet loss' in output, f'Resolution-trigger ping failed: {output}'

        with allure.step(f'Verify {HB_IP} present in neighbor table on HA with 20-byte IB lladdr'):
            neigh = ha_engine.run_cmd(f'ip neigh show {HB_IP} dev {ha_iface}').strip()
            logger.info(f'Neighbor entry: {neigh!r}')
            assert HB_IP in neigh, f'Peer {HB_IP} not in neighbor table: {neigh!r}'

            match = IB_LLADDR_REGEX.search(neigh)
            assert match, f'No 20-octet IB lladdr in neighbor entry: {neigh!r}'
            lladdr = match.group(1)
            assert lladdr != ':'.join(['00'] * 20), f'lladdr is all zeros: {lladdr}'

            assert any(state in neigh for state in VALID_NEIGH_STATES), (
                f'Expected neighbor state in {VALID_NEIGH_STATES}, got: {neigh!r}'
            )
            logger.info(f'Verified IPoIB neighbor on HA: {HB_IP} -> {lladdr}')

        with allure.step(f'Verify reverse direction: HA appears in HB neighbor table'):
            hb_engine.run_cmd(f'ip neigh flush dev {hb_iface}')
            output = hb_engine.run_cmd(f'ping -c1 -W2 -I {hb_iface} {HA_IP}')
            assert '0% packet loss' in output, f'Reverse-direction ping failed: {output}'
            neigh = hb_engine.run_cmd(f'ip neigh show {HA_IP} dev {hb_iface}').strip()
            logger.info(f'Reverse neighbor entry: {neigh!r}')
            assert HA_IP in neigh, f'Peer {HA_IP} not in reverse neighbor table: {neigh!r}'
            assert IB_LLADDR_REGEX.search(neigh), (
                f'No 20-octet IB lladdr in reverse neighbor entry: {neigh!r}'
            )

        with allure.step('Verify zero link errors after ARP resolution traffic'):
            Tools.TrafficValidatorTool.verify_no_link_errors(engines.dut, devices.dut).verify_result()

    finally:
        with allure.step('Cleanup: unset IPs on both hosts'):
            _cleanup_ipoib(ha_engine, hb_engine, ha_iface, hb_iface)


@pytest.mark.general
@pytest.mark.skynet
def test_basic_ipoib_concurrent_bidirectional(engines, devices, players, interfaces, start_sm):
    """
    Verify concurrent bidirectional IPoIB traffic.

    The standard test_basic_ipoib_traffic sends traffic in two sequential
    directions. This test launches both directions in parallel via threads
    and verifies:
      - Both pings achieve 0% loss (no duplex / queue / scheduling issues).
      - No link errors on the switch during concurrent traffic.

    Catches regressions where forwarding becomes serialized or one direction
    starves the other.
    """
    PING_COUNT = 30
    PING_INTERVAL = 0.1
    PING_TIMEOUT = 2

    ha_engine = players['ha']['engine']
    hb_engine = players['hb']['engine']
    ha_iface = interfaces.ha_dut_1
    hb_iface = interfaces.hb_dut_1

    results = {}
    errors = {}

    def run_ping(label, engine, iface, target):
        try:
            results[label] = engine.run_cmd(
                f'ping -c {PING_COUNT} -i {PING_INTERVAL} -W {PING_TIMEOUT} -I {iface} {target}'
            )
        except Exception as ex:
            errors[label] = ex

    try:
        with allure.step(f'Configure IPs once: {ha_iface}={HA_IP}, {hb_iface}={HB_IP}'):
            _setup_ipoib(ha_engine, hb_engine, ha_iface, hb_iface)

        with allure.step('Clear counters AFTER setup churn'):
            Tools.TrafficValidatorTool.clear_traffic_port_counters(engines.dut).verify_result()

        with allure.step(f'Launch concurrent ping HA->HB and HB->HA ({PING_COUNT} pkts each)'):
            t_ha = threading.Thread(
                target=run_ping, args=('ha->hb', ha_engine, ha_iface, HB_IP), daemon=True,
            )
            t_hb = threading.Thread(
                target=run_ping, args=('hb->ha', hb_engine, hb_iface, HA_IP), daemon=True,
            )
            t_ha.start()
            t_hb.start()
            t_ha.join(timeout=60)
            t_hb.join(timeout=60)
            assert not t_ha.is_alive(), 'HA->HB ping thread did not complete in 60s'
            assert not t_hb.is_alive(), 'HB->HA ping thread did not complete in 60s'

        with allure.step('Verify both directions completed without thread errors'):
            assert not errors, f'Ping threads raised exceptions: {errors}'
            assert 'ha->hb' in results and 'hb->ha' in results, (
                f'Missing thread results: {list(results.keys())}'
            )

        with allure.step('Verify HA->HB had 0% packet loss'):
            assert '0% packet loss' in results['ha->hb'], (
                f'HA->HB had loss during concurrent traffic: {results["ha->hb"]}'
            )

        with allure.step('Verify HB->HA had 0% packet loss'):
            assert '0% packet loss' in results['hb->ha'], (
                f'HB->HA had loss during concurrent traffic: {results["hb->ha"]}'
            )

        with allure.step('Verify zero link errors after concurrent bidirectional traffic'):
            Tools.TrafficValidatorTool.verify_no_link_errors(engines.dut, devices.dut).verify_result()

    finally:
        with allure.step('Cleanup: unset IPs on both hosts'):
            _cleanup_ipoib(ha_engine, hb_engine, ha_iface, hb_iface)

#!/bin/bash
# Workaround for the AST2700 BMC DHCP issue (Redmine #5091238): after a (re)boot
# or power-cycle the ftgmac100 NIC reports "Link is Up" but no DHCP offer ever
# arrives, so eth0 stays without an IPv4 address and the BMC is unreachable over
# the network. Reloading the driver and re-running dhclient restores it.
#
# Run periodically by bmc-net-recover.timer (a oneshot at boot is not enough: the
# IP can be present briefly at the moment the boot check runs and then drop, and
# the lease can also be lost at runtime). Idempotent: a no-op when eth0 already
# has an IPv4 address. Runs as root via systemd, so no sudo is needed here.

# eth0 already has an IPv4 address -> nothing to do.
if ip -4 addr show eth0 2>/dev/null | grep -q 'inet '; then
    exit 0
fi

logger -t bmc-net-recover "eth0 has no IPv4 address; reloading ftgmac100 and renewing DHCP"

# Stop any running dhclient first so repeated timer runs do not pile up extra
# dhclient processes on eth0.
dhclient -x 2>/dev/null || true

# Reload the NIC driver. Prefer modprobe (resolves the module path
# automatically); fall back to insmod with the running kernel version so a
# kernel upgrade does not break a hard-coded path.
modprobe -r ftgmac100 2>/dev/null || rmmod ftgmac100 2>/dev/null
modprobe ftgmac100 2>/dev/null || \
    insmod "/usr/lib/modules/$(uname -r)/kernel/drivers/net/ethernet/faraday/ftgmac100.ko"

# Re-acquire a lease.
dhclient -v eth0

if ip -4 addr show eth0 2>/dev/null | grep -q 'inet '; then
    logger -t bmc-net-recover "eth0 recovered: $(ip -4 -o addr show eth0 | awk '{print $4}')"
    exit 0
fi
logger -t bmc-net-recover "eth0 still has no IPv4 address after recovery attempt"
exit 1

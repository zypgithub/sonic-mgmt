import ipaddress

from Constants import NogaConstants


def is_ipv6(ip):
    try:
        return isinstance(ipaddress.ip_address(ip), ipaddress.IPv6Address)
    except (ValueError, TypeError):
        return False


def bracket_for_url(ip):
    return f'[{ip}]' if is_ipv6(ip) else ip


def _specific(switch_info):
    return switch_info[NogaConstants.ATTRIBUTES][NogaConstants.SPECIFIC]


def is_ipv6_setup(switch_info):
    try:
        specific = _specific(switch_info)
        return NogaConstants.IPV6_MARKER in specific.get(NogaConstants.HARDWARE_STATE_DETAILS, '')
    except (KeyError, AttributeError):
        return False


def resolve_bmc_ip(switch_info):
    specific = _specific(switch_info)
    if is_ipv6_setup(switch_info):
        bmc_ipv6 = specific.get(NogaConstants.BMC_IPV6)
        mgmt_ipv6 = specific.get(NogaConstants.MGMT_IPV6)
        if not bmc_ipv6 and not mgmt_ipv6:
            raise ValueError(
                f"Setup marked '{NogaConstants.IPV6_MARKER}' in "
                f"{NogaConstants.HARDWARE_STATE_DETAILS} but no IPv6 address populated "
                f"(neither Specific.{NogaConstants.BMC_IPV6} nor Specific.{NogaConstants.MGMT_IPV6})."
            )
        if not bmc_ipv6:
            raise ValueError(
                f"IPv6-only setup missing Specific.{NogaConstants.BMC_IPV6} "
                f"- Redfish target unreachable over IPv4."
            )
        print(f"[ip_resolve] IPv6 setup -> bmc = {bmc_ipv6} (Specific.{NogaConstants.BMC_IPV6})")
        return bmc_ipv6
    bmc_ip = specific.get(NogaConstants.BMC_IP)
    print(f"[ip_resolve] IPv4 setup -> bmc = {bmc_ip} (Specific.{NogaConstants.BMC_IP})")
    return bmc_ip


def resolve_switch_mgmt_ip(switch_info):
    """Return an SSH-reachable switch mgmt target.

    On IPv6 setups, returns Specific.ipv6 (raises if missing) to avoid any DNS
    dependency. On v4 setups, preserves today's behaviour: Common.Name hostname.
    """
    if is_ipv6_setup(switch_info):
        specific = _specific(switch_info)
        mgmt_ipv6 = specific.get(NogaConstants.MGMT_IPV6)
        if not mgmt_ipv6:
            raise ValueError(
                f"IPv6-only setup missing Specific.{NogaConstants.MGMT_IPV6} "
                f"- switch mgmt unreachable over IPv4."
            )
        print(f"[ip_resolve] IPv6 setup -> switch mgmt = {mgmt_ipv6} (Specific.{NogaConstants.MGMT_IPV6})")
        return mgmt_ipv6
    hostname = switch_info[NogaConstants.ATTRIBUTES][NogaConstants.COMMON]['Name'].strip()
    print(f"[ip_resolve] IPv4 setup -> switch mgmt = {hostname} (Common.Name)")
    return hostname

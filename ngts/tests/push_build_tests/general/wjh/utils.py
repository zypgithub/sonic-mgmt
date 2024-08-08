import re

ACL_INGRESS_TABLE_NAME = "DATA_INGRESS_L3TEST"


def parse_ip_address_from_packet(ip_string):
    """
    A function that extracts the actual ip address from the wjh table entry, so the WJH entry validation will be simple.
     Handles both IPv4 and IPv6 addresses.
     Example:
        For IPv4, taking the <ipv4_addr:port> wjh entry and extracts the ipv4_addr.
        For IPv6, take the <[ipv6_addr]:port> and extract the ipv6_addr.
    :param ip_string: The entry from wjh_table containing the ip address and the port
    """
    # Patterns for matching the ip addresses and their ports (optional)
    ipv4_pattern = re.compile(r'(\d+\.\d+\.\d+\.\d+):?(\d+)?')
    ipv6_pattern = re.compile(r'\[?([0-9a-fA-F:]+)\]?:?(\d+)?')

    ipv4_match = ipv4_pattern.match(ip_string)
    if ipv4_match:
        ip = ipv4_match.group(1)
        return ip

    ipv6_match = ipv6_pattern.match(ip_string)
    if ipv6_match:
        ip = ipv6_match.group(1)
        return ip

    # Return N/A if the input doesn't match one of the patterns
    return 'N/A'


def get_drop_src_ip_from_ingress_acl_table(cli_obj):
    """
    Returns an ipv4 src_ip which matches a drop rule from the ACL_INGRESS_TABLE_NAME table
    """
    acl_rules = cli_obj.acl.show_and_parse_acl_rule()[ACL_INGRESS_TABLE_NAME]

    # Filter the table to drop rules only
    drop_rules = [rule for rule in acl_rules if rule['Action'] == 'DROP']

    # Extract a src_ip that matches a drop rule, without the ip mask
    for rule in drop_rules:
        for match in rule['Match']:
            if 'SRC_IP' in match:
                # The match will be of format SRC_IP: IP_ADDR/IP_MASK, so we extract the ip address without mask.
                src_ip = match.split(': ')[1].split('/')[0]
                return src_ip
    # Returns N/A if no src_ip was found in a drop acl rule - shouldn't happen with push-gate acl configuration.
    return 'N/A'

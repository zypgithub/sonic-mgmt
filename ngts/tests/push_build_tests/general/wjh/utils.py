import re
import logging
import pytest
from ngts.cli_util.cli_parsers import generic_sonic_output_parser
from ngts.cli_wrappers.sonic.sonic_wjh_clis import SonicWjhCli
from ngts.cli_wrappers.sonic.sonic_trimming_clis import SonicTrimmingCli
logger = logging.getLogger()
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


def wjh_is_channel_enabled(engines, channel_name):
    engine = engines.dut
    wjh_cli = SonicWjhCli(engine)
    channels_config = wjh_cli.show_wjh_configuration_channels()
    pytest.CHANNEL_CONF = generic_sonic_output_parser(channels_config, output_key="Channel")
    logger.info(f"pytest.CHANNEL_CONF: {pytest.CHANNEL_CONF}")
    if channel_name in pytest.CHANNEL_CONF:
        logger.info(f"Channel '{channel_name}' is enabled")
        return True
    else:
        logger.info(f"Channel '{channel_name}' is disabled")
        return False


def wjh_config_channel_state(engines, channel_name, state):
    logger.info(f"Setting channel '{channel_name}' state to '{state}'")
    engine = engines.dut
    wjh_cli = SonicWjhCli(engine)
    result = wjh_cli.config_wjh_channel_state(channel_name, state)
    logger.info(f"Configuration command return code: {result}")


def get_buffer_profile_trimming_status(duthost, buffer_profile_name):
    logger.info(f"Starting status check for buffer profile: {buffer_profile_name}")
    trimming_cli = SonicTrimmingCli(topology_obj=None, engine=duthost, dut_alias='dut', cli_obj=None)
    if not trimming_cli.check_buffer_profile_exists(buffer_profile_name):
        logger.error(f"Buffer profile {buffer_profile_name} does not exist")
        raise ValueError(f"Buffer profile {buffer_profile_name} does not exist")
    return trimming_cli.get_buffer_profile_packet_discard_action(buffer_profile_name)


def configure_trimming_action(duthost, buffer_profile_name, action):
    logger.info(f"Starting configuration for profile: {buffer_profile_name}, action: {action}")
    if action not in ["on", "off"]:
        raise ValueError(f"Invalid action: {action}. Must be either 'on' or 'off'")

    trimming_cli = SonicTrimmingCli(topology_obj=None, engine=duthost, dut_alias='dut', cli_obj=None)
    trimming_cli.config_mmu_trimming(buffer_profile_name, action)
    trimming_cli.show_mmu()
    logger.info(f"Successfully set packet trimming action to '{action}' for buffer profile {buffer_profile_name}")
    return True


def discover_trimming_enabled_profiles(duthost):
    logger.info("Discovering buffer profiles with trimming enabled")
    trimming_profiles = []
    try:
        trimming_cli = SonicTrimmingCli(topology_obj=None, engine=duthost, dut_alias='dut', cli_obj=None)
        buffer_profile_names = trimming_cli.get_all_buffer_profile_keys()
        logger.info(f"Found {len(buffer_profile_names)} total buffer profiles")

        for buffer_profile_name in buffer_profile_names:
            logger.info(f"Checking profile: {buffer_profile_name}")
            trimming_status = get_buffer_profile_trimming_status(duthost, buffer_profile_name)
            if trimming_status == "trim":
                trimming_profiles.append(buffer_profile_name)
                logger.info(f"Added profile: {buffer_profile_name}")
        logger.info(f"Discovery complete: {len(trimming_profiles)} profiles have trimming enabled")
        return trimming_profiles
    except Exception as e:
        logger.error(f"Exception occurred while discovering trimming profiles: {str(e)}")
        return []

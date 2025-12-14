import re
import logging

logger = logging.getLogger()


def get_internal_ip_for_oob_server(oob_mgmt_server):
    try:
        cmd = 'sudo cat /etc/dhcp/dhcpd.hosts'
        logger.info(f"Getting internal IP for OOB server: {cmd}")
        output = oob_mgmt_server.run_cmd(cmd)

        match = re.search(r'option\s+routers\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', output)
        if match:
            logger.info(f"Internal IP for OOB server: {match.group(1)}")
            return match.group(1)
        else:
            logger.error("Internal IP for OOB server not found")
            return oob_mgmt_server.ip
    except Exception as e:
        logger.error(f"Error getting internal IP for OOB server: {e}")
        return oob_mgmt_server.ip

import logging
import re

from paramiko.ssh_exception import SSHException
from ngts.constants.performance_constants import PerfConsts

logger = logging.getLogger()


def get_sonic_branch(topology, dut_alias='dut'):
    """
    Get the SONiC branch based on release field from /etc/sonic/sonic_version.yml
    :param topology: topology fixture object
    :return: branch name
    :param dut_alias: alias of switch
    """
    try:
        branch = topology.players[dut_alias]['engine'].run_cmd("sonic-cfggen -y /etc/sonic/sonic_version.yml -v release")
    except SSHException as err:
        branch = 'Unknown'
        logger.error(f'Unable to get branch. Assuming that the device is not reachable. Setting the branch as Unknown. '
                     f'Got error: {err}')
    # master branch always has release "none"
    except Exception as nvueerr:
        if topology.players['dut']['attributes'].noga_query_data['attributes']['Topology Conn.']['CLI_TYPE'] \
                in PerfConsts.NON_SONIC_CLI_TYPE:
            branch = "master"
            logger.warning(f'unable to run sonic cmd on dut. Assuming that sonic image is not installed on this device '
                           f'Got error: {nvueerr}')
        else:
            raise nvueerr

    if branch == "none":
        branch = "master"
    return branch.strip()


def update_branch_in_topology(topology, branch=None):
    """
    Method which doing update for SONiC branch in topology object
    :param topology: topology fixture object
    :param branch: SONiC branch, example: "202106"
    """
    if not branch:
        branch = get_sonic_branch(topology)
    topology.players['dut']['branch'] = branch


def update_sanitizer_in_topology(topology, is_sanitizer=None):
    """
    Method which doing update for SONiC branch in topology object
    :param topology: topology fixture object
    :param is_sanitizer: True if sanitizer image, else False
    """
    if is_sanitizer is None:
        is_sanitizer = is_sanitizer_image(topology)
    topology.players['dut']['sanitizer'] = is_sanitizer


def is_sanitizer_image(topology):
    dut_engine = topology.players['dut']['engine']
    is_sanitizer = False
    sanitizer = None
    try:
        sanitizer = dut_engine.run_cmd("sonic-cfggen -y /etc/sonic/sonic_version.yml -v asan")
    except SSHException as err:
        logger.warning(f'Unable to get sanitizer. Assuming that the device is not reachable. '
                       f'Setting the sanitizer as False, '
                       f'Got error: {err}')
    except BaseException as err:
        if topology.players['dut']['attributes'].noga_query_data['attributes']['Topology Conn.']['CLI_TYPE'] \
                in PerfConsts.NON_SONIC_CLI_TYPE:
            logger.info(f"Error ignored ({err}) - this is NVOS setup ")
        else:
            raise err
    if sanitizer == "yes":
        logger.info("The sonic image has sanitizer")
        is_sanitizer = True
    return is_sanitizer


def get_sonic_image(topology):
    """
    The function fetches the SONiC image of the dut
    :param topology: topology fixture object
    :return: branch name
    """
    if topology.players['dut']['attributes'].noga_query_data['attributes']['Topology Conn.']['CLI_TYPE'] \
            in PerfConsts.NON_SONIC_CLI_TYPE:
        return "Unknown"

    try:
        sonic_installer_output = topology.players['dut']['engine'].run_cmd("sudo sonic-installer list")
        image = re.search(r'Current:\s(.*)', sonic_installer_output, re.IGNORECASE).group(1)
    except SSHException as err:
        image = 'Unknown'
        logger.error(f'Unable to get image. Assuming that the device is not reachable. Setting the image as Unknown. '
                     f'Got error: {err}')
    return image

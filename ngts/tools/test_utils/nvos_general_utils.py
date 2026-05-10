import fnmatch
import logging
import os
import re
import time
from contextlib import contextmanager
from typing import Tuple

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from ngts.nvos_constants.constants_nvos import DiskConsts, TopologyConsts, NvosConst
from ngts.nvos_tools.infra.DiskTool import DiskTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.IpTool import IpTool


@contextmanager
def loganalyzer_ignore(cond: bool = True):
    """
    @summary:
        Context manager that wraps code chunks with loganalyzer disabling at the beginning, and enabling in the end
    @param cond: boolean condition; log analyzer will be disabled for the code section only if cond is True (optional)
    """
    # cond = False
    try:
        if cond:
            TestToolkit.start_code_section_loganalyzer_ignore()
        yield
    finally:
        if cond:
            TestToolkit.end_code_section_loganalyzer_ignore()


def check_partitions_capacity(partition_name: str = DiskConsts.DEFAULT_PARTITION_NAME,
                              allowed_limit: int = DiskConsts.PARTITION_CAPACITY_LIMIT,
                              minimum_free_space: float = DiskConsts.MINIMUM_FREE_SPACE):
    """
    Validate there is enough capacity left on disk
    - Create a folder for disk partition to mount
    - Mount new folder to check the remaining space
    - Check if there is enough space
    - Do cleanup, Unmount and remove temp dirs
    """
    switch: ProxySshEngine = TestToolkit.get_engine()

    disk_tool = DiskTool(switch, partition_name)
    partitions = None

    try:
        partitions = disk_tool.get_unmounted_partitions()
        disk_tool.mount_partitions(partitions)

        with allure.step('Check if storage is less than allowed limit'):
            available_partitions_capacity = disk_tool.get_available_partition_capacity()
            for storage in available_partitions_capacity:
                if not storage:
                    continue
                logging.info(f"Disk used space for partition is {storage}")
                # Trim percent symbol from the end, e.g '22%'
                disk_used_space = int(storage.strip()[:-1])
                assert disk_used_space < allowed_limit, f'The disk used space is {disk_used_space}% which is over ' \
                    f'allowed limit of {allowed_limit}%, so image may not fit'
        with allure.step('Check Minimum Free Space'):
            available_disk_free_space = disk_tool.get_free_space()
            # Trim "G" symbol from the end, e.g '6.7G%'
            free = float(available_disk_free_space.strip()[:-1])
            assert free >= minimum_free_space, f'Available free disk space is {available_disk_free_space} which is ' \
                f'below {minimum_free_space}G'

    finally:
        disk_tool.unmount_partitions(partitions)


def wait_for_ldap_nvued_restart_workaround(test_item, engine_to_use=None,
                                           username: str = None, timeout: int = 20,
                                           poll_interval: float = 1.0):
    """
    Wait until a remote-AAA config change is observable on the DUT.

    Historical behavior: a blind ``time.sleep(1)`` used after LDAP
    configuration changes to give nslcd / NVUE time to reload. Kept as
    the fallback when no ``username``/``engine_to_use`` is supplied, so
    existing LDAP call sites are unchanged.

    Readiness-probe behavior: when both ``engine_to_use`` and ``username``
    are supplied, poll ``getent passwd <username>`` on the DUT until the
    user resolves through NSS, or ``timeout`` seconds elapse. Returns as
    soon as the user resolves, which on healthy runs is sub-second.
    On timeout, falls through to the legacy sleep so the caller is never
    worse off than the old behavior.

    Works for LDAP, TACACS+ and RADIUS uniformly: all three route NSS via
    the same ``getent passwd`` lookup on NVOS. The function name is
    kept for backward compatibility with existing LDAP call sites.

    Args:
        test_item: pytest item (kept for signature compatibility).
        engine_to_use: SSH engine to the DUT used for the probe. When
            ``None``, only the legacy sleep is performed.
        username: Username expected to resolve via NSS after the config
            change. When ``None``, only the legacy sleep is performed.
        timeout: Upper bound for the probe, in seconds.
        poll_interval: Seconds between probe iterations.
    """
    workaround_max_time = 1

    if engine_to_use is not None and username:
        with allure.step(
                f'Wait until user "{username}" resolves on DUT '
                f'(timeout={timeout}s) - remote-AAA readiness probe'):
            deadline = time.time() + timeout
            last_output = ''
            while time.time() < deadline:
                last_output = engine_to_use.run_cmd(f'getent passwd {username}') or ''
                if last_output.strip().startswith(f'{username}:'):
                    logging.info(
                        f'User "{username}" resolved on DUT after probe: '
                        f'{last_output.strip()}'
                    )
                    return
                time.sleep(poll_interval)
            logging.warning(
                f'User "{username}" did NOT resolve on DUT within {timeout}s. '
                f'Last getent passwd output: {last_output!r}. '
                f'Falling through to legacy {workaround_max_time}s sleep.'
            )

    with allure.step('After remote-AAA configuration - NVUE restart workaround sleep'):
        with allure.step(f'sleep for {workaround_max_time} seconds'):
            time.sleep(workaround_max_time)


def get_version_info(version: str) -> Tuple[str, str]:
    """
    extract version number and build number from a given image url/path or just a version
    Examples:
        - /a/b/c/d/25.01.3001.bin -> '25.01.3001', ''
        - http://abc.com/a/b/c/25.01.3001-123.bin -> '25.01.3001', '123'
        - 25.01.3001 -> '25.01.3001', ''
    """
    pattern = r'(\d+\.\d+\.\d+)(?:-(\d+))?(?:\.bin)?$'
    match = re.search(pattern, version)
    if match and match.group(0):
        version_num = match.group(1)
        bin_num = match.group(2) if match.group(2) else ''
        return version_num, bin_num
    return '', ''


def generate_scp_uri_using_player(player, file_path: str) -> str:
    ip = IpTool.format_ip_for_uri(player)
    return f'scp://{player.username}:{player.password}@{ip}{file_path}'


def generate_sftp_uri_using_player(player, file_path: str) -> str:
    ip = IpTool.format_ip_for_uri(player)
    return f'sftp://{player.username}:{player.password}@{ip}{file_path}'


def generate_file_location_uri(file_path: str, localhost: bool = False) -> str:
    """
    Generate a file location uri for a given file path
    - file:///home/admin/cert.p12 no localhost
    - file://localhost/home/admin/cert.pem with localhost
    @param file_path: the path to the file
    @param localhost: if True, the uri will be file://localhost/file_path, otherwise file://file_path
    @return: the file location uri
    """
    if localhost:
        return f'file://localhost{file_path}'
    return f'file://{file_path}'


def is_ipv6_setup(topology, player_name: str) -> bool:
    """Check if a player is on an IPv6-only setup via NOGA attributes."""
    try:
        specific = topology.players[player_name]['attributes'].noga_query_data['attributes']['Specific']
        return 'IPv6 setup' in specific.get('Hardware_state_details', '')
    except (KeyError, AttributeError):
        return False


def get_switch_type(topology):
    switch_type = TopologyConsts.SONIC
    try:
        cli_type = topology.players['dut']['attributes'].noga_query_data['attributes']['Topology Conn.']['CLI_TYPE']
        if cli_type == NvosConst.NVUE_CLI:
            switch_type = topology.players['dut']['attributes'].noga_query_data['attributes']['Specific']['TYPE']
            if switch_type == NvosConst.CUMULUS_SWITCH:
                switch_type = TopologyConsts.CL
            else:
                switch_type = TopologyConsts.NVOS
    except Exception as ex:
        logging.warning(f"Failed to check switch type\n{ex}")
    finally:
        logging.info(f"Switch type: {switch_type}")
        return switch_type


def get_file_hash(engine: LinuxSshEngine, file_path: str) -> str:
    return engine.run_cmd(f"sha1sum {file_path}").split(' ')[0]

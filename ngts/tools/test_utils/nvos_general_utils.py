import fnmatch
import logging
import os
import re
import time
from contextlib import contextmanager
from typing import Tuple

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.constants.constants import LinuxConsts
from ngts.nvos_constants.constants_nvos import ApiType, DiskConsts
from ngts.nvos_tools.infra.DiskTool import DiskTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.authentication_restrictions.constants import RestrictionsConsts
from ngts.tests_nvos.system.clock.ClockConsts import ClockConsts
from ngts.tools.test_utils import allure_utils as allure


def set_base_configurations_cl(dut_engine, timezone=LinuxConsts.ETC_UTC_TIMEZONE, apply=False, save_conf=False):
    """
    @summary: Set base configurations.
        Used in:
            - nvos post installation steps
            - nvos clear config (post test) function
    """
    logging.info('Set base configurations')
    orig_api = TestToolkit.tested_api

    try:
        logging.info('Change tested api to NVUE')
        TestToolkit.tested_api = ApiType.NVUE

        logging.info(f'Set switch timezone: {timezone}')
        system = System()
        system.set(ClockConsts.TIMEZONE, LinuxConsts.ETC_UTC_TIMEZONE, dut_engine=dut_engine).verify_result()

        if apply:
            logging.info('Apply configurations')
            NvueGeneralCli.apply_config(engine=dut_engine, option='--assume-yes')

        if save_conf:
            logging.info('Save configurations')
            NvueGeneralCli.save_config(dut_engine)
    finally:
        logging.info(f'Change tested api back to {orig_api}')
        TestToolkit.tested_api = orig_api


def set_base_configurations(dut_engine, timezone=LinuxConsts.JERUSALEM_TIMEZONE, apply=False, save_conf=False):
    """
    @summary: Set base configurations.
        Used in:
            - nvos post installation steps
            - nvos clear config (post test) function
    """
    logging.info('Set base configurations')
    orig_api = TestToolkit.tested_api

    try:
        logging.info('Change tested api to NVUE')
        TestToolkit.tested_api = ApiType.NVUE

        logging.info(f'Set switch timezone: {timezone}')
        system = System()
        system.set(ClockConsts.TIMEZONE, LinuxConsts.JERUSALEM_TIMEZONE, dut_engine=dut_engine).verify_result()

        logging.info('Set authentication restrictions configurations')
        system.aaa.authentication.restrictions.set(RestrictionsConsts.LOCKOUT_STATE,
                                                   RestrictionsConsts.DISABLED, dut_engine=dut_engine).verify_result()
        system.aaa.authentication.restrictions.set(RestrictionsConsts.FAIL_DELAY, 0,
                                                   dut_engine=dut_engine).verify_result()

        if apply:
            logging.info('Apply configurations')
            NvueGeneralCli.apply_config(engine=dut_engine, option='--assume-yes')

        if save_conf:
            logging.info('Save configurations')
            NvueGeneralCli.save_config(dut_engine)
    finally:
        logging.info(f'Change tested api back to {orig_api}')
        TestToolkit.tested_api = orig_api


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


def get_real_file_path(file_path: str) -> str:
    """
    @summary: Get the real file path from a given path
    """
    real_path = os.path.realpath(file_path)
    containing_dir = os.path.dirname(real_path)
    filename = os.path.basename(real_path)
    dir_content = os.listdir(containing_dir)
    matching_filename = [dir_file for dir_file in dir_content if fnmatch.fnmatch(dir_file, filename)][0]
    real_file_path = os.path.join(containing_dir, matching_filename)
    return real_file_path


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
    switch: ProxySshEngine = TestToolkit.engines.dut

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
                logging.info(f"Available disk space for partition is {storage}")
                # Trim percent symbol from the end, e.g '22%'
                available_disk_space = int(storage.strip()[:-1])
                assert available_disk_space < allowed_limit, f'The disk space is over {allowed_limit}%, so image may ' \
                    f'not fit '
        with allure.step('Check Minimum Free Space'):
            free_space = disk_tool.get_free_space()
            # Trim "G" symbol from the end, e.g '6.7G%'
            free = float(free_space.strip()[:-1])
            assert free >= minimum_free_space, f'Available disk space {free}G is below {minimum_free_space}G'

    finally:
        disk_tool.unmount_partitions(partitions)


def wait_for_ldap_nvued_restart_workaround(test_item, engine_to_use=None):
    with allure.step('After LDAP configuration - wait for NVUE restart Workaround'):
        workaround_max_time = 15
        with allure.step(f'sleep for {workaround_max_time} seconds'):
            time.sleep(workaround_max_time)
        # sleep_time = 3
        # if not engine_to_use:
        #     engine_to_use = test_item.active_remote_admin_engine if hasattr(test_item,
        #                                                                     'active_remote_admin_engine') else TestToolkit.engines.dut
        # with allure.step(f'Disconnect engine of user "{engine_to_use.username}"'):
        #     engine_to_use.disconnect()
        #     time.sleep(sleep_time)
        # with allure.step(f'Wait till cli up - using user "{engine_to_use.username}"'):
        #     wait_until_cli_is_up(engine=engine_to_use)


def is_secure_boot_enabled(engine: ProxySshEngine) -> bool:
    output: str = engine.run_cmd('mokutil --sb-state')
    return output.replace('SecureBoot ', '').strip() == 'enabled'


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


def generate_scp_uri_using_player(player: LinuxSshEngine, file_path: str) -> str:
    return f'scp://{player.username}:{player.password}@{player.ip}{file_path}'

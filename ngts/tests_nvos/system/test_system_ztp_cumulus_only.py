import pytest
import logging
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from retry import retry
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.tools.infra import get_platform_info
from ngts.tools.test_utils.switch_recovery import recover_dut_with_remote_reboot

import time
import json
import re

logger = logging.getLogger()


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.ztp
@pytest.mark.system
def test01_run_ztp_from_local_files_nv(engines, devices):
    """
    Name: run_ztp_from_local_files_nv
    =====
    Description:
    ============
    Verify ZTP running from local files.

    Steps:
    - For every supported local ztp file name:
        - reset ZTP first
        - create ZTP script (has auto provisioning flag and exits 0)
        - starts ZTP using NVUE command
        - verify that ZTP is executed as expected and returns the expected results
        - reset ZTP
    """

    system = System(None)
    try:
        reset_ztp(engines, system)
        vendor, model, revision, arch = get_platform_info_nv(engines)
        ztp_scripts = [
            "/var/lib/cumulus/ztp/cumulus-ztp-{}-{}_{}-r{}".format(arch, vendor, model, revision),
            "/var/lib/cumulus/ztp/cumulus-ztp-{}-{}_{}".format(arch, vendor, model),
            "/var/lib/cumulus/ztp/cumulus-ztp-{}-{}".format(arch, vendor),
            "/var/lib/cumulus/ztp/cumulus-ztp-{}".format(arch),
            "/var/lib/cumulus/ztp/cumulus-ztp"
        ]

        for script in ztp_scripts:
            with allure.step("Download ztp script file"):
                _download_ztp_script_path(engines, script)

            with allure.step("Run nv action run system ztp"):
                # nv action run system ztp force
                system.ztp.action_run_ztp()

            with allure.step("Run show ztp after run and verify values"):
                system_ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()
                logger.info(system_ztp_output)

                with allure.step("Run show ztp and verify default values"):
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)

                with allure.step("Verify show ztp value"):
                    ValidationTool.verify_field_value_in_output(system_ztp_output, 'service', 'disabled').verify_result()
                    ValidationTool.verify_field_value_in_output(system_ztp_output, 'source', 'local-fs').verify_result()

            with allure.step("resetting ZTP"):
                reset_ztp(engines, system)

    except Exception as e:
        logger.info("Received Exception during test_ztp_run_nv: {}".format(e))
        raise e
    finally:
        engines.dut.run_cmd('sudo rm -f /var/lib/cumulus/ztp/cumulus-ztp')
        reset_ztp(engines, system)


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.ztp
@pytest.mark.system
def test02_run_ztp_from_url(engines, devices):
    """
    Name: run_ztp_from_url
    =====
    Description:
    ============
    Verify ZTP running from url.

    Steps:
        - create ZTP script (has auto provisioning flag and exits 0)
        - starts ZTP using NVUE url command
        - verify that ZTP is executed as expected and returns the expected results
    """
    system = System(None)
    try:

        with allure.step("Download ztp script file"):
            _download_ztp_script(engines)

        with allure.step("Run nv action run system ztp url"):
            # nv action run system ztp url <path>
            system.ztp.action_run_ztp_url(url='/var/lib/cumulus/ztp/cumulus-ztp')

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Run show ztp after run url and verify values"):
            system_ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()

            with allure.step("Verify show ztp value"):
                excepted_path = "/var/lib/cumulus/ztp/cumulus-ztp"
                ValidationTool.verify_field_value_in_output(system_ztp_output, 'service', 'disabled').verify_result()
                _wait_until_ztp_url(system, excepted_path)

    except Exception as e:
        logger.info("Received Exception during test_ztp_run_url: {}".format(e))
        raise e
    finally:

        engines.dut.run_cmd('sudo rm -f /var/lib/cumulus/ztp/cumulus-ztp')
        reset_ztp(engines, system)


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.ztp
@pytest.mark.system
def test03_run_ztp_enable(engines, topology_obj):
    """
    Name: run_ztp_enabled
    =====
    Description:
    ============
    Verify ZTP enabled, ZTP must run after the next reboot

    Steps:
        - enable ZTP
        - verify that ZTP is enabled
        - create a script
        - run ZTP using NVUE command
        - wait for ZTP to complete
        - verify that ZTP is executed
    """
    system = System()

    try:

        with allure.step("Run nv action enable system ztp"):
            system.ztp.action_enable_ztp()

            with allure.step("Check ztp status"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_ENABLED)

        with allure.step("Download ztp script file"):
            _download_ztp_script(engines)

        with allure.step("Run nv action run system ztp"):
            # nv action run system ztp force
            system.ztp.action_run_ztp()

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_service(system, SystemConsts.ZTP_SERVICE_DISABLED)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)

    except Exception as e:
        logger.info("Received Exception during test_ztp_enabled {}".format(e))
        raise e
    finally:
        engines.dut.run_cmd('sudo rm -f /var/lib/cumulus/ztp/cumulus-ztp')
        reset_ztp(engines, system)


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.ztp
@pytest.mark.system
def test04_run_ztp_disable(engines, devices):
    """
    Name: run_ztp_disabled
    =====
    Description:
    ============
    Verify ZTP disable, ZTP must not run after the next reboot

    Steps:
        - create a script
        - disable ZTP
        - reboot the cumulus node
        - wait for ZTP to complete
        - verify that ZTP was not executed and disabled
        - reset ZTP
    """
    system = System(None)

    try:

        with allure.step("Download ztp script file"):
            _download_ztp_script(engines)

        with allure.step("Run nv action disable system ztp"):
            system.ztp.action_disable_ztp()

            with allure.step("Check ztp status"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_SERVICE_DISABLED)

        sleep_time_seconds = 240
        with allure.step(f"Reboot the system and sleep {sleep_time_seconds} seconds"):
            reboot_dut(engines, system, sleep_time_seconds)

        with allure.step("Run show ztp after run and verify values"):
            _wait_until_ztp_service(system, SystemConsts.ZTP_SERVICE_DISABLED)

    except Exception as e:
        logger.info("Received Exception during test_ztp_disabled {}".format(e))
        raise e

    finally:
        engines.dut.run_cmd('sudo rm -f /var/lib/cumulus/ztp/cumulus-ztp')
        reset_ztp(engines, system)


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.ztp
@pytest.mark.system
def test05_run_ztp_non_existing_file(engines, devices):
    """
    Name: run_ztp_non_existing_file.
    =====
    Description:
    ============
    Verify ZTP fails when local files do not exist.

    Steps:
        - create ZTP script (has auto provisioning flag and exits 0)
        - run ZTP with URL with a non existing file
        - verify that ZTP is not executed as expected and returns failure
        - starts run ZTP with url with valid file using NVUE command
        - verify that ZTP is executed as expected and returns success
        - reset ZTP
    """
    system = System(None)

    try:
        with allure.step("Download ztp script file"):
            _download_ztp_script(engines)

        with allure.step("Run nv action run system ztp with non-existing url"):
            try:
                system.ztp.action_run_ztp_url(url='/var/lib/cumulus/ztp/negative_cumulus-ztp')
            except Exception as e:
                logger.info("Received Exception during run ZTP URL: {}".format(e))

            with allure.step("Run show ztp after run and verify values"):
                time.sleep(60)
                system_ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()
                ValidationTool.verify_field_value_in_output(system_ztp_output, 'service', 'disabled').verify_result()
                ValidationTool.verify_field_value_in_output(system_ztp_output, 'status', 'failure').verify_result()

        with allure.step("Run nv action run system ztp with valid url"):
            # nv action run system ztp url
            system.ztp.action_run_ztp_url(url='/var/lib/cumulus/ztp/cumulus-ztp')

        with allure.step("Run show ztp after run and verify values"):
            system_ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()
            _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)
            ValidationTool.verify_field_value_in_output(system_ztp_output, 'service', 'disabled').verify_result()

    except Exception as e:
        logger.info("Received Exception during test_ztp_connectivity_check: {}".format(e))
        raise e
    finally:
        engines.dut.run_cmd('sudo rm -f /var/lib/cumulus/ztp/cumulus-ztp')
        reset_ztp(engines, system)


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.ztp
@pytest.mark.system
def test06_run_ztp_script_config_reboot(engines, devices):
    """
    Name: run_ztp_script_config
    ====
    Description:
    ============
    Verify ZTP running with reboot in ztp script

    Steps:
         - create a script (has auto provisioning flag and exits 0) with reload
         - run ztp
         - wait for ZTP to complete
         - verify that ZTP is executed as expected and returns the expected results
         - run it again using NVUE command
         - verify that ZTP completes again (RM2660705)
    """
    system = System(None)

    try:
        with allure.step("Download ztp script file"):
            _download_ztp_script_reboot(engines)

        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp()
            logger.info("excepted rebooting of the dut")
            time.sleep(240)
            with allure.step('Wait for switch to be up'):
                engines.dut.disconnect()
                time.sleep(30)

            with allure.step("Run show ztp after run and verify values"):
                system_ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)
                ValidationTool.verify_field_value_in_output(system_ztp_output, 'service', 'disabled').verify_result()

    except Exception as e:
        logger.info("Received Exception during test_ztp_connectivity_check: {}".format(e))
        raise e
    finally:
        engines.dut.run_cmd('sudo rm -f /var/lib/cumulus/ztp/cumulus-ztp')
        reset_ztp(engines, system)


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.ztp
@pytest.mark.system
def test07_run_ztp_abort(engines, devices):
    """
    Description:
    ============
    Verify ZTP abort while ztp script is running

    Steps:
        - create a script (has auto provisioning flag and exits 0) with reload
        - run ztp
        - wait for ZTP
        - abort ztp while ZTP is running
        - verify that ZTP is aborted as expected and returns the expected results

    """
    system = System(None)
    try:
        reset_ztp(engines, system)
        with allure.step("Download ztp script file"):
            _download_ztp_script(engines, cmd="sleep 100")

            with allure.step("Run nv action run system ztp"):
                system.ztp.action_run_ztp()
                with allure.step("Run nv action abort system ztp "):
                    system.ztp.action_abort_ztp()

                with allure.step("Check ztp status"):
                    # ztp status enabled since it did not run
                    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_ENABLED)

    except Exception as e:
        logger.info("Received Exception during test_ztp_connectivity_check: {}".format(e))
        raise e
    finally:
        engines.dut.run_cmd('sudo rm -f /var/lib/cumulus/ztp/cumulus-ztp')
        reset_ztp(engines, system)


@pytest.mark.cumulus
@pytest.mark.cumulus_only
@pytest.mark.ztp
@pytest.mark.system
def test08_run_ztp_run_after_enable(engines, topology_obj):
    """
    Name: run_ztp_run_after_enable
    =====
    Description:
    ============
    Verify ZTP enabled, ZTP must run after the next reboot/run
    enable ztp does not delete ztp script

    Steps:
        - create a script
        - enable ZTP
        - verify that ZTP is enabled
        - verify script is present
        - run ZTP
        - wait for ZTP to complete
        - verify that ZTP is executed
    """
    system = System()

    try:
        with allure.step("Download ztp script file"):
            _download_ztp_script(engines)

        with allure.step("Run nv action enable system ztp"):
            system.ztp.action_enable_ztp()

            with allure.step("Check ztp status"):
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_ENABLED)
                try:
                    engines.dut.run_cmd('cat /var/lib/cumulus/ztp/cumulus-ztp')
                except Exception as e:
                    logger.info("ztp script not found: /var/lib/cumulus/ztp/cumulus-ztp")

        with allure.step("Run nv action run system ztp"):
            system.ztp.action_run_ztp()

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_service(system, SystemConsts.ZTP_SERVICE_DISABLED)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)

        with allure.step("Download ztp script file"):
            _download_ztp_script(engines)

        with allure.step("Run nv action enable system ztp"):
            system.ztp.action_enable_ztp()

        with allure.step("Run nv action run system ztp url"):
            # nv action run system ztp url < >
            system.ztp.action_run_ztp_url(url='/var/lib/cumulus/ztp/cumulus-ztp')

            with allure.step("Run show ztp and verify default values"):
                _wait_until_ztp_service(system, SystemConsts.ZTP_SERVICE_DISABLED)
                _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_SUCCESS)

    except Exception as e:
        logger.info("Received Exception during test_run_ztp_run_after_enable {}".format(e))
        raise e
    finally:
        engines.dut.run_cmd('sudo rm -f /var/lib/cumulus/ztp/cumulus-ztp')
        reset_ztp(engines, system)


def reboot_dut(engines, system, sleep_time_seconds=240):
    try:
        system.reboot.action_reboot(engines.dut)
        # system.reboot.action_reboot()
    except Exception as e:
        logger.info("excepted rebooting of the dut: {}".format(e))
        time.sleep(sleep_time_seconds)
        with allure.step('Wait for switch to be up'):
            engines.dut.disconnect()
            time.sleep(30)


def create_script(cmds=None, auto_flag=True, cascade_flag=False, front_panel_flag=False, exit=0, config_reboot=False):
    script_str = '#!/bin/sh\n'
    if cmds:
        script_str += cmds + '\n'
    if auto_flag:
        script_str += '# CUMULUS-AUTOPROVISIONING\n'
    if cascade_flag:
        script_str += '# CUMULUS-AUTOPROVISIONING-CASCADE\n'
    if front_panel_flag:
        script_str += '# CUMULUS-AUTOPROVISIONING-FRONT-PANEL\n'
    if config_reboot:
        script_str += 'nv set interface lo ip address 2000::1/128\n'
        script_str += 'nv config apply -y; nv config save\n'
        script_str += 'shutdown -r +1 \n'
    script_str += 'exit ' + str(exit)
    return script_str


def _download_ztp_script(engines, cmd=''):
    engines.dut.run_cmd('sudo rm -f /var/lib/cumulus/ztp/cumulus-ztp')
    success_str = create_script(cmds=cmd)
    # return engines.dut.run_cmd("echo '{}' > {}' ".format(success_str, '/var/lib/cumulus/ztp/cumulus-ztp'))
    return engines.dut.run_cmd("echo '{}' | sudo tee {} > /dev/null".format(success_str, '/var/lib/cumulus/ztp/cumulus-ztp'))


def _download_ztp_script_path(engines, path=''):
    engines.dut.run_cmd('sudo rm -f {}'.format(path))
    success_str = create_script()
    return engines.dut.run_cmd("echo '{}' | sudo tee {} > /dev/null".format(success_str, path))


def _download_ztp_script_reboot(engines):
    engines.dut.run_cmd('sudo rm -f /var/lib/cumulus/ztp/cumulus-ztp')
    success_str = create_script(config_reboot=True)
    return engines.dut.run_cmd("echo '{}' | sudo tee {} > /dev/null".format(success_str, '/var/lib/cumulus/ztp/cumulus-ztp'))


@retry(Exception, tries=30, delay=2)
def _wait_until_ztp_status(system, ztp_status=''):
    with allure.step("Waiting for ztp status changed to status {}".format(ztp_status)):
        ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()
        logger.info(ztp_output)
        assert ztp_output['status'] == ztp_status, f'ztp status not changed to {ztp_status}'


@retry(Exception, tries=30, delay=2)
def _wait_until_ztp_service(system, ztp_service=''):
    with allure.step("Waiting for ztp service changed to service {}".format(ztp_service)):
        ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()
        logger.info(ztp_output)
        assert ztp_output['service'] == ztp_service, f'ztp status not changed to {ztp_service}'


@retry(Exception, tries=30, delay=2)
def _wait_until_ztp_url(system, url=''):
    with allure.step("Waiting for ztp url changed to path {}".format(url)):
        ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system.ztp.show()).get_returned_value()
        logger.info(ztp_output)
        assert ztp_output['script']['location'] == url, f'ztp status not changed to {url}'


def _wait_until_ztp_step_status(system, ztp_step='', ztp_status='', tries=30, delay=2):
    @retry(Exception, tries=tries, delay=delay)
    def _retry_decorator(system_obj, ztp_step_name='', ztp_status_name=''):
        logger.info("calling wait until ztp step status")
        with allure.step("Waiting for ztp status changed to status {}".format(ztp_status_name)):
            ztp_output = OutputParsingTool.parse_json_str_to_dictionary(system_obj.ztp.show()).get_returned_value()
            logger.info(ztp_output)
            assert ztp_output['stage'][ztp_step_name]['status'] == ztp_status_name, \
                f'ztp status not changed to {ztp_status_name}'
    _retry_decorator(system, ztp_step, ztp_status)


def reset_ztp(engines, system):
    logger.info('Resetting ZTP')
    engines.dut.run_cmd('sudo ztp -R')
    time.sleep(10)
    _wait_until_ztp_status(system, SystemConsts.ZTP_STATUS_ENABLED)


def get_platform_info(engines):
    # platform = node.device.sudo('/usr/bin/platform-detect --all')
    platform = engines.dut.run_cmd('/usr/bin/platform-detect --all')
    platform_fields = platform.replace(',', ' ').split()
    vendor = platform_fields[0]
    model = platform_fields[1]
    revision = platform_fields[2]
    arch = engines.dut.run_cmd('/bin/uname -m')
    return vendor, model, revision, arch


def get_platform_info_nv(engines):
    platform = engines.dut.run_cmd('/usr/bin/platform-detect --all')
    platform_fields = platform.replace(',', ' ').split()
    vendor = platform_fields[0]
    model = platform_fields[1]
    revision = platform_fields[2]
    arch = engines.dut.run_cmd('/bin/uname -m')

    return vendor, model, revision, arch

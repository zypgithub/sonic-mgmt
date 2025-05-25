import io
import os
import re
import json
import yaml
import time
import logging
import tempfile
import ConfigParser
import pytest

from tests.common.utilities import wait_until
from tests.common.plugins.loganalyzer.loganalyzer import LogAnalyzer, LogAnalyzerError

PLATFORM_COMP_PATH_TEMPLATE = '/usr/share/sonic/device/{}/platform_components.json'

FW_INSTALL_INVALID_NAME_LOG = '.*Invalid value for "<component_name>"*.'
FW_INSTALL_INVALID_PATH_LOG = '.*Error: Invalid value for "<fw_path>"*.'
FW_INSTALL_INVALID_URL_LOG = '.*Error: Did not receive a response from remote machine. Aborting...*.'

FW_UPDATE_INVALID_PLATFORM_SCHEMA_LOG = '.*Error: Failed to parse "platform_components.json": invalid platform schema*.'
FW_UPDATE_INVALID_CHASSIS_SCHEMA_LOG = '.*Error: Failed to parse "platform_components.json": invalid chassis schema*.'
FW_UPDATE_INVALID_COMPONENT_SCHEMA_LOG = '.*Error: Failed to parse "platform_components.json": invalid component schema*.'

FW_INSTALL_START_LOG = "Firmware install started: component=.*, firmware=.*"
FW_INSTALL_SUCCESS_LOG = "Firmware install ended: component=.*, firmware=.*, status=success"

FW_UPDATE_START_LOG = "Firmware update started: component=.*, firmware=.*"
FW_UPDATE_SUCCESS_LOG = "Firmware update ended: component=.*, firmware=.*, status=success"

FW_TYPE_INSTALL = 'install'
FW_TYPE_UPDATE = 'update'

IMAGE_TYPE_CURRENT = 'current'
IMAGE_TYPE_NEXT = 'next'

SUCCESS_CODE = 0

logger = logging.getLogger(__name__)


class FwComponent(object):

    def _kill_task(self, duthost, cmd, task, result):
        """
        Kill task
        """
        # W/A for ThreadPool().terminate()
        try:
            pid = duthost.command("pgrep -f '{}'".format(cmd))['stdout']
            duthost.command("kill -s SIGKILL {}".format(pid))

            result_json = json.dumps(result.get(timeout=5), indent=4)
            logger.error("{} firmware task stucked:\n{}".format(self.get_name(), result_json))

            task.terminate()
            task.join()
        except Exception as e:
            pytest.fail("Failed to kill stucked {} firmware task: {}".format(self.get_name(), str(e)))

    def get_name(self):
        """
        Get component name
        """
        raise NotImplemented

    def check_version(self, fw_version, comp_fw_status):
        """
        Check if component firmware version was updated as expected
        """
        raise NotImplemented

    def process_versions(self, duthost, binaries_path, fw_type):
        """
        Process latest/other component firmware versions
        """
        raise NotImplemented

    def install_fw(self, request, install_cmd, fw_path=None, fw_version=None):
        """
        Install component firmware
        """
        raise NotImplemented

    def update_fw(self, request, update_cmd, fw_path=None, fw_version=None):
        """
        Update component firmware
        """
        raise NotImplemented


class OnieComponent(FwComponent):
    COMPONENT_TYPE = 'onie'

    def __init__(self, comp_name):
        self.__name = comp_name

    def __parse_version(self, files_path):
        fw_path = None
        fw_ver = None

        release_path = os.path.realpath(files_path)
        fw_ver = os.path.basename(os.path.dirname(release_path))
        fw_ver += "-{}".format(os.path.basename(release_path))

        for file_name in os.listdir(release_path):
            if file_name.startswith('onie-updater'):
                fw_path = os.path.join(release_path, file_name)
                break

        return fw_path, fw_ver

    def get_name(self):
        return self.__name

    def check_version(self, fw_version, comp_fw_status):
        return comp_fw_status['version'].startswith(fw_version)

    def process_versions(self, duthost, binaries_path, fw_type):
        files_path = os.path.join(binaries_path, self.COMPONENT_TYPE)
        fw_status = get_fw_status(duthost)

        latest_fw_path = None
        latest_ver = None
        previous_fw_path = None
        previous_ver = None
        is_latest = False

        for file_name in os.listdir(files_path):
            if file_name.startswith('latest'):
                latest_fw_path, latest_ver = self.__parse_version(os.path.join(files_path, file_name))

                if fw_status['ONIE']['version'].startswith(latest_ver):
                    is_latest = True
            elif file_name.startswith('other'):
                previous_fw_path, previous_ver = self.__parse_version(os.path.join(files_path, file_name))

        if latest_fw_path is None or previous_fw_path is None:
            pytest.skip("{} firmware updates are not available".format(self.get_name()))

        versions = {
            'previous_firmware': previous_fw_path,
            'previous_version': previous_ver,
            'latest_firmware': latest_fw_path,
            'latest_version': latest_ver,
            'is_latest_installed': is_latest
        }
        logger.info("Parsed {} versions:\n{}".format(self.get_name(), json.dumps(versions, indent=4)))

        return versions

    def __execute_task(self, request, cmd):
        localhost = request.getfixturevalue('localhost')
        duthost = request.getfixturevalue('duthost')

        hostname = duthost.hostname

        logger.info("Execute {} firmware task: cmd={}".format(self.get_name(), cmd))
        fw_task, fw_result = duthost.command(cmd, module_ignore_errors=True, module_async=True)

        logger.info("Wait for {} to go down".format(hostname))
        result = localhost.wait_for(host=hostname, port=22, state='stopped', timeout=180, module_ignore_errors=True)

        if 'msg' in result.keys() and 'Timeout' in result['msg']:
            try:
                result_json = json.dumps(fw_result.get(timeout=0), indent=4)
                logger.error("{} firmware task failed:\n{}".format(self.get_name(), result_json))
            except:
                self._kill_task(duthost, cmd, fw_task, fw_result)

            pytest.fail(result['msg'])

        logger.info("Wait for {} to come back".format(hostname))
        localhost.wait_for(host=hostname, port=22, state='started', delay=10, timeout=300)

        logger.info("Wait until system is stable")
        wait_until(300, 30, 0, duthost.critical_services_fully_started)

        logger.info("Wait until system init is done")
        time.sleep(30)

    def install_fw(self, request, install_cmd, fw_path=None, fw_version=None):
        duthost = request.getfixturevalue('duthost')

        loganalyzer = LogAnalyzer(ansible_host=duthost, marker_prefix='fwutil')
        loganalyzer.expect_regex = [ FW_INSTALL_START_LOG ]

        with loganalyzer:
            self.__execute_task(request, install_cmd)

    def update_fw(self, request, update_cmd, fw_path=None, fw_version=None):
        duthost = request.getfixturevalue('duthost')

        loganalyzer = LogAnalyzer(ansible_host=duthost, marker_prefix='fwutil')
        loganalyzer.expect_regex = [ FW_UPDATE_START_LOG ]

        with loganalyzer:
            self.__execute_task(request, update_cmd)


class SsdComponent(FwComponent):
    COMPONENT_TYPE = 'ssd'

    def __init__(self, comp_name):
        self.__name = comp_name

    def __get_ssd_info(self, duthost):
        cmd = '/usr/bin/mlnx-ssd-fw-update.sh -q'
        result = duthost.command(cmd)

        ssd_info = { }

        for line in result['stdout'].splitlines():
            cols = line.split(':')

            if cols[0].startswith('Device Model'):
                ssd_info['model'] = cols[1].lstrip(' \t')
            if cols[0].startswith('User Capacity'):
                ssd_info['size'] = cols[1].replace('GB', ' ').strip(' \t')
            if cols[0].startswith('Firmware Version'):
                ssd_info['fw'] = cols[1].lstrip(' \t')

        return ssd_info

    def __get_ssd_image_info(self, image_path):
        contents_path = None

        try:
            contents_path = tempfile.mkdtemp(prefix='pkg-')
            cmd = "tar zxf {} -C {} --strip-components=1".format(image_path, contents_path)
            subprocess.check_call(cmd.split())

            cp = ConfigParser.ConfigParser()
            with io.open(os.path.join(contents_path, 'list.ini'), 'rb') as list_ini:
                cp.readfp(list_ini)
        finally:
            if contents_path is not None and os.path.exists(contents_path):
                cmd = "rm -rf {}".format(contents_path)
                subprocess.check_call(cmd.split())

        ssd_image_info = [ ]

        for section in cp.sections():
            if cp.has_option(section, 'SSD_FW_Model'):
                data = { }

                data['model'] = cp.get(section, 'SSD_FW_Model')
                data['size'] = cp.get(section, 'SSD_Size')
                data['fw_required'] = cp.get(section, 'SSD_FW_Version')
                data['fw_available'] = cp.get(section, 'Newer_FW_Version')
                data['shutdown_policy'] = cp.get(section, 'Shutdown_Policy')

                ssd_image_info.append(data)

        return ssd_image_info

    def __parse_version(self, duthost, latest_fw_path, previous_fw_path):
        ssd_info = self.__get_ssd_info(duthost)
        logger.info("Parsed {} info:\n{}".format(self.get_name(), json.dumps(ssd_info, indent=4)))

        ssd_downgrade_image_info = self.__get_ssd_image_info(previous_fw_path)
        ssd_upgrade_image_info = self.__get_ssd_image_info(latest_fw_path)

        downgrade_info = [ ]

        for item in ssd_downgrade_image_info:
            if item['model'] == ssd_info['model'] and item['size'] == ssd_info['size']:
                downgrade_info.append(item)

        upgrade_info = [ ]

        for item in ssd_upgrade_image_info:
            if item['model'] == ssd_info['model'] and item['size'] == ssd_info['size']:
                upgrade_info.append(item)

        logger.info("Parsed {} downgrade image info:\n{}".format(self.get_name(), json.dumps(downgrade_info, indent=4)))
        logger.info("Parsed {} upgrade image info:\n{}".format(self.get_name(), json.dumps(upgrade_info, indent=4)))

        if not downgrade_info or not upgrade_info:
            return ssd_info['fw'], ssd_info['fw']

        downgrade_fw_versions = { }
        downgrade_fw_versions['fw_required'] = [ ]
        downgrade_fw_versions['fw_available'] = [ ]

        for item in downgrade_info:
            downgrade_fw_versions['fw_required'].append(item['fw_required'])
            downgrade_fw_versions['fw_available'].append(item['fw_available'])

        upgrade_fw_versions = { }
        upgrade_fw_versions['fw_required'] = [ ]
        upgrade_fw_versions['fw_available'] = [ ]

        for item in upgrade_info:
            upgrade_fw_versions['fw_required'].append(item['fw_required'])
            upgrade_fw_versions['fw_available'].append(item['fw_available'])

        latest_ver = set(upgrade_fw_versions['fw_available']) & set(downgrade_fw_versions['fw_required'])
        previous_ver = set(upgrade_fw_versions['fw_required']) & set(downgrade_fw_versions['fw_available'])

        if len(latest_ver) != 1 or len(previous_ver) != 1:
            pytest.fail(
                "Failed to parse {} firmware versions: latest={}, previous={}".format(
                    self.get_name(),
                    latest_ver,
                    previous_ver
                )
            )

        return latest_ver.pop(), previous_ver.pop()

    def get_name(self):
        return self.__name

    def check_version(self, fw_version, comp_fw_status):
        return comp_fw_status['version'].startswith(fw_version)

    def process_versions(self, duthost, binaries_path, fw_type):
        files_path = os.path.join(binaries_path, self.COMPONENT_TYPE)
        fw_status = get_fw_status(duthost)

        latest_fw_path = None
        latest_ver = None
        previous_fw_path = None
        previous_ver = None
        is_latest = False

        for file_name in os.listdir(files_path):
            if file_name.startswith('latest'):
                latest_fw_path = os.path.realpath(os.path.join(files_path, file_name))
            elif file_name.startswith('other'):
                previous_fw_path = os.path.realpath(os.path.join(files_path, file_name))

        if latest_fw_path is None or previous_fw_path is None:
            pytest.skip("{} firmware updates are not available".format(self.get_name()))

        latest_ver, previous_ver = self.__parse_version(duthost, latest_fw_path, previous_fw_path)

        if fw_status['SSD']['version'].startswith(latest_ver):
            is_latest = True

        versions = {
            'previous_firmware': previous_fw_path,
            'previous_version': previous_ver,
            'latest_firmware': latest_fw_path,
            'latest_version': latest_ver,
            'is_latest_installed': is_latest
        }
        logger.info("Parsed {} versions:\n{}".format(self.get_name(), json.dumps(versions, indent=4)))

        return versions

    def __execute_task(self, request, cmd, shutdown_policy):
        localhost = request.getfixturevalue('localhost')
        duthost = request.getfixturevalue('duthost')

        hostname = duthost.hostname

        logger.info("Execute {} firmware task: cmd={}".format(self.get_name(), cmd))

        if not shutdown_policy:
            duthost.command(cmd)
            return

        fw_task, fw_result = duthost.command(cmd, module_ignore_errors=True, module_async=True)

        logger.info("Wait for {} to go down".format(hostname))
        result = localhost.wait_for(host=hostname, port=22, state='stopped', timeout=180, module_ignore_errors=True)

        if 'msg' in result.keys() and 'Timeout' in result['msg']:
            try:
                result_json = json.dumps(fw_result.get(timeout=0), indent=4)
                logger.error("{} firmware task failed:\n{}".format(self.get_name(), result_json))
            except:
                self._kill_task(duthost, cmd, fw_task, fw_result)

            pytest.fail(result['msg'])

        logger.info("Wait for {} to come back".format(hostname))
        localhost.wait_for(host=hostname, port=22, state='started', delay=10, timeout=300)

        logger.info("Wait until system is stable")
        wait_until(300, 30, 0, duthost.critical_services_fully_started)

        logger.info("Wait until system init is done")
        time.sleep(30)

    def install_fw(self, request, install_cmd, fw_path=None, fw_version=None):
        duthost = request.getfixturevalue('duthost')

        ssd_image_info = self.__get_ssd_image_info(fw_path)
        ssd_image_info = filter(lambda arg: arg['fw_available'] == fw_version, ssd_image_info)[0]

        loganalyzer = LogAnalyzer(ansible_host=duthost, marker_prefix='fwutil')

        if ssd_image_info['shutdown_policy'] == 'Yes':
            loganalyzer.expect_regex = [ FW_INSTALL_START_LOG ]

            with loganalyzer:
                self.__execute_task(request, install_cmd, shutdown_policy=True)
        else:
            loganalyzer.expect_regex = [ FW_INSTALL_START_LOG, FW_INSTALL_SUCCESS_LOG ]

            with loganalyzer:
                self.__execute_task(request, install_cmd, shutdown_policy=False)

    def update_fw(self, request, update_cmd, fw_path=None, fw_version=None):
        duthost = request.getfixturevalue('duthost')

        ssd_image_info = self.__get_ssd_image_info(fw_path)
        ssd_image_info = filter(lambda arg: arg['fw_available'] == fw_version, ssd_image_info)[0]

        loganalyzer = LogAnalyzer(ansible_host=duthost, marker_prefix='fwutil')

        if ssd_image_info['shutdown_policy'] == 'Yes':
            loganalyzer.expect_regex = [ FW_UPDATE_START_LOG ]

            with loganalyzer:
                self.__execute_task(request, update_cmd, shutdown_policy=True)
        else:
            loganalyzer.expect_regex = [ FW_UPDATE_START_LOG, FW_UPDATE_SUCCESS_LOG ]

            with loganalyzer:
                self.__execute_task(request, update_cmd, shutdown_policy=False)


class BiosComponent(FwComponent):
    COMPONENT_TYPE = 'bios'

    def __init__(self, comp_name):
        self.__name = comp_name

    def __parse_version(self, files_path):
        fw_path = None
        fw_ver = None

        release_path = os.path.realpath(files_path)
        baudrate = os.path.basename(release_path).split('_')

        fw_ver = os.path.basename(os.path.dirname(release_path))
        fw_ver = fw_ver[::-1].replace('x', '0', 1)[::-1]

        if len(baudrate) > 1:
            fw_ver += "_{}".format(baudrate[1])

        for file_name in os.listdir(release_path):
            if file_name.endswith('.rom'):
                fw_path = os.path.join(release_path, file_name)
                break

        return fw_path, fw_ver

    def get_name(self):
        return self.__name

    def check_version(self, fw_version, comp_fw_status):
        return comp_fw_status['version'].startswith(fw_version)

    def process_versions(self, duthost, binaries_path, fw_type):
        files_path = os.path.join(binaries_path, self.COMPONENT_TYPE)
        platform_type = duthost.facts['platform']
        fw_status = get_fw_status(duthost)
        latest = '{}_latest'.format(platform_type)
        other = '{}_other'.format(platform_type)

        latest_fw_path = None
        latest_ver = None
        previous_fw_path = None
        previous_ver = None
        is_latest = False

        for file_name in os.listdir(files_path):
            if file_name.startswith(latest):
                latest_fw_path, latest_ver = self.__parse_version(os.path.join(files_path, file_name))

                if fw_status['BIOS']['version'].startswith(latest_ver):
                    is_latest = True
            elif file_name.startswith(other):
                previous_fw_path, previous_ver = self.__parse_version(os.path.join(files_path, file_name))

        if latest_fw_path is None or previous_fw_path is None:
            pytest.skip("{} firmware updates are not available".format(self.get_name()))

        versions = {
            'previous_firmware': previous_fw_path,
            'previous_version': previous_ver,
            'latest_firmware': latest_fw_path,
            'latest_version': latest_ver,
            'is_latest_installed': is_latest
        }
        logger.info("Parsed {} versions:\n{}".format(self.get_name(), json.dumps(versions, indent=4)))

        return versions

    def __execute_task(self, request, cmd):
        localhost = request.getfixturevalue('localhost')
        duthost = request.getfixturevalue('duthost')

        hostname = duthost.hostname

        logger.info("Execute {} firmware task: cmd={}".format(self.get_name(), cmd))
        fw_task, fw_result = duthost.command(cmd, module_ignore_errors=True, module_async=True)

        logger.info("Wait for {} to go down".format(hostname))
        result = localhost.wait_for(host=hostname, port=22, state='stopped', timeout=180, module_ignore_errors=True)

        if 'msg' in result.keys() and 'Timeout' in result['msg']:
            try:
                result_json = json.dumps(fw_result.get(timeout=0), indent=4)
                logger.error("{} firmware task failed:\n{}".format(self.get_name(), result_json))
            except:
                self._kill_task(duthost, cmd, fw_task, fw_result)

            pytest.fail(result['msg'])

        logger.info("Wait for {} to come back".format(hostname))
        localhost.wait_for(host=hostname, port=22, state='started', delay=10, timeout=300)

        logger.info("Wait until system is stable")
        wait_until(300, 30, 0, duthost.critical_services_fully_started)

        logger.info("Wait until system init is done")
        time.sleep(30)

    def install_fw(self, request, install_cmd, fw_path=None, fw_version=None):
        duthost = request.getfixturevalue('duthost')

        loganalyzer = LogAnalyzer(ansible_host=duthost, marker_prefix='fwutil')
        loganalyzer.expect_regex = [ FW_INSTALL_START_LOG ]

        with loganalyzer:
            self.__execute_task(request, install_cmd)

    def update_fw(self, request, update_cmd, fw_path=None, fw_version=None):
        duthost = request.getfixturevalue('duthost')

        loganalyzer = LogAnalyzer(ansible_host=duthost, marker_prefix='fwutil')
        loganalyzer.expect_regex = [ FW_UPDATE_START_LOG ]

        with loganalyzer:
            self.__execute_task(request, update_cmd)


class CpldComponent(FwComponent):
    COMPONENT_TYPE = 'cpld'

    FW_EXTENSION_INSTALL = '.vme'
    FW_EXTENSION_UPDATE = '.mpfa'

    def __init__(self, comp_name):
        self.__name = comp_name

    def __get_part_number(self, files_path):
        cpld_pn = None

        config_file_path = os.path.join(files_path, 'cpld_name_to_pn.yml')
        with io.open(config_file_path, 'rb') as config_file:
            cpld_name_to_pn_dict = yaml.safe_load(config_file)
            cpld_pn = cpld_name_to_pn_dict[self.get_name()]

        return cpld_pn

    def __parse_install_version(self, files_path, file_name):
        fw_path = os.path.join(files_path, file_name)
        real_fw_path = os.path.realpath(fw_path)
        fw_rev = os.path.splitext(os.path.basename(real_fw_path))[0].upper()

        # get CPLD part number
        cpld_pn = self.__get_part_number(files_path)
        if cpld_pn not in fw_rev:
            raise RuntimeError("Part number is not found: pn={}, rev={}".format(cpld_pn, fw_rev))

        # parse CPLD version
        cpld_ver = fw_rev.split(cpld_pn)[1]
        cpld_ver = cpld_ver[1:].split('_')[0]
        cpld_ver_major = cpld_ver[:5]
        cpld_ver_minor = cpld_ver[5:]

        return cpld_pn, cpld_ver_major, cpld_ver_minor

    def __parse_update_version(self, files_path, file_name):
        fw_path = os.path.join(files_path, file_name)

        contents_path = tempfile.mkdtemp(prefix='mpfa-')
        metadata_path = os.path.join(contents_path, 'metadata.ini')

        try:
            cmd = "tar xzf {} -C {}".format(fw_path, contents_path)
            subprocess.check_call(cmd.split())

            if not os.path.isfile(metadata_path):
                raise RuntimeError("Metadata doesn't exist: path={}".format(metadata_path))

            cp = ConfigParser.ConfigParser()
            with io.open(metadata_path, 'rb') as metadata_ini:
                cp.readfp(metadata_ini)
        finally:
            cmd = "rm -rf {}".format(contents_path)
            subprocess.check_call(cmd.split())

        if not cp.has_option('version', self.get_name()):
            raise RuntimeError("Failed to get {} firmware version: path={}".format(self.get_name(), fw_path))

        # get CPLD version
        fw_rev = cp.get('version', self.get_name())

        # get CPLD part number
        cpld_pn = self.__get_part_number(files_path)
        if cpld_pn not in fw_rev:
            raise RuntimeError("Part number is not found: pn={}, rev={}".format(cpld_pn, fw_rev))

        # parse CPLD version
        cpld_pn = fw_rev.split('_')[0]
        cpld_ver = fw_rev.split('_')[1]
        cpld_ver_major = cpld_ver[:5]
        cpld_ver_minor = cpld_ver[5:]

        return cpld_pn, cpld_ver_major, cpld_ver_minor

    def __parse_version(self, files_path, file_name, fw_status, fw_type, platform_type):
        # parse CPLD version
        if fw_type == FW_TYPE_INSTALL:
            cpld_pn, cpld_ver_major, cpld_ver_minor = self.__parse_install_version(files_path, file_name)
        else:
            cpld_pn, cpld_ver_major, cpld_ver_minor = self.__parse_update_version(files_path, file_name)

        # parse component version
        comp_pn = fw_status[self.get_name()]['version'].split('_')[0]
        comp_ver = fw_status[self.get_name()]['version'].split('_')[1]
        comp_ver_major = comp_ver[:5]
        comp_ver_minor = comp_ver[5:]

        parsed_ver = "{}_{}{}".format(cpld_pn, cpld_ver_major, cpld_ver_minor)

        # handle not supported CPLD3 (Port CPLD) P/N and version minor on SPC-1
        if platform_type in ['x86_64-mlnx_msn2700-r0']:
            if self.get_name() == 'CPLD3':
                parsed_ver = "{}_{}{}".format(comp_pn, cpld_ver_major, comp_ver_minor)

        return parsed_ver, cpld_ver_major == comp_ver_major

    def get_name(self):
        return self.__name

    def check_version(self, fw_version, comp_fw_status):
        return comp_fw_status['version'].startswith(fw_version)

    def process_versions(self, duthost, binaries_path, fw_type):
        platform_type = duthost.facts['platform']
        files_path = os.path.join(binaries_path, self.COMPONENT_TYPE, platform_type)
        fw_status = get_fw_status(duthost)

        if fw_type not in [ FW_TYPE_INSTALL, FW_TYPE_UPDATE ]:
            raise RuntimeError("Invalid firmware type is provided: {}".format(fw_type))

        if fw_type == FW_TYPE_INSTALL:
            latest = 'latest{}'.format(self.FW_EXTENSION_INSTALL)
            other = 'other{}'.format(self.FW_EXTENSION_INSTALL)
        else:
            latest = 'latest{}'.format(self.FW_EXTENSION_UPDATE)
            other = 'other{}'.format(self.FW_EXTENSION_UPDATE)

        latest_fw_path = None
        latest_ver = None
        previous_fw_path = None
        previous_ver = None
        is_previous = False
        is_latest = False

        for file_name in os.listdir(files_path):
            if file_name.startswith(latest):
                latest_ver, is_latest = self.__parse_version(files_path, file_name, fw_status, fw_type, platform_type)
                latest_fw_path = os.path.realpath(os.path.join(files_path, file_name))
            if file_name.startswith(other):
                previous_ver, is_previous = self.__parse_version(files_path, file_name, fw_status, fw_type, platform_type)
                previous_fw_path = os.path.realpath(os.path.join(files_path, file_name))

        if latest_fw_path is None or previous_fw_path is None:
            pytest.skip("{} firmware updates are not available".format(self.get_name()))

        versions = {
            'previous_firmware': previous_fw_path,
            'previous_version': previous_ver,
            'latest_firmware': latest_fw_path,
            'latest_version': latest_ver,
            'is_latest_installed': is_latest
        }
        logger.info("Parsed {} versions:\n{}".format(self.get_name(), json.dumps(versions, indent=4)))

        return versions

    def __install_fw(self, request, cmd):
        localhost = request.getfixturevalue('localhost')
        duthost = request.getfixturevalue('duthost')

        hostname = duthost.hostname

        logger.info("Execute {} firmware task: cmd={}".format(self.get_name(), cmd))
        duthost.command(cmd)

        logger.info("Complete {} firmware update: run power cycle".format(self.get_name()))

        logger.info("Get {} number of PSUs".format(hostname))
        psu_num_cmd = 'sudo psuutil numpsus'
        psu_num_out = duthost.command(psu_num_cmd)

        try:
            psu_num = int(psu_num_out['stdout'])
        except Exception as e:
            pytest.fail("Failed to get {} number of PSUs: {}".format(hostname, str(e)))

        logger.info("Create {} PDU controller".format(hostname))
        pdu_controller = request.getfixturevalue('pdu_controller')
        if pdu_controller is None:
            pytest.fail("Failed to create {} PDU controller".format(hostname))

        outlet_status = pdu_controller.get_outlet_status()
        if outlet_status:
            # turn off all psu
            for outlet in outlet_status:
                if outlet['outlet_on']:
                    logger.info("Turn off outlet: id={}".format(outlet['outlet_id']))
                    pdu_controller.turn_off_outlet(outlet)
                    time.sleep(5)

            logger.info("Wait for 30 sec to trigger {} firmware refresh".format(self.get_name()))
            time.sleep(30)

            outlet_status = pdu_controller.get_outlet_status()
            if outlet_status:
                # turn on all psu
                for outlet in outlet_status:
                    if not outlet['outlet_on']:
                        logger.info("Turn on outlet: id={}".format(outlet['outlet_id']))
                        pdu_controller.turn_on_outlet(outlet)
                        time.sleep(5)

        logger.info("Wait for {} to come back".format(hostname))
        localhost.wait_for(host=hostname, port=22, state='started', delay=10, timeout=300)

        logger.info("Wait until system is stable")
        wait_until(300, 30, 0, duthost.critical_services_fully_started)

        logger.info("Wait until system init is done")
        time.sleep(30)

    def __update_fw(self, request, cmd):
        localhost = request.getfixturevalue('localhost')
        duthost = request.getfixturevalue('duthost')

        hostname = duthost.hostname

        logger.info("Execute {} firmware task: cmd={}".format(self.get_name(), cmd))
        fw_task, fw_result = duthost.command(cmd, module_ignore_errors=True, module_async=True)

        logger.info("Wait for {} to go down".format(hostname))
        result = localhost.wait_for(host=hostname, port=22, state='stopped', timeout=3000, module_ignore_errors=True)

        if 'msg' in result.keys() and 'Timeout' in result['msg']:
            try:
                result_json = json.dumps(fw_result.get(timeout=0), indent=4)
                logger.error("{} firmware task failed:\n{}".format(self.get_name(), result_json))
            except:
                self._kill_task(duthost, cmd, fw_task, fw_result)

            pytest.fail(result['msg'])

        logger.info("Wait for {} to come back".format(hostname))
        localhost.wait_for(host=hostname, port=22, state='started', delay=10, timeout=300)

        logger.info("Wait until system is stable")
        wait_until(300, 30, 0, duthost.critical_services_fully_started)

        logger.info("Wait until system init is done")
        time.sleep(30)

    def install_fw(self, request, install_cmd, fw_path=None, fw_version=None):
        duthost = request.getfixturevalue('duthost')

        loganalyzer = LogAnalyzer(ansible_host=duthost, marker_prefix='fwutil')
        loganalyzer.expect_regex = [ FW_INSTALL_START_LOG ]
        # Temporarily disable install end verification due to loganalyzer issue
        #loganalyzer.expect_regex = [ FW_INSTALL_START_LOG, FW_INSTALL_SUCCESS_LOG ]

        with loganalyzer:
            self.__install_fw(request, install_cmd)

    def update_fw(self, request, update_cmd, fw_path=None, fw_version=None):
        duthost = request.getfixturevalue('duthost')

        loganalyzer = LogAnalyzer(ansible_host=duthost, marker_prefix='fwutil')
        loganalyzer.expect_regex = [ FW_UPDATE_START_LOG ]

        with loganalyzer:
            self.__update_fw(request, update_cmd)


def get_fw_status(duthost):
    """
    Parse output of 'fwutil show status' and return the data
    """
    cmd = 'fwutil show status'
    result = duthost.command(cmd)

    num_spaces = 2
    output_data = {}
    status_output = result['stdout']
    separators = re.split(r'\s{2,}', status_output.splitlines()[1])  # get separators
    output_lines = status_output.splitlines()[2:]

    for line in output_lines:
        data = []
        start = 0

        for sep in separators:
            curr_len = len(sep)
            data.append(line[start:start+curr_len].strip())
            start += curr_len + num_spaces

        component = data[2]
        output_data[component] = {
            'version': data[3],
            'desc': data[4]
        }

    return output_data


def set_default_boot(request):
    """
    Set current image as default
    """
    duthost = request.getfixturevalue('duthost')

    image_facts = duthost.image_facts()['ansible_facts']['ansible_image_facts']
    current_image = image_facts['current']

    logger.info("Set default SONiC boot: version={}".format(current_image))
    duthost.command("sonic_installer set_default {}".format(current_image))


def set_next_boot(request):
    """
    Set other available image as next.
    If there is no other available image, get it from user arguments
    """
    duthost = request.getfixturevalue('duthost')

    image_facts = duthost.image_facts()['ansible_facts']['ansible_image_facts']
    next_img = image_facts['next']

    if next_img == image_facts['current']:
        for img in image_facts['available']:
            if img != image_facts['current']:
                next_img = img
                break

    if next_img == image_facts['current']:
        logger.warning("Second SONiC image is not available: try to install")

        try:
            second_image_path = request.config.getoption('--second_image_path')
            remote_second_image_path = os.path.join('/home/admin', os.path.basename(second_image_path))

            hostname = duthost.hostname

            msg = "Copy SONiC image to {}: local_path={}, remote_path={}"
            logger.info(msg.format(hostname, second_image_path, remote_second_image_path))
            duthost.copy(src=second_image_path, dest=remote_second_image_path)

            logger.info("Install second SONiC image: path={}".format(remote_second_image_path))
            duthost.command("sonic_installer install -y {}".format(remote_second_image_path))
        except Exception as e:
            pytest.fail("Failed to install second SONiC image: not enough images for this test")

        return

    logger.info("Set next SONiC boot: version={}".format(next_img))
    duthost.command("sonic_installer set_next_boot {}".format(next_img))


def reboot_to_image(request, image_version):
    """
    Reboot device to the specified image
    """
    localhost = request.getfixturevalue('localhost')
    duthost = request.getfixturevalue('duthost')

    hostname = duthost.hostname
    reboot_cmd = 'reboot'

    logger.info("Set default SONiC image: version={}".format(image_version))
    duthost.command("sonic_installer set_default {}".format(image_version))

    logger.info("Reboot {}".format(hostname))
    reboot_task, reboot_result = duthost.command(reboot_cmd, module_async=True)

    try:
        logger.info("Wait for {} to go down".format(hostname))
        localhost.wait_for(host=hostname, port=22, state='stopped', delay=10, timeout=300)
    except Exception as e:
        logger.error("Wait for {} to go down failed: try to kill possible stuck reboot task".format(hostname))

        pid = duthost.command("pgrep -f '{}'".format(reboot_cmd))['stdout']
        duthost.command("kill -s SIGKILL {}".format(pid))

        logger.info("Result of task:\n{}".format(json.dumps(reboot_result.get(timeout=0), indent=4)))

        reboot_task.terminate()
        reboot_task.join()

        pytest.fail("Failed to reboot {}: {}".format(hostname, str(e)))

    logger.info("Wait for {} to come back".format(hostname))
    localhost.wait_for(host=hostname, port=22, state='started', delay=10, timeout=300)

    logger.info("Wait until system is stable")
    wait_until(300, 30, 0, duthost.critical_services_fully_started)

    logger.info("Wait until system init is done")
    time.sleep(30)

    image_facts = duthost.image_facts()['ansible_facts']['ansible_image_facts']

    if image_facts['current'] != image_version:
        pytest.fail("Reboot to image failed: version={}".format(image_version))


def generate_components_file(request, fw_path, fw_version):
    """
    Generate 'platform_components.json' file for positive test cases
    """
    platform_components = request.getfixturevalue('platform_components')
    component_object = request.getfixturevalue('component_object')
    duthost = request.getfixturevalue('duthost')

    hostname = duthost.hostname
    chassis_name = duthost.command("decode-syseeprom -p")['stdout'].strip('\0')
    comp_name = component_object.get_name()
    platform_type = duthost.facts['platform']

    json_data = {}
    json_data['chassis'] = {}
    json_data['chassis'][chassis_name] = {}
    json_data['chassis'][chassis_name]['component'] = {}

    for comp in platform_components:
        json_data['chassis'][chassis_name]['component'][comp] = {}

        if comp == comp_name:
            json_data['chassis'][chassis_name]['component'][comp]['firmware'] = fw_path
            json_data['chassis'][chassis_name]['component'][comp]['version'] = fw_version

    remote_comp_file_path = PLATFORM_COMP_PATH_TEMPLATE.format(platform_type)
    comp_file_path = "/tmp/platform_components.json"

    logger.info("Generate 'platform_components.json' on localhost: path={}".format(comp_file_path))
    with io.open(comp_file_path, 'wb') as comp_file:
        json.dump(json_data, comp_file, indent=4)
        logger.info("Generated 'platform_components.json':\n{}".format(json.dumps(json_data, indent=4)))

    msg = "Copy 'platform_components.json' to {}: local_path={}, remote_path={}"
    logger.info(msg.format(hostname, comp_file_path, remote_comp_file_path))
    duthost.copy(src=comp_file_path, dest=remote_comp_file_path)

    logger.info("Remove 'platform_components.json' from localhost: path={}".format(comp_file_path))
    os.remove(comp_file_path)


def generate_invalid_components_file(request, chassis_key, component_key, is_valid_comp_structure):
    """
    Generate invlid 'platform_components.json' file for negative test cases
    """
    duthost = request.getfixturevalue('duthost')
    platform_components = request.getfixturevalue('platform_components')

    hostname = duthost.hostname
    chassis_name = duthost.command("decode-syseeprom -p")['stdout'].strip('\0')
    platform_type = duthost.facts['platform']

    json_data = {}
    json_data[chassis_key] = {}
    json_data[chassis_key][chassis_name] = {}
    json_data[chassis_key][chassis_name][component_key] = {}

    for comp in platform_components:
        json_data[chassis_key][chassis_name][component_key][comp] = {}
        json_data[chassis_key][chassis_name][component_key][comp]['firmware'] = 'path/to/install'

        if not is_valid_comp_structure:
            json_data[chassis_key][chassis_name][component_key][comp]['version'] = {}
            json_data[chassis_key][chassis_name][component_key][comp]['version']['version'] = 'version/to/install'
        else:
            json_data[chassis_key][chassis_name][component_key][comp]['version'] = 'version/to/install'

    remote_comp_file_path = PLATFORM_COMP_PATH_TEMPLATE.format(platform_type)
    comp_file_path = "/tmp/invalid_platform_components.json"

    logger.info("Generate invalid 'platform_components.json' on localhost: path={}".format(comp_file_path))
    with io.open(comp_file_path, 'wb') as comp_file:
        json.dump(json_data, comp_file)
        logger.info("Generated invalid 'platform_components.json':\n{}".format(json.dumps(json_data, indent=4)))

    msg = "Copy invalid 'platform_components.json' to {}: local_path={}, remote_path={}"
    logger.info(msg.format(hostname, comp_file_path, remote_comp_file_path))
    duthost.copy(src=comp_file_path, dest=remote_comp_file_path)

    logger.info("Remove invalid 'platform_components.json' from localhost: path={}".format(comp_file_path))
    os.remove(comp_file_path)


def execute_invalid_command(duthost, cmd, expected_log):
    """
    Execute invalid update command and verify that errors occur
    """
    result = duthost.command(cmd, module_ignore_errors=True)
    if result['rc'] == SUCCESS_CODE:
        pytest.fail("Failed to get expected error code: rc={}".format(result['rc']))

    logger.info("Command:\n{}".format(cmd))
    logger.info("Output:\n{}".format(result['stdout'] if result['stdout'] else result['stderr']))

    if not re.search(expected_log, result['stderr']):
        if not re.search(expected_log, result['stdout']):
            pytest.fail("Failed to find expected error message: pattern={}".format(expected_log))


def install_firmware(request, fw_path, fw_version):
    component_object = request.getfixturevalue('component_object')
    duthost = request.getfixturevalue('duthost')

    hostname = duthost.hostname
    comp_name = component_object.get_name()
    remote_fw_path = os.path.join('/tmp', os.path.basename(fw_path))

    install_cmd_tmplt = "fwutil install chassis component {} fw -y {}"
    install_cmd = install_cmd_tmplt.format(comp_name, remote_fw_path)

    logger.info("Copy firmware to {}: local_path={}, remote_path={}".format(hostname, fw_path, remote_fw_path))
    duthost.copy(src=fw_path, dest=remote_fw_path)

    try:
        component_object.install_fw(request, install_cmd, fw_path, fw_version)
    finally:
        logger.info("Remove firmware from {}: remote_path={}".format(hostname, remote_fw_path))
        duthost.file(path=remote_fw_path, state='absent')

    fw_status = get_fw_status(duthost)
    comp_fw_status = fw_status[comp_name]
    logger.info("Parsed {} firmware status:\n{}".format(comp_name, json.dumps(comp_fw_status, indent=4)))

    logger.info("Verify {} firmware is updated: version={}".format(comp_name, fw_version))
    if not component_object.check_version(fw_version, comp_fw_status):
        pytest.fail("Version check failed: current({}) != expected({})".format(comp_fw_status['version'], fw_version))


def update_firmware(request, fw_path, fw_version, image_type):
    component_object = request.getfixturevalue('component_object')
    duthost = request.getfixturevalue('duthost')

    hostname = duthost.hostname
    comp_name = component_object.get_name()
    remote_fw_path = os.path.join('/tmp', os.path.basename(fw_path))

    if image_type not in [ IMAGE_TYPE_CURRENT, IMAGE_TYPE_NEXT ]:
        raise RuntimeError("Invalid image type is provided: {}".format(image_type))

    if image_type == IMAGE_TYPE_CURRENT:
        update_cmd_tmplt = "fwutil update chassis component {} fw -y --image=current"
        update_cmd = update_cmd_tmplt.format(comp_name)
    else:
        update_cmd_tmplt = "fwutil update chassis component {} fw -y --image=next"
        update_cmd = update_cmd_tmplt.format(comp_name)

    if image_type == IMAGE_TYPE_CURRENT:
        generate_components_file(request, remote_fw_path, fw_version)

        logger.info("Copy firmware to {}: local_path={}, remote_path={}".format(hostname, fw_path, remote_fw_path))
        duthost.copy(src=fw_path, dest=remote_fw_path)

    try:
        component_object.update_fw(request, update_cmd, fw_path, fw_version)
    finally:
        if image_type == IMAGE_TYPE_CURRENT:
            logger.info("Remove firmware from {}: remote_path={}".format(hostname, remote_fw_path))
            duthost.file(path=remote_fw_path, state='absent')

    fw_status = get_fw_status(duthost)
    comp_fw_status = fw_status[comp_name]
    logger.info("Parsed {} firmware status:\n{}".format(comp_name, json.dumps(comp_fw_status, indent=4)))

    logger.info("Verify {} firmware is updated: version={}".format(comp_name, fw_version))
    if not component_object.check_version(fw_version, comp_fw_status):
        pytest.fail("Version check failed: current({}) != expected({})".format(comp_fw_status['version'], fw_version))


def update_from_current_image(request):
    """
    Update firmware from current image
    """
    logger.info("Update firmware from current image")

    component_object = request.getfixturevalue('component_object')
    component_firmware = request.getfixturevalue('component_firmware')

    comp_name = component_object.get_name()

    if not component_firmware['is_latest_installed']:
        fw_path = component_firmware['latest_firmware']
        fw_version = component_firmware['latest_version']

        # install latest firmware update
        logger.info("Install latest {} firmware update: version={}, path={}".format(comp_name, fw_version, fw_path))
        update_firmware(request, fw_path, fw_version, IMAGE_TYPE_CURRENT)

    fw_path = component_firmware['previous_firmware']
    fw_version = component_firmware['previous_version']

    # install previous firmware update
    logger.info("Install previous {} firmware update: version={}, path={}".format(comp_name, fw_version, fw_path))
    update_firmware(request, fw_path, fw_version, IMAGE_TYPE_CURRENT)


def update_from_next_image(request):
    """
    Update firmware from next image
    """
    logger.info("Update firmware from next image")

    component_object = request.getfixturevalue('component_object')
    component_firmware = request.getfixturevalue('component_firmware')

    comp_name = component_object.get_name()

    set_next_boot(request)

    fw_path = component_firmware['latest_firmware']
    fw_version = component_firmware['latest_version']

    # install latest firmware update
    logger.info("Install latest {} firmware update: version={}, path={}".format(comp_name, fw_version, fw_path))
    update_firmware(request, fw_path, fw_version, IMAGE_TYPE_NEXT)

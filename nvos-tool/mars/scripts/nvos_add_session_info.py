"""
@copyright:
    Copyright (C) Mellanox Technologies Ltd. 2001-2017.  ALL RIGHTS RESERVED.

    This software product is a proprietary product of Mellanox Technologies
    Ltd. (the "Company") and all right, title, and interest in and to the
    software product, including all associated intellectual property rights,
    are and shall remain exclusively with the Company.

    This software product is governed by the End User License Agreement
    provided with the software product.

@date:
    Nov 23, 2022

@author:
    rmahameed@nvidia.com

@changed:

"""
import fnmatch
#######################################################################
# Global imports
#######################################################################
import os
import re

#######################################################################
# Local imports
#######################################################################
from mars_open_community.additional_info.session_add_info import SessionAddInfo
from mlxlib.common import trace
from mlxlib.remote.mlxrpc import RemoteRPC

logger = trace.set_logger()

SONIC_MGMT_WORKSPACE = '/root/mars/workspace/'


class NvosAddSessionInfo(SessionAddInfo):
    """
    Class to collect session info.
    Contains the conf_obj, extra_info dict if exist and session_info from the
    cmd if exists
    """

    def __init__(self, conf_obj, extra_info=None, session_info=None):
        """
        Constructor
        @param conf_obj:
            The configuration object, can get all the conf information from it.
        @param extra_info:
            Extra info dict from setup conf
        @param session_info:
            Info from the cmd info
        """
        SessionAddInfo.__init__(self, conf_obj, extra_info, session_info)

    def get_dynamic_info(self):
        """
        Implementation for getting the NVOS info for NVOS regression runs.
        Currently it will get the following:
            1. version
            2. platform
            3. asic

        @return:
            Tuple with return code and dictionary of additional info to add.
        """
        return self._get_info()

    def _get_info(self):
        print("Run NVOS AddSessionInfo.get_dynamic_info")
        try:
            res = {
                "dut_name": self.conf_obj.get_extra_info().get("dut_name"),
                "version": self._get_version_from_version_param("target_version"),
                "base_version": self._get_version_from_version_param("base_version"),
                "tarball": self._get_tarball_name(),
                "platform": self.conf_obj.get_extra_info().get("dut_hwsku"),
                "asic": self.conf_obj.get_extra_info().get("chip_type"),
                "topology": self.conf_obj.get_extra_info().get("topology"),
                "is_code_coverage_run": self.conf_obj.get_extra_info().get("code_coverage_run"),
                "is_sanitizer_run": self.conf_obj.get_extra_info().get("sanitizer_run"),
            }

            print("Regression Info:\n" + '\n'.join([f'{str(k)}: {str(v)}' for k, v in res.items()]))

            return 0, res
        except Exception as e:
            logger.error("Exception error: %s" % repr(e))
            return 1, {}

    def _get_tarball_name(self):
        tarball = self.conf_obj.get_extra_info().get("custom_tarball_name")
        if not tarball:
            return ''
        return tarball.replace('SONIC_CANONICAL-sonic-mgmt_', '').replace('.db.1.tgz', '').replace('.b.1.tgz', '')

    def _get_version_from_version_param(self, version_param_name) -> str:
        param_val = self.conf_obj.get_extra_info().get(version_param_name)
        if not param_val:
            return ''
        path = self._get_real_file_path(param_val)
        return self._get_formal_version_info(path) or self._get_dev_version_info(path)

    def _get_real_file_path(self, file_path: str) -> str:
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

    def _get_formal_version_info(self, version: str) -> str:
        """
        extract version number and build number from a given image url/path or just a version
        Examples:
            - /a/b/c/d/25.01.3001.bin -> '25.01.3001', ''
            - http://abc.com/a/b/c/25.01.3001-123.bin -> '25.01.3001', '123'
            - 25.01.3001 -> '25.01.3001', ''
        """
        if 'nvos_ci' in version:
            return 'nvos_ci-' + version.split('nvos_ci/')[1].split('/')[0]

        pattern = r'(\d+\.\d+\.\d+)(?:-(\d+))?(?:\.bin)?$'
        match = re.search(pattern, version)
        if match and match.group(0):
            version_num = match.group(1)
            bin_num = match.group(2) if match.group(2) else ''
            res = version_num + (f'-{bin_num}' if bin_num else '')
            return res
        return ''

    def _get_dev_version_info(self, version: str) -> str:
        pattern = r'nvos-(.*)(?:\.bin)?$'
        match = re.search(pattern, version)
        if match and match.group(0):
            version_name = match.group(1)
            return version_name.replace('.bin', '')
        return ''

    def _get_info_orig(self):
        print("Run NVOS AddSessionInfo.get_dynamic_info")
        machines_players = self.conf_obj.get_active_players()
        print("machine_players=" + str(machines_players))
        if type(machines_players) is list:
            machine = machines_players[0]
        else:
            machine = machines_players
        print("machine=" + str(machine))
        remote_workspace = SONIC_MGMT_WORKSPACE
        if not remote_workspace:
            logger.error("'sonic_mgmt_workspace' must be defined in extra_info section of setup conf")
            return (1, {})
        print("remote_workspace=" + str(remote_workspace))
        dut_name = self.conf_obj.get_extra_info().get("dut_name")
        topology = self.conf_obj.get_extra_info().get("topology")
        code_coverage_run = self.conf_obj.get_extra_info().get("code_coverage_run")
        sanitizer_run = self.conf_obj.get_extra_info().get("sanitizer_run")
        repo_name = self.conf_obj.get_extra_info().get("sonic_mgmt_repo_name")
        nvue_sswitch_user = os.getenv("NVU_SWITCH_USER")
        nvue_sswitch_pass = os.getenv("NVU_SWITCH_NEW_PASSWORD")
        cmd_system = "ansible -m command --extra-vars 'ansible_ssh_user={USER} ansible_ssh_pass={PASSWORD}' -i inventory {DUT_NAME}-{TOPOLOGY} -a 'nv show system -o json'"
        cmd_device = "ansible -m command --extra-vars 'ansible_ssh_user={USER} ansible_password={PASSWORD}' -i inventory {DUT_NAME}-{TOPOLOGY} -a 'nv show ib device -o json'"
        cmd_system = cmd_system.format(USER=nvue_sswitch_user, PASSWORD=nvue_sswitch_pass, DUT_NAME=dut_name,
                                       TOPOLOGY=topology)
        cmd_device = cmd_device.format(USER=nvue_sswitch_user, PASSWORD=nvue_sswitch_pass, DUT_NAME=dut_name,
                                       TOPOLOGY=topology)
        print("cmd=" + cmd_system)
        print("cmd=" + cmd_device)
        try:
            conn = RemoteRPC(machine)
            conn.import_module("os")
            conn.import_module("mlxlib.common.execute")

            conn.modules.os.chdir(os.path.join(remote_workspace, repo_name, "ansible"))
            conn.modules.os.environ["HOME"] = "/root"

            p_system = conn.modules.execute.run_process(cmd_system, shell=True)
            p_device = conn.modules.execute.run_process(cmd_device, shell=True)
            rc_system, system_output = conn.modules.execute.wait_process(p_system)

            rc_device, device_output = conn.modules.execute.wait_process(p_device)
            print("rc_system=" + str(rc_system))
            print("output_system=" + str(system_output))
            print("rc_device=" + str(rc_device))
            print("output_device" + str(device_output))

            if rc_system != 0:
                print("Execute command failed!")
                return 1, {}
            res = self._parse_system_version(system_output, device_output, topology, code_coverage_run, sanitizer_run)
            return 0, res
        except Exception as e:
            logger.error("Failed to execute command: %s" % cmd_system)
            logger.error("Exception error: %s" % repr(e))
            return 1, {}

    def _parse_system_version(self, show_system_output, show_device_output, topology, code_coverage_run, sanitizer_run):
        version = re.compile(r'"product-release": "(.*)"', re.IGNORECASE)
        platform_re = re.compile(r'"platform": "(.*)"', re.IGNORECASE)
        asic = re.compile(r'"type": "(.*)"', re.IGNORECASE)
        res = {
            "version": version.findall(show_system_output)[0] if version.search(show_system_output) else "",
            "platform": platform_re.findall(show_system_output)[0] if platform_re.search(show_system_output) else "",
            "topology": topology,
            "asic": asic.findall(show_device_output)[0] if asic.search(show_device_output) else "",
            "is_code_coverage_run": code_coverage_run,
            "is_sanitizer_run": sanitizer_run,
        }

        return res

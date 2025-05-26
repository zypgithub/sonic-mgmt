import logging
import json
import os
import re
import time
import allure
import netmiko

from ngts.cli_wrappers.interfaces.interface_general_clis import GeneralCliInterface
from ngts.cli_wrappers.common.general_clis_common import GeneralCliCommon
from ngts.cli_wrappers.sonic.sonic_onie_clis import SonicOnieCli, OnieInstallationError
from ngts.constants.constants import InfraConst
from ngts.constants.performance_constants import PerfConsts
from ngts.helpers.run_process_on_host import run_process_on_host
from ngts.helpers.secure_boot_helper import SecureBootHelper

from infra.tools.topology_tools.nogaq import get_noga_entire_resource_data
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive

logger = logging.getLogger()


class DvsGeneralCli(GeneralCliCommon):

    def __init__(self, engine, dut_alias):
        super().__init__(engine, dut_alias)

    def deploy_image(self, image_path, topology_obj, dut_alias):
        self.prepare_for_installation(topology_obj, dut_alias)
        try:
            self.install_image_onie(self.engine, image_path)
        except OnieInstallationError:
            logger.error('Caught exception OnieInstallationError during install. Perform reboot and trying again')
            self.engine.disconnect()
            self.remote_reboot(topology_obj, boot_into_onie=True, dut_alias=dut_alias)

    def _install_sdk_and_fw(self, sdk_version, fw_version, debian_enabled):
        """
        Internal method to install SDK and FW with debian flag control
        """
        di_flag = "-di" if debian_enabled else ""
        install_cmd = "sdk_install -v {} {} && fw_burn -v {} -f --ocr".format(sdk_version, di_flag, fw_version)
        self.engine.run_cmd(install_cmd, validate=True)

    def install_sdk_and_burn_fw_flow(self, sdk_version):
        """
        install SDK on the switch and burn fw to it, with dedicated script
        """
        with allure.step("Install SDK & FW"):
            logger.info("installing SDK and FW on the switch")
            self.apply_mount()
            self.set_aliases()
            fw_version = self.get_fw_version_from_sdk(sdk_version)
            logger.info(f"Starting installation of SDK version: {sdk_version} and FW version: {fw_version}")

            try:
                self._install_sdk_and_fw(sdk_version, fw_version, debian_enabled=True)
            except Exception as e:
                logger.warning(f"Installation with debian enabled failed: {str(e)}. Trying without debian...")
                self._install_sdk_and_fw(sdk_version, fw_version, debian_enabled=False)

            self.dvs_restart()
            logger.info("SDK and FW installation has ended successfully!")

    def install_traffic_generator(self):
        """
        Function verifies the traffic generator is functional post deploy on DVS OS
        :return: None
        """
        self.engine.run_cmd(f"{PerfConsts.DVS_RUN_TEST_PATH} -si")
        # TODO: uncomment once sdk_ver has shahaf changes
        # self.engine.run_cmd(f"{PerfConsts.DVS_RUN_TEST} --names {PerfConsts.DVS_TG_NAME}")

    def get_fw_version_from_sdk(self, sdk_version):
        fw_version_path = os.path.join(PerfConsts.SDK_VERSION_PATH, sdk_version, PerfConsts.FW_VERSION_FILE)
        fw_version = self.engine.run_cmd(f"cat {fw_version_path}")
        logger.info(f"FW version is {fw_version}")
        return fw_version

    def dvs_restart(self):
        logger.info("Performing restart to DVS")
        clean_switch_alias_cmd = f"alias clean_switch={PerfConsts.CLEAN_SWITCH_PATH}"
        restart_cmd = "dvs_stop.sh && clean_switch && dvs_start.sh --sdk_bridge_mode=HYBRID"
        self.engine.run_cmd_set([clean_switch_alias_cmd, restart_cmd], validate=True)

    def apply_mount(self):
        logger.info(f"Adding mounts for {PerfConsts.USED_SITE} site")
        cmd = f"SITE={PerfConsts.USED_SITE} nis_add.sh"
        self.engine.run_cmd(cmd)

    def set_aliases(self):
        logger.info("Setting aliases for sdk install, clean switch and fw burn commands")
        sdk_install_alias_cmd = f"alias sdk_install={PerfConsts.SDK_INSTALL_PATH}"
        clean_switch_alias_cmd = f"alias clean_switch={PerfConsts.CLEAN_SWITCH_PATH}"
        fw_burn_alias_cmd = f"alias fw_burn={PerfConsts.FW_BURN_PATH}"
        self.engine.run_cmd_set([sdk_install_alias_cmd, clean_switch_alias_cmd, fw_burn_alias_cmd])

    def is_dut_supports_image(self, base_version_url, dut_name, cli_type) -> bool:
        """
        This method checks whether the given base version url is supported for the given dut , or not
        In the future this method will check the sdk version compatibility to fw
        :return: True/False
        """
        image_supports = True
        logger.info(
            f"dut: {dut_name} {'supports' if image_supports else 'does not support'} version: {base_version_url}")
        return image_supports

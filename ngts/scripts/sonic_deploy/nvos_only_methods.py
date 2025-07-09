import logging
import os
import shutil
import time
import copy
import yaml

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.constants.constants import LinuxConsts, SerialLoggerConst
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.nvos_tools.infra.CurlTool import CurlTool
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.SecureBootTool import SecureBootTool
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.conftest import ProxySshEngine
from ngts.tests_nvos.general.post_upgrade_switch.constants import UPGRADE_STATUS_SUCCESS_MSG, UPGRADE_STATUS_FAIL_MSG, \
    UPGRADE_STATUS_FILE_PATH, InstallSteps
from ngts.tests_nvos.general.post_upgrade_switch.install_steps_timer import InstallStepsTimer
from ngts.tests_nvos.general.security.bmc.bmc_creds.constants import BmcUsers
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_config_utils import clear_conf
from ngts.tests_nvos.platform.test_platform_firmware import validate_firmware_keys, validate_firmware_components

logger = logging.getLogger()


class NvosInstallationSteps:

    @staticmethod
    def pre_installation_steps(setup_info, base_version='', target_version=''):
        assert target_version, 'Argument "target_version" must be provided for installing NVOS'

        with allure.step('Initialize timer'):
            InstallStepsTimer.initialize_timer()

    @staticmethod
    def post_installation_steps(topology_obj, workspace_path, setup_info, serial_log_analyzer,
                                root_dir, base_version='', target_version='', verify_secure_boot: bool = True):
        """
        Post-installation steps for NVOS NOS
        :return:
        """
        assert target_version, 'Argument "target_version" must have been provided for installing NVOS'

        with allure.step('Replace minigraph_facts.py replaced in ansible/library'):
            source_py = os.path.join(workspace_path, "sonic-mgmt/sonic-tool/sonic_ngts/scripts/minigraph_facts.py")
            destination_path = os.path.join(workspace_path, "sonic-mgmt/ansible/library/minigraph_facts.py")
            try:
                shutil.os.system('sudo cp "{source}" "{destination}"'.format(source=source_py,
                                                                             destination=destination_path))
                logger.info("minigraph_facts.py was replaced in ansible/library")
                logger.info("source path: " + source_py)
                logger.info("destination path: " + destination_path)
            except BaseException:
                logger.warning("Failed to replace minigraph_facts.py in ansible path. Community tests will fail.")

        with allure.step('Initialize engine and device objects'):
            cli_obj: NvueGeneralCli = setup_info['duts'][0]['cli_obj']
            dut_device = cli_obj.device
            dut_engine = cli_obj.engine
            TestToolkit.is_eth_dut(dut_device)  # initialize this field in TestToolkit global object

            with allure.step("Test output of nv show platform firmware"):
                platform = Platform()
                firmware_items = dut_device.constants.firmware
                validate_firmware_keys(platform, firmware_items, dut_engine)
                validate_firmware_components(platform, firmware_items, dut_engine)

        if dut_device.has_bmc:
            with allure.step('reset password of bmc root user'):
                CurlTool(PlatformConsts.BMC_INTERNAL_IP, BmcUsers.admin.username, TpmTool(dut_engine).get_bmc_admin_password_from_tpm()).change_root_password(dut_engine=dut_engine)

        if verify_secure_boot:
            with allure.step('Verify Secure-Boot is enabled'):
                assert SecureBootTool.is_secure_boot_enabled(dut_engine), "Secure-Boot is expected to be enabled, but it's disabled!"

        if base_version:
            with allure.step('========== NVOS - Upgrade With Saved Configuration Flow =========='):
                # if deploy_and_upgrade was invoked also with base_version, meaning that base_version is the version that
                #   was installed, and now we want to test the scenario where we set pre-defined configuration,
                #   apply & save it, and upgrade to the given target_version, which is the one that will be used for testing
                with serial_log_analyzer.stage(SerialLoggerConst.UPGRADE_STAGE):
                    NvosInstallationSteps.upgrade_with_saved_config_flow(topology_obj, dut_engine, dut_device,
                                                                         root_dir, base_version, target_version)
        else:
            logger.info('NVOS: Argument "base-version" was not given. therefore not running the upgrade with saved '
                        'configuration scenario')

        with allure.step('show intervals of installation flow steps'):
            allure.attach('install flow intervals', InstallStepsTimer.analyze_saved_timestamps())

        with allure.step('Set base configuration for tests after the install phase'):
            dut_device.clear_config(dut_engine=dut_engine, default_yml_path=None, root_dir=root_dir)
            try:
                with allure.step('Set timezone using timedatectl command'):
                    logger.info("Configuring same time zone for dut and local engine to {}"
                                .format(LinuxConsts.JERUSALEM_TIMEZONE))
                    os.popen('sudo timedatectl set-timezone {}'.format(LinuxConsts.JERUSALEM_TIMEZONE))
            except BaseException as ex:
                logger.warning('Failed to configure timezone')

        logger.info('========== NVOS - Post installation steps Done ==========')

    @staticmethod
    def upgrade_with_saved_config_flow(topology_obj, dut_engine, dut_device, root_dir, base_version='',
                                       target_version=''):
        with allure.step('Upgrade to target version with saved configuration'):
            NvosInstallationSteps.upgrade_version_with_saved_configuration(dut_engine, dut_device,
                                                                           topology_obj, target_version,
                                                                           base_version, root_dir)
        with allure.step('Show system and firmware version after upgrade'):
            system = System()
            platform = Platform()
            system.version.show(dut_engine=dut_engine)
            platform.firmware.show(dut_engine=dut_engine)

    @staticmethod
    def upgrade_version_with_saved_configuration(dut_engine: ProxySshEngine, dut_device: BaseDevice,
                                                 topology_obj, target_version_path: str, base_version: str, root_dir):
        with allure.step('Strings preparation'):
            config_file_path, config_filename = dut_device.get_test_config_file_by_version(base_version)
            system = System()
            sonic_mgmt_engine = topology_obj.players['sonic-mgmt']['engine']
            scp_host_creds = f'{sonic_mgmt_engine.username}:{sonic_mgmt_engine.password}@{sonic_mgmt_engine.ip}'
            if target_version_path.startswith('http'):
                target_version_path = f'/auto/{target_version_path.split("/auto/")[1]}'
            bin_filename = target_version_path.split('/')[-1]

        with allure.step('Apply and save pre-defined configuration'):
            NvosInstallationSteps.fetch_apply_save_config(config_filename, config_file_path, dut_engine,
                                                          scp_host_creds, system, dut_device)

        with allure.step('Upgrade to target version'):
            NvosInstallationSteps.upgrade_to_target_version(bin_filename, dut_engine, dut_device, scp_host_creds,
                                                            system,
                                                            target_version_path, topology_obj)

        with allure.step('Wait until switch is up'):
            dut_engine.disconnect()  # force engines.dut to reconnect
            dut_engine.password = dut_device.get_default_password_by_version(target_version_path)  # after upgrade flow switch has new default password

        with allure.step('Verify configuration after upgrade'):
            NvosInstallationSteps.verify_config_after_upgrade(config_file_path, dut_engine)

        with allure.step('Clear tested configuration for the tests'):
            dut_device.clear_config(dut_engine=dut_engine, default_yml_path=None, root_dir=root_dir)
            NvueGeneralCli.show_config(dut_engine)

        with allure.step('Clear fetched files for the tests'):
            system = System()
            dut_engine.disconnect()  # force engines.dut to reconnect
            # in the cleanup we unset interface which sets back default ACL rules (to mgmt ports)
            # in this case, ongoing sessions may get stuck/interrupted. thus, wait few seconds after that configuration
            # more info in redmine: #4132303
            logging.info('sleep after applied default ACL rules in cleanup')
            time.sleep(10)

            with allure.step('Delete fetched image file'):
                system.image.files.delete_all_existing_files(engine=dut_engine)
            with allure.step('Delete config files'):
                system.config.files.delete_all_existing_files(engine=dut_engine)
            with allure.step('Uninstall older version'):
                system.image.action_uninstall(engine=dut_engine, verify_res=False)

    @staticmethod
    def verify_config_after_upgrade(config_file_path, dut_engine):
        dicts_diff = None
        with allure.step('Get actual configuration'):
            actual_config = OutputParsingTool.parse_json_str_to_dictionary(
                NvueGeneralCli.show_config(dut_engine)).get_returned_value()
            actual_config = [item for item in actual_config if 'set' in item][0]
        with allure.step('Get expected configuration from yml file'):
            # safe load my yml file - [{"header":...}, {"set":...}]
            with open(config_file_path, 'r') as file:
                expected_config = yaml.safe_load(file)
                expected_config = [item for item in expected_config if 'set' in item][0]
            normalized_expected_config = NvosInstallationSteps.normalize_config(expected_config)
        with allure.step('Check differences between expected and actual configurations'):
            logger.info(f'config before upgrade (expected):\n{normalized_expected_config}')
            logger.info(f'config after upgrade (actual):\n{actual_config}')
            exceptions = {"secret": "*", "password": "*", "readonly-community": None}
            dicts_diff = ValidationTool.get_dictionaries_diff(normalized_expected_config, actual_config, exceptions=exceptions)
            logger.info(f'configs diff:\n{dicts_diff}')
            upgrade_status_file_path_dut = UPGRADE_STATUS_FILE_PATH
            if not dicts_diff:
                dut_engine.run_cmd(f'echo "{UPGRADE_STATUS_SUCCESS_MSG}" > {upgrade_status_file_path_dut}')
            else:
                err = f'{UPGRADE_STATUS_FAIL_MSG}\ndiff:\n{dicts_diff}'
                logger.info(err)
                dut_engine.run_cmd(f'echo "{err}" > {upgrade_status_file_path_dut}')
        return dicts_diff

    @staticmethod
    def upgrade_to_target_version(bin_filename, dut_engine, dut_device, scp_host_creds, system, target_version_path,
                                  topology_obj, param_value=''):
        image_scp_url = f'scp://{scp_host_creds}{target_version_path}'
        system.image.action_fetch(image_scp_url, base_url='', engine=dut_engine, device=dut_device)
        # use new default password for recovery after upgrade
        recovery_engine = LinuxSshEngine(dut_engine.ip, dut_engine.username,
                                         dut_device.get_default_password_by_version(target_version_path))
        InstallStepsTimer.add_timestamp(InstallSteps.UPGRADE_CMD)
        system.image.files.file_name[bin_filename].action_file_install_with_reboot(engine=dut_engine, device=dut_device,
                                                                                   recovery_engine=recovery_engine,
                                                                                   topology_obj=topology_obj,
                                                                                   param_value=param_value, track_boot_intervals=True)

    @staticmethod
    def fetch_apply_save_config(config_filename, config_file_path, dut_engine, scp_host_creds, system, dut_device=None,
                                verify_result=False):
        conf_scp_url = f'scp://{scp_host_creds}{config_file_path}'
        result = system.config.action_fetch(conf_scp_url, base_url='', engine=dut_engine, device=dut_device)
        if verify_result:
            result.verify_result()
        NvueGeneralCli.replace_config(engine=dut_engine, file=config_filename, verify_execution=verify_result)
        NvueGeneralCli.apply_config(engine=dut_engine, option='-y', verify_execution=verify_result)
        NvueGeneralCli.save_config(engine=dut_engine)
        time.sleep(30)  # due to bug SW #4262437

    @staticmethod
    def wait_for_nvos_to_become_functional(dut_engine):
        """
        Waiting for NVOS to complete the init and become functional after the installation
        :return: Bool
        """
        try:
            DutUtilsTool.wait_for_nvos_to_become_functional(dut_engine).verify_result()
            return True
        except Exception as err:
            return False

    @staticmethod
    def deploy_image(cli, topology_obj, setup_name, platform_params, base_image_url, deploy_type,
                     apply_base_config, reboot_after_install, fw_pkg_path, target_image_url='', dut_alias=None):
        """
        This method will deploy NVOS image on the dut.
        :param topology_obj: topology object
        :param setup_name: setup_name from NOGA
        :param platform_params: platform_params
        :param image_url: path to sonic version to be installed
        :param deploy_type: deploy_type
        :param apply_base_config: apply_base_config
        :param reboot_after_install: reboot_after_install
        :param cli: NVUE cli object
        :param dut_alias: dut_alias
        :return: raise assertion error in case of script failure
        """
        with allure.step('Decide which version to install'):
            assert target_image_url, 'Argument "target_version" must be provided for installing NVOS'
            # In here, image_url is url to provided base_version ; target_image_url is url to provided target_version.
            # For NVOS, target version is always the one to install, unless base version is provided, and in that
            #   situation we'll install the base version with ONIE, and eventually upgrade to target version
            #   using upgrade CLI.
            logger.info(f'base_image_url: {base_image_url}')
            logger.info(f'target_image_url: {target_image_url}')
            image_to_install_in_onie_url = base_image_url if base_image_url else target_image_url
            logger.info(f'URL of image to install in ONIE: {image_to_install_in_onie_url}')

        with allure.step(f'Deploy {image_to_install_in_onie_url} image on the dut'):
            cli.deploy_image(topology_obj=topology_obj, image_path=image_to_install_in_onie_url,
                             apply_base_config=apply_base_config, setup_name=setup_name,
                             platform_params=platform_params, deploy_type=deploy_type,
                             reboot_after_install=reboot_after_install, fw_pkg_path=fw_pkg_path, set_timezone=None,
                             dut_alias=dut_alias)

    @staticmethod
    def normalize_config(old_config: dict):
        """
        Normalize the config to match the format of the config after upgrade
        :param config: config
        :return: normalized config
        """
        normalized_config = copy.deepcopy(old_config)

        tacacs_path_old = normalized_config["set"]["system"]["aaa"]["tacacs"]
        if "hostname" in tacacs_path_old:
            tacacs_path_old["server"] = tacacs_path_old.pop("hostname")
            for _, config in tacacs_path_old["server"].items():
                if "auth-type" in config:
                    config["auth-mode"] = config.pop("auth-type")

        return normalized_config

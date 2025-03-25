import logging
import os
import time
from collections import namedtuple
from typing import List, Dict

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.linux_tools.linux_tools import scp_file
from ngts.nvos_constants.constants_nvos import MultiPlanarConsts, PlatformConsts, HealthConsts, \
    ActionConsts, ChassisLocationConsts, CableCartridgeConsts
from ngts.nvos_constants.constants_nvos import (NvosConst, DatabaseConst, IbConsts, StatsConsts, FansConsts,
                                                DocumentsConsts)
from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ExpectedString
from ngts.nvos_tools.system.Spdm import SPDMComponents
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.tests_nvos.constants import MINUTE
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_config_utils import clear_conf
from ngts.tools.test_utils.nvos_general_utils import get_version_info
from ngts.nvos_tools.infra.FilesTool import FilesTool

logger = logging.getLogger()


class IbSwitch(BaseSwitch):
    ErotFirmwareImagesTestConsts = namedtuple('ErotFirmwareImagesTestConsts',
                                              ('previous_image_path', 'current_image_path', 'version_names'))

    def __init__(self, asic_amount, switch_type=NvosConst.IB_SWITCH_TYPE, switch_class=NvosConst.IB_SWITCH_TYPE):
        super().__init__(switch_type=switch_type, asic_amount=asic_amount, switch_class=switch_class)
        self.documents_path = None
        self.documents_files = None
        self._init_sensors_dict()
        self._init_gnmi_consts()
        self.open_api_port = "443"
        self.default_password = os.environ["NVU_SWITCH_NEW_PASSWORD"]
        self.default_username = os.environ["NVU_SWITCH_USER"]
        self.prev_default_password = os.environ["NVU_SWITCH_PASSWORD"]
        self._init_ib_speeds()
        self._init_eth0_speeds()
        self._init_eth0_duplex()
        self.init_documents_consts()
        self.init_cli_coverage_prop("nvos")
        self._init_interface_lists()

    def get_default_password_by_version(self, version: str):
        version_num, _ = get_version_info(version)
        if self.prev_default_password and version_num:
            logging.info(f'detected version: {version_num}')
            if version_num.startswith('25.01.') and int(version_num.split('.')[-1]) <= 3000:
                logging.info('using prev default password')
                return self.prev_default_password
        logging.info('using regular default password')
        return self.default_password

    def get_voltage_sensors(self, dut_engine=None):
        return Tools.FilesTool.get_subfiles_list(engine=dut_engine, folder_path=PlatformConsts.VOLTAGE_FILES_PATH,
                                                 subfiles_pattern=PlatformConsts.VOLTAGE_FILES_PATTERN)

    def get_default_nvue_config(self, dut_engine=None):
        default_conf = NvosConst.DEFAULT_CONFIG
        default_conf["interface"] = NvosConst.DEFAULT_NVOS_IFACE_CONFIG
        return default_conf

    def show_setup_versions(self, dut_engine: LinuxSshEngine = None):
        outputs = {
            'system version': dut_engine.run_cmd('nv show system version'),
            'platform firmware': dut_engine.run_cmd('nv show platform firmware'),
            'fae platform firmware': dut_engine.run_cmd('nv show fae platform firmware'),
        }
        res = [f'{title.upper()}:\n{output}\n' for title, output in outputs.items()]
        return '\n'.join(res)

    def verify_ib_ports_state(self, dut_engine, expected_port_state):
        logging.info(f"number of ports: {self.ib_ports_num}")
        output_dict = OutputParsingTool.parse_json_str_to_dictionary(
            Port.show_interface(dut_engine, '--applied')).returned_value
        err_msg = ""
        for key, value in output_dict.items():
            if value[IbInterfaceConsts.TYPE] == IbInterfaceConsts.IB_PORT_TYPE and expected_port_state not in \
                    value[IbInterfaceConsts.LINK][IbInterfaceConsts.DHCP_STATE].keys():
                err_msg += "{} state is {}".format(key,
                                                   value[IbInterfaceConsts.LINK][IbInterfaceConsts.DHCP_STATE].keys())

        return ResultObj(False, err_msg) if err_msg else ResultObj(True, "", "")

    def clear_config(self, dut_engine, markers=None, default_yml_path=None, root_dir=""):
        clear_conf(dut_engine, self, default_yml_path, root_dir)

    def handle_exception(self, dut_engine):
        try:
            logging.info("Handle ib exception")
            dut_engine.run_cmd("docker ps")
            dut_engine.run_cmd("systemctl --type=service")
            dut_engine.run_cmd("nv show system version")
        except BaseException as err:
            logging.warning(err)

    def get_default_config_yml(self, engine, root_dir):
        try:
            with allure.step("Get default yml file"):
                default_config_name = NvosConst.DEFAULT_CONFIG_FILE_NAME
                path_to_config_ymls = f"{root_dir}/{NvosConst.DEFAULT_CONFIG_PATH}"

                logging.info(f"eth0_ip:{TestToolkit.dut_eth0_ip}")
                logging.info(f"switch_class:{self.switch_class}")

                for file_name in os.listdir(path_to_config_ymls):
                    if self.switch_class in file_name:
                        default_config_name = file_name
                    if TestToolkit.dut_eth0_ip and TestToolkit.dut_eth0_ip in file_name:
                        default_config_name = file_name
                        break

            yml_file_path = f"{NvosConst.PATH_TO_CONFIG_FILES_ON_DUT}/{default_config_name}"

            if FilesTool.file_exists(engine, yml_file_path):
                logging.info(f"Config file {yml_file_path} already exists on the switch")
            else:
                with allure.step(f"Copy {default_config_name} to the switch"):
                    scp_file(player=engine,
                             src_path=f"{path_to_config_ymls}{default_config_name}",
                             dst_path=NvosConst.PATH_TO_TMP_ON_DUT,
                             download_from_remote=False, print_output=True)

                tmp_file_path = f"{NvosConst.PATH_TO_TMP_ON_DUT}/{default_config_name}"

                with allure.step(f"Copy {tmp_file_path} to {yml_file_path}"):
                    engine.run_cmd(f"sudo cp {tmp_file_path} {yml_file_path}")

            logging.info(f"Using default yml file: {yml_file_path}")
            return yml_file_path

        except BaseException as ex:
            print(f"SCP command failed - error output: {ex}")
            return ""

    def _init_ib_speeds(self):
        self.invalid_ib_speeds = {'qdr': '40G'}
        self.supported_ib_speeds = ('hdr', 'edr', 'fdr', 'sdr', 'ndr')

    def _init_eth0_speeds(self):
        self.supported_eth0_speeds = ['100M', '1G']

    def _init_eth0_duplex(self):
        self.supported_eth0_duplex = ['half', 'full']

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2",
                         "FAN5/1", "FAN5/2", "FAN6/1", "FAN6/2"]

    def _init_led_list(self):
        self.led_list = ['FAN1', 'FAN2', 'FAN3', 'FAN4', 'FAN5', 'FAN6', "PSU_STATUS", "STATUS", "UID"]

    def _init_system_lists(self):
        self.user_fields = ['admin', 'monitor']

    def _init_security_lists(self):
        super()._init_security_lists()
        self.kex_algorithms = ['curve25519-sha256', 'curve25519-sha256@libssh.org', 'diffie-hellman-group16-sha512',
                               'diffie-hellman-group18-sha512', 'diffie-hellman-group14-sha256']
        self.aaa_cleanup_cmds = ['nv config detach', 'nv unset system aaa authentication order',
                                 'nv unset system aaa authentication failthrough', 'nv config apply -y']

    def _init_password_hardening_lists(self):
        self.aaa_admin_role = 'admin'
        self.aaa_monitor_role = 'monitor'
        self.local_test_users = [{AaaConsts.USERNAME: AaaConsts.LOCALADMIN,
                                  AaaConsts.PASSWORD: AaaConsts.STRONG_PASSWORD,
                                  AaaConsts.ROLE: self.aaa_admin_role},
                                 {AaaConsts.USERNAME: AaaConsts.LOCALMONITOR,
                                  AaaConsts.PASSWORD: AaaConsts.STRONG_PASSWORD,
                                  AaaConsts.ROLE: self.aaa_monitor_role}]

    def _init_available_databases(self):
        super()._init_available_databases()
        self.available_databases.update(
            {DatabaseConst.APPL_DB_NAME: DatabaseConst.APPL_DB_ID,
             DatabaseConst.ASIC_DB_NAME: DatabaseConst.ASIC_DB_ID,
             # DatabaseConst.COUNTERS_DB_NAME: DatabaseConst.COUNTERS_DB_ID, - disabled for now
             DatabaseConst.CONFIG_DB_NAME: DatabaseConst.CONFIG_DB_ID,
             DatabaseConst.STATE_DB_NAME: DatabaseConst.STATE_DB_ID
             })

        self.available_tables['database'] = {
            DatabaseConst.APPL_DB_ID:
            {"ALIAS_PORT_MAP": self.get_ib_ports_num()},
            DatabaseConst.ASIC_DB_ID:
            {"ASIC_STATE:SAI_OBJECT_TYPE_PORT": self.get_ib_ports_num() + 1,
             "ASIC_STATE:SAI_OBJECT_TYPE_SWITCH": 1,
             "LANES": 1,
             "VIDCOUNTER": 1,
             "RIDTOVID": 1,
             "HIDDEN": 1,
             "COLDVIDS": 1},
            DatabaseConst.COUNTERS_DB_ID:
            {"COUNTERS_PORT_NAME_MAP": 1,
             "COUNTERS:oid": self.get_ib_ports_num()},
            DatabaseConst.CONFIG_DB_ID:
            {"IB_PORT": self.get_ib_ports_num(),
             "FEATURE": 11,
             "CONFIG_DB_INITIALIZED": 1,
             "DEVICE_METADATA": 1,
             "VERSIONS": 1,
             "KDUMP": 1}
        }
        self.available_tables['database'][DatabaseConst.ASIC_DB_ID].update(
            {"ASIC_STATE:SAI_OBJECT_TYPE_PORT": self.get_ib_ports_num() / 2,
             "ASIC_STATE:SAI_OBJECT_TYPE_SWITCH": 0,
             "LANES": 0,
             "VIDCOUNTER": 0,
             "RIDTOVID": 0,
             "HIDDEN": 0,
             "COLDVIDS": 0})

        self.available_tables['database'][DatabaseConst.ASIC_DB_ID].update(
            {"ASIC_STATE:SAI_OBJECT_TYPE_PORT": self.get_ib_ports_num(),
             "ASIC_STATE:SAI_OBJECT_TYPE_SWITCH": 0,
             "LANES": 0,
             "VIDCOUNTER": 0,
             "RIDTOVID": 0,
             "HIDDEN": 0,
             "COLDVIDS": 0})

        self.available_tables_per_asic = {
            DatabaseConst.APPL_DB_ID:
                {"ALIAS_PORT_MAP": self.get_ib_ports_num()},
            DatabaseConst.ASIC_DB_ID:
                {"ASIC_STATE:SAI_OBJECT_TYPE_PORT": self.get_ib_ports_num() / 2 + 1,
                 "LANES": 1,
                 "VIDCOUNTER": 1,
                 "RIDTOVID": 1,
                 "HIDDEN": 1,
                 "COLDVIDS": 1},
            DatabaseConst.COUNTERS_DB_ID:
                {"COUNTERS_PORT_NAME_MAP": 1,
                 "COUNTERS:oid": self.get_ib_ports_num() / 2},
            DatabaseConst.CONFIG_DB_ID:
                {"IB_PORT": self.get_ib_ports_num() / 2,
                 "FEATURE": 6,
                 "CONFIG_DB_INITIALIZED": 1,
                 "DEVICE_METADATA": 1,
                 "VERSIONS": 0,
                 "KDUMP": 0}
        }
        self.available_tables.update({'database0': self.available_tables_per_asic})

    def _init_services(self):
        super()._init_services()
        self.available_services.extend((
            'docker.service', 'database.service', 'hw-management.service', 'config-setup.service',
            'updategraph.service', 'ntp.service', 'hostname-config.service', 'ntp-config.service',
            'rsyslog-config.service', 'procdockerstatsd.service',
            'configmgrd.service', 'countermgrd.service', 'portsyncmgrd.service'
        ))
        for deamon in NvosConst.DOCKER_PER_ASIC_LIST:
            for asic_num in range(0, self.asic_amount):
                self.available_services.append('{deamon}@{asic_num}.service'.format(deamon=deamon, asic_num=asic_num))

    def _init_dependent_services(self):
        super()._init_dependent_services()
        self.dependent_services.append(NvosConst.SYM_MGR_SERVICES)

    def _init_gnmi_consts(self):
        self.version_xpath = 'platform-general/versions/state/nos-version'
        self.bios_xpath = "platform-general/versions/state/fw-version-bios"
        self.cpld1_xpath = 'platform-general/versions/fw-versions-cpld/fw-version-cpld[id=1]/state/fw-version'
        self.cpld2_xpath = 'platform-general/versions/fw-versions-cpld/fw-version-cpld[id=1]/state/fw-version'
        self.cpld3_xpath = 'platform-general/versions/fw-versions-cpld/fw-version-cpld[id=3]/state/fw-version'
        self.cpld4_xpath = 'platform-general/versions/fw-versions-cpld/fw-version-cpld[id=4]/state/fw-version'
        self.components_gnmi_xpath = [self.bios_xpath, self.cpld1_xpath, self.cpld2_xpath,
                                      self.cpld3_xpath, self.cpld4_xpath]

    def _init_dockers(self):
        super()._init_dockers()
        self.available_dockers.extend(('database', 'gnmi-server'))  # TODO: Add lldp container check
        for deamon in NvosConst.DOCKER_PER_ASIC_LIST:
            for asic_num in range(0, self.asic_amount):
                self.available_dockers.append("{deamon}{asic_num}".format(deamon=deamon, asic_num=asic_num))

    def _init_constants(self):
        super()._init_constants()
        self.full_version_pattern = r'^nvos-\d{2}\.\d{2}\.\d{4}(-\d{3})?$'
        self.version_number_pattern = r'\d{2}\.\d{2}\.\d{4}'
        self.health_monitor_config_file_path = ""
        self.platform_file_path = ""
        self.primary_asic = f"{IbConsts.DEVICE_ASIC_PREFIX}1"
        self.primary_swid = f"{IbConsts.SWID}0"
        self.primary_ipoib_interface = IbConsts.IPOIB_INT.format(self.asic_amount - 1)
        self.multi_asic_system = False
        self.multi_planar = False
        self.login_pattern = NvosConst.INSTALL_SUCCESS_PATTERN
        self.install_patterns = {self.login_pattern: 0}
        self.install_success_patterns = list(self.install_patterns.keys())
        self.mst_dev_name = '/dev/mst/mt54002_pciconf0'  # TODO update
        self.category_list = ['temperature', 'cpu', 'disk', 'power', 'fan', 'mgmt-interface', 'voltage']
        self.category_disk_interval_default = '30'
        self.system_profile_default_values = ['enabled', '2048', 'disabled', 'disabled', '1']
        self.fw_versions_json_file_path = "/auto/sw_system_project/NVOS_INFRA/verification_files/platform_components/crocodile_versions.json"
        self.erot_fw_image_info = self.ErotFirmwareImagesTestConsts(
            current_image_path='auto/sw_system_release/erot/juliet/01.03.0202.000/sign/n04/dev/cec1736-ecfw-01.03.0202.0000-n04-dev-initial.bin',
            previous_image_path='auto/sw_system_release/erot/juliet/01.03.0183.000/sign/n04/dev/cec1736-ecfw-01.03.0183.0000-n04-dev-initial.bin',
            version_names={'cec1736-ecfw-01.03.0196.0001-n04-dev-initial.fwpkg': '01.03.0196.0001_n04',
                           'cec1736-ecfw-01.03.0202.0000-n04-dev-initial.fwpkg': '01.03.0202.0000_n04'})
        self.category_default_disabled_dict = {
            StatsConsts.HISTORY_DURATION: StatsConsts.HISTORY_DURATION_DEFAULT,
            StatsConsts.INTERVAL: StatsConsts.INTERVAL_DEFAULT,
            StatsConsts.STATE: StatsConsts.State.DISABLED.value
        }
        self.category_default_dict = {
            StatsConsts.HISTORY_DURATION: StatsConsts.HISTORY_DURATION_DEFAULT,
            StatsConsts.INTERVAL: StatsConsts.INTERVAL_DEFAULT,
            StatsConsts.STATE: StatsConsts.STATE_DEFAULT
        }
        self.category_disk_default_dict = {
            StatsConsts.HISTORY_DURATION: StatsConsts.HISTORY_DURATION_DEFAULT,
            StatsConsts.INTERVAL: self.category_disk_interval_default,
            StatsConsts.STATE: StatsConsts.STATE_DEFAULT
        }
        self.category_disk_default_disable_dict = {
            StatsConsts.HISTORY_DURATION: StatsConsts.HISTORY_DURATION_DEFAULT,
            StatsConsts.INTERVAL: self.category_disk_interval_default,
            StatsConsts.STATE: StatsConsts.State.DISABLED.value
        }
        self.category_disabled_dict = {
            self.category_list[0]: self.category_default_disabled_dict,
            self.category_list[1]: self.category_default_disabled_dict,
            self.category_list[2]: self.category_disk_default_disable_dict,
            self.category_list[3]: self.category_default_disabled_dict,
            self.category_list[4]: self.category_default_disabled_dict,
            self.category_list[5]: self.category_default_disabled_dict,
            self.category_list[6]: self.category_default_disabled_dict
        }
        self.category_list_default_dict = {
            self.category_list[0]: self.category_default_dict,
            self.category_list[1]: self.category_default_dict,
            self.category_list[2]: self.category_disk_default_dict,
            self.category_list[3]: self.category_default_dict,
            self.category_list[4]: self.category_default_dict,
            self.category_list[5]: self.category_default_dict,
            self.category_list[6]: self.category_default_dict
        }

        self.asic0 = 'asic0'
        self.asic1 = 'asic1'
        self.counters_db_name = 'COUNTERS_DB'

        self.voltage_sensors = ["PMIC-1-12V-ASIC-VCORE-In-1", "PMIC-1-ASIC-VCORE-Out-1", "PMIC-2-12V-ASIC-HVDD-DVDD-In-1",
                                "PMIC-2-ASIC-DVDD-WEST-Out-2", "PMIC-2-ASIC-HVDD-WEST-Out-1", "PMIC-3-12V-ASIC-HVDD-DVDD-In-1",
                                "PMIC-3-ASIC-DVDD-EAST-Out-2", "PMIC-3-ASIC-HVDD-EAST-Out-1", "PMIC-4-3.3V-OSFP-P01-P08-Out-1",
                                "PMIC-4-3.3V-OSFP-P09-P16-Out-2", "PMIC-4-12V-PORTS-WEST-In-1", "PMIC-5-3.3V-OSFP-P17-P24-Out-1",
                                "PMIC-5-3.3V-OSFP-P25-P32-Out-2", "PMIC-5-12V-PORTS-EAST-In-1", "PMIC-6-13V5-COMEX-VDD-In-1",
                                "PMIC-6-COMEX-VCCSA-Out-2", "PMIC-6-COMEX-VCORE-Out-1", "PSU-1-12V-Out", "PSU-2-12V-Out"]

        self.device_list = [IbConsts.DEVICE_ASIC_PREFIX + str(index) for index in range(1, self.asic_amount + 1)]
        self.device_list.append(IbConsts.DEVICE_SYSTEM)

        dump_files_to_replace_for_each_asic = ['docker.swss-ibv0{}.log', 'saidump{}']
        dump_files_to_add_for_each_asic = ['APPL_DB.json.{}', 'ASIC_DB.json.{}', 'CONFIG_DB.json.{}',
                                           'STATE_DB.json.{}', 'FLEX_COUNTER_DB.json.{}', 'COUNTERS_DB.json.{}',
                                           'COUNTERS_DB_1.json.{}', 'COUNTERS_DB_2.json.{}']

        for dump_file in dump_files_to_replace_for_each_asic:
            self.constants.dump_files.remove(dump_file.format(''))
            for asic_num in range(0, self.asic_amount):
                self.constants.dump_files.append(dump_file.format(asic_num))

        self.constants.firmware.append('transceiver')

        for dump_file in dump_files_to_add_for_each_asic:
            for asic_num in range(0, self.asic_amount):
                self.constants.dump_files.append(dump_file.format(asic_num))

        self.pre_login_message = "NVOS switch"
        self.post_login_message = "\n \u2588\u2588\u2588\u2557   \u2588\u2588\u2557\u2588\u2588\u2557   " \
                                  "\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557 " \
                                  "\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\n \u2588\u2588\u2588\u2588" \
                                  "\u2557  \u2588\u2588\u2551\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588" \
                                  "\u2554\u2550\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550" \
                                  "\u2550\u2550\u255d\n \u2588\u2588\u2554\u2588\u2588\u2557 \u2588\u2588" \
                                  "\u2551\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2551   " \
                                  "\u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\n " \
                                  "\u2588\u2588\u2551\u255a\u2588\u2588\u2557\u2588\u2588\u2551\u255a\u2588" \
                                  "\u2588\u2557 \u2588\u2588\u2554\u255d\u2588\u2588\u2551   \u2588\u2588\u2551" \
                                  "\u255a\u2550\u2550\u2550\u2550\u2588\u2588\u2551\n \u2588\u2588\u2551 \u255a" \
                                  "\u2588\u2588\u2588\u2588\u2551 \u255a\u2588\u2588\u2588\u2588\u2554\u255d " \
                                  "\u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2588" \
                                  "\u2588\u2588\u2588\u2588\u2551\n \u255a\u2550\u255d  \u255a\u2550\u2550" \
                                  "\u2550\u255d  \u255a\u2550\u2550\u2550\u255d   \u255a\u2550\u2550\u2550" \
                                  "\u2550\u2550\u255d \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u255d\n"
        self.ssd_image_per_ssd_model = {
            'StorFly VSFBM4XC016G-MLX2':
                BaseSwitch.SsdImageConsts(
                    file='/auto/sw_system_project/NVOS_INFRA/verification_files/ssd_fw/virtium_ssd_fw_pkg.pkg',
                    current_version='0202-000', alternate_version='0202-002'),
        }
        self.module_offset = None  # Should be overridden in child if used for module mapping
        self.expected_operation_durations = {}

    def sleep_after_system_reboot(self):
        pass

    def init_documents_consts(self):
        self.documents_files = {
            DocumentsConsts.TYPE_EULA: "NVOS_EULA.pdf",
            DocumentsConsts.TYPE_RELEASE_NOTES: f"NVOS_{self.switch_type}_Release_Notes.pdf",
            DocumentsConsts.TYPE_USER_MANUAL: f"NVOS_{self.switch_type}_User_Manual.pdf",
            DocumentsConsts.TYPE_OPEN_SOURCE_LICENSES: "Open_Source_Licenses.txt"}
        self.documents_path = {DocumentsConsts.TYPE_EULA:
                               f"/usr/share/nginx/html/system_documents/eula/{self.documents_files[DocumentsConsts.TYPE_EULA]}",
                               DocumentsConsts.TYPE_RELEASE_NOTES:
                               f"/usr/share/nginx/html/system_documents/release_notes/{self.documents_files[DocumentsConsts.TYPE_RELEASE_NOTES]}",
                               DocumentsConsts.TYPE_USER_MANUAL:
                               f"/usr/share/nginx/html/system_documents/user_manual/{self.documents_files[DocumentsConsts.TYPE_USER_MANUAL]}",
                               DocumentsConsts.TYPE_OPEN_SOURCE_LICENSES:
                               f"/usr/share/nginx/html/system_documents/open_source_licenses/"
                               f"{self.documents_files[DocumentsConsts.TYPE_OPEN_SOURCE_LICENSES]}"}

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors += ["CPU-Core-2-Temp", "CPU-Core-3-Temp", "PCH-Temp", "PSU-2-Temp", "SODIMM-1-Temp"]

    def _init_sensors_dict(self):
        self.sensors_dict = {"VOLTAGE": self.voltage_sensors,
                             "TEMPERATURE": self.temperature_sensors}

    def _init_interface_lists(self):
        self.ib_ports_num = 64
        self.mgmt_ports = ['eth0']
        self.plane_port_list = ['pl1', 'pl2']
        self.default_aggregated_port = 'sw32p1'
        self.default_loopback_ports = ['sw31p1', 'sw31p2']
        self.loop_back_to_ports = {
            'sw31p1': 'sw32p1pl1',
            'sw31p2': 'sw32p1pl2'
        }
        self.default_port = 'sw1p1'
        self.aggregated_port_list = ['sw1p1', 'sw2p1', 'sw32p1']  # total 3 ports
        self.fnm_port_list = ['fnm1']
        self.aggregated_split_port_list = ['sw10p1']
        self.fnm_external_port_list = ['fnm1']
        self.fnm_external_child_port = 'fnm1s1'
        self.interface_active_internal_fnm_ports = {}
        self.child_aggregated_port = 'swA10p1s1'
        self.num_of_plane_ports = 4
        self.num_of_fnm_plane_ports = 2
        self.network_ports = ['eth0', 'ib0', 'lo']  # total 3 ports
        self.fnm_link_speed = '400G'
        self.fnm_port_type = 'fnm'
        self.object_numbers = {  # TBD - update values
            'sw1p1': {
                'plane1': 'COUNTERS:oid:0x100000000001f',
                'plane2': 'COUNTERS:oid:0x100000000001f'
            },
            'sw2p1': {
                'plane1': 'COUNTERS:oid:0x100000000001f',
                'plane2': 'COUNTERS:oid:0x100000000001f'
            },
            'sw32p1': {
                'plane1': 'COUNTERS:oid:0x100000000001f',
                'plane2': 'COUNTERS:oid:0x100000000001f'
            }
        }

    def wait_for_os_to_become_functional(self, engine, find_prompt_tries=60, find_prompt_delay=10):
        return DutUtilsTool.wait_for_nvos_to_become_functional(engine)

    def reload_device(self, engine, cmd_list, validate=False, enter_config_mode=False):
        return engine.send_config_set(cmd_list, exit_config_mode=False, cmd_verify=False,
                                      enter_config_mode=enter_config_mode)

    def get_bios_file_name(self):
        return self.current_bios_version_path.split('/')[-1]

    def setup_base_aaa_config(self, dut_engine: LinuxSshEngine):
        pass

    def cleanup_base_aaa_config(self, dut_engine: LinuxSshEngine):
        pass


# -------------------------- Gorilla Switch ----------------------------


class GorillaSwitch(IbSwitch):

    def __init__(self, asic_amount=1):
        super().__init__(asic_amount=asic_amount, switch_class=NvosConst.GORILLA_SWITCH)

    def _init_constants(self):
        IbSwitch._init_constants(self)
        self.core_count = 4
        self.asic_type = NvosConst.QTM2
        self.split_ports_supported = True
        self.profile_change_supported = True
        self.health_monitor_config_file_path = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(
            "x86_64-mlnx_mqm9700-r0")
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-mlnx_mqm9700-r0")
        self.show_platform_output.update({
            "product-name": "MQM9700",
            "asic-model": self.asic_type,
        })
        self.asic_version = BaseSwitch.AsicImageConsts(
            version="31_2014_0902-024",
            filename="fw-QTM2-rel-31_2014_0902-024.mfa"
        )
        self.previous_cpld_version = BaseSwitch.CpldImageConsts(
            burn_image_path="/auto/sw_system_project/NVOS_INFRA/verification_files/cpld_fw/FUI000258_BURN_Gorilla_MNG_CPLD000232_REV0700_CPLD000324_REV0300_CPLD000268_REV0700_IPN.vme",
            refresh_image_path="/auto/sw_system_project/NVOS_INFRA/verification_files/cpld_fw/FUI000258_REFRESH_Gorilla_MNG_CPLD000232_REV0700_CPLD000324_REV0300_CPLD000268_REV0700.vme",
            version_names={
                "CPLD1": "CPLD000232_REV0700",
                "CPLD2": "CPLD000324_REV0300",
                "CPLD3": "CPLD000268_REV0700",
            }
        )
        self.current_cpld_version = BaseSwitch.CpldImageConsts(
            burn_image_path="/auto/sw_system_project/NVOS_INFRA/verification_files/cpld_fw/FUI000276_BURN_Gorilla_MNG_CPLD000232_REV0700_CPLD000324_REV0400_CPLD000268_REV0700_IPN.vme",
            refresh_image_path="/auto/sw_system_project/NVOS_INFRA/verification_files/cpld_fw/FUI000276_REFRESH_Gorilla_MNG_CPLD000232_REV0700_CPLD000324_REV0400_CPLD000268_REV0700.vme",
            version_names={
                "CPLD1": "CPLD000232_REV0700",
                "CPLD2": "CPLD000324_REV0400",
                "CPLD3": "CPLD000268_REV0700",
            }
        )
        self.stats_disk_header_num_of_lines = 16
        self.stats_cpu_header_num_of_lines = 12
        self.stats_temperature_header_num_of_lines = 53
        self.valid_ports_count = 64
        self.number_of_transceivers = 64
        self.transceivers_tables_name = "TRANSCEIVER_FIRMWARE_INFO"
        self.transceiver_list = [f'sw{a + 1}' for a in range(32)]
        self.supports_tpm_testing = False

    def get_mgmt_ports(self) -> List[str]:
        return self.mgmt_ports

    def verify_sed_password(self, tpm_tool, sed_default_password=""):
        return  # This should be ignored on gorilla, overrides method from base switch

    def _init_fan_list(self):
        super()._init_fan_list()
        self.fan_list += ["FAN7/1", "FAN7/2"]

    def _init_led_list(self):
        super()._init_led_list()
        self.led_list.append('FAN7')

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors += ["CPU-Core-2-Temp", "CPU-Core-3-Temp", "PCH-Temp", "PSU-2-Temp"]

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2000, range_max=10000),
            "max-speed": ExpectedString(range_min=20000, range_max=40000)}
        self.platform_inventory_switch_values.update({"hardware-version": None,
                                                      "model": ExpectedString(regex="MQM9700.*")})

    def _init_eth0_speeds(self):
        super()._init_eth0_speeds()
        self.supported_eth0_speeds += ['10M']

    def _init_boot_time_timeouts(self):
        super()._init_boot_time_timeouts()
        self.timeout_system_is_ready = 10 * MINUTE


# -------------------------- Gorilla BF3 Switch ----------------------------
class GorillaSwitchBF3(GorillaSwitch):

    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.constants.firmware.remove(PlatformConsts.FW_BIOS)
        self.ib_ports_num = 64
        self.core_count = 16
        self.asic_type = NvosConst.QTM2

    def get_mgmt_ports(self) -> List[str]:
        return self.mgmt_ports

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors += ["xSFP-module-26-Temp", "xSFP-module-29-Temp"]


# -------------------------- BlackMamba Switch ----------------------------
class BlackMambaSwitch(IbSwitch):

    def __init__(self):
        super().__init__(asic_amount=4, switch_class=NvosConst.BLACK_MAMBA_SWITCH)

    def _init_constants(self):
        self.asic_amount = 4
        super()._init_constants()
        self.ib_ports_num = 2 * 72
        self.core_count = 4
        self.asic_type = NvosConst.QTM3
        self.multi_planar = True
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-mlnx_qm8790-r0")
        self.show_platform_output.update({
            "product-name": "Q3400_RA",
            "asic-model": self.asic_type,
        })
        self.asic_version = BaseSwitch.AsicImageConsts(
            version="35.2014.2012",
            filename="fw-QTM3-rel-35_2014_2012.mfa"
        )
        self.voltage_sensors = ['PMIC-1-12V-VDD-ASIC1-In-1', 'PMIC-1-ASIC1-VDD-Out-1',
                                'PMIC-2-12V-HVDD-DVDD-ASIC1-In-1', 'PMIC-2-ASIC1-DVDD-PL0-Out-2',
                                'PMIC-2-ASIC1-HVDD-PL0-Out-1', 'PMIC-3-12V-HVDD-DVDD-ASIC1-In-1',
                                'PMIC-3-ASIC1-DVDD-PL1-Out-2', 'PMIC-3-ASIC1-HVDD-PL1-Out-1',
                                'PMIC-4-12V-VDD-ASIC2-In-1', 'PMIC-4-ASIC2-VDD-Out-1',
                                'PMIC-5-12V-HVDD-DVDD-ASIC2-In-1', 'PMIC-5-ASIC2-DVDD-PL0-Out-2',
                                'PMIC-5-ASIC2-HVDD-PL0-Out-1', 'PMIC-6-12V-HVDD-DVDD-ASIC2-In-1',
                                'PMIC-6-ASIC2-DVDD-PL1-Out-2', 'PMIC-6-ASIC2-HVDD-PL1-Out-1',
                                'PMIC-7-12V-VDD-ASIC3-In-1', 'PMIC-7-ASIC3-VDD-Out-1',
                                'PMIC-8-12V-HVDD-DVDD-ASIC3-In-1', 'PMIC-8-ASIC3-DVDD-PL0-Out-2',
                                'PMIC-8-ASIC3-HVDD-PL0-Out-1', 'PMIC-9-12V-HVDD-DVDD-ASIC3-In-1',
                                'PMIC-9-ASIC3-DVDD-PL1-Out-2', 'PMIC-9-ASIC3-HVDD-PL1-Out-1',
                                'PMIC-10-12V-VDD-ASIC4-In-1', 'PMIC-10-ASIC4-VDD-Out-1',
                                'PMIC-11-12V-HVDD-DVDD-ASIC4-In-1', 'PMIC-11-ASIC4-DVDD-PL0-Out-2',
                                'PMIC-11-ASIC4-HVDD-PL0-Out-1', 'PMIC-12-12V-HVDD-DVDD-ASIC4-In-1',
                                'PMIC-12-ASIC4-DVDD-PL1-Out-2', 'PMIC-12-ASIC4-HVDD-PL1-Out-1', 'PMIC-13-12V-MAIN-In-1',
                                'PMIC-13-CEX-VDD-Out-1', 'PSU-1-12V-Out', 'PSU-2-12V-Out', 'PSU-3-12V-Out',
                                'PSU-4-12V-Out', 'PSU-5-12V-Out', 'PSU-6-12V-Out', 'PSU-7-12V-Out', 'PSU-8-12V-Out']

        self.stats_disk_header_num_of_lines = 16
        self.stats_cpu_header_num_of_lines = 12
        self.stats_temperature_header_num_of_lines = 45
        self.fw_versions_json_file_path = "/auto/sw_system_project/NVOS_INFRA/verification_files/platform_components/black_mamba_versions.json"
        self.allow_cpld_update = True
        self.system_profile_default_values = ['enabled', '1792', 'enabled', 'disabled', '1']
        self.mst_dev_name = '/dev/mst/mt54004_pciconf2'
        self.ztp_prod_json = 'uninstall_prod.json'
        self.ztp_dev_json = 'uninstall.json'
        self.ztp_complex_prod_json = 'complex_prod.json'
        self.ztp_complex_dev_json = 'complex.json'
        self.valid_ports_count = 144
        self.number_of_transceivers = 145
        self.transceivers_tables_name = "TRANSCEIVER_FIRMWARE_INFO"
        self.transceiver_list = ['fnm1'] + [f'sw{a + 1}p{b}' for a in range(72) for b in (1, 2)]
        self.constants.firmware.extend(['CPLD4', 'CPLD5', 'CPLD6'])
        self.expected_operation_durations.update({
            "Install BIOS": 550,
        })

    def get_mgmt_ports(self) -> List[str]:
        return self.mgmt_ports

    def _init_fan_list(self):
        super()._init_fan_list()
        self.fan_list += ["FAN7/1", "FAN7/2", "FAN8/1", "FAN8/2", "FAN9/1", "FAN9/2", "FAN10/1", "FAN10/2"]

    def _init_led_list(self):
        super()._init_led_list()
        self.led_list += ['FAN7', 'FAN8', 'FAN9', 'FAN10']

    def _init_psu_list(self):
        super()._init_psu_list()
        self.psu_list += ["PSU3", "PSU4", "PSU5", "PSU6", "PSU7", "PSU8"]
        self.psu_fan_list += ["PSU3/FAN", "PSU4/FAN", "PSU5/FAN", "PSU6/FAN", "PSU7/FAN", "PSU8/FAN"]

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors = [
            'ASIC1', 'ASIC2', 'ASIC3', 'ASIC4', 'Ambient-Fan-Side-Temp', 'Ambient-Port-Side-Temp', 'PCH-Temp',
            'CPU-Core-0-Temp', 'CPU-Core-1-Temp', 'CPU-Core-2-Temp', 'CPU-Core-3-Temp', 'CPU-Pack-Temp', 'Drive-Temp',
            'PMIC-1-Temp', 'PMIC-2-Temp', 'PMIC-3-Temp', 'PMIC-4-Temp', 'PMIC-5-Temp', 'PMIC-6-Temp', 'PMIC-7-Temp',
            'PMIC-8-Temp', 'PMIC-9-Temp', 'PMIC-10-Temp', 'PMIC-11-Temp', 'PMIC-12-Temp', 'PMIC-13-Temp',
            'PSU-1-Temp', 'PSU-2-Temp', 'PSU-3-Temp', 'PSU-4-Temp', 'PSU-5-Temp', 'PSU-6-Temp', 'PSU-7-Temp', 'PSU-8-Temp',
            'SODIMM-1-Temp', 'SODIMM-2-Temp']

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK.lower(), "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2000, range_max=10000),
            "max-speed": ExpectedString(range_min=20000, range_max=40000)}
        self.platform_inventory_switch_values.update({"hardware-version": None,
                                                      "model": None})

    def _init_interface_lists(self):
        super()._init_interface_lists()
        self.mgmt_ports = ['eth0']  # 'eth1' disabled for now
        ib_ports = self.fnm_external_port_list + [f'sw{a + 1}p{b}' for a in range(self.ib_ports_num) for b in (1, 2)]
        # = ['fnm1', 'sw1p1', 'sw1p2', ..., 'sw72p1', 'sw72p2']
        self.interface_list = self.network_ports + ib_ports + ['eth1']
        self.interface_fae_list = (
            self.interface_list +
            [f'{p}pl{pl + 1}' for p in ib_ports for pl in range(self.asic_amount)] +  # e.g. sw7p1 - sw7p4
            [f'fnma{pl + 1}p{i + 1}' for i in range(3) for pl in range(self.asic_amount)])  # fnma1p1 - fnma4p3
        self.interface_active_internal_fnm_ports = {'fnma1p1', 'fnma1p2', 'fnma2p1', 'fnma2p2', 'fnma3p1', 'fnma3p2',
                                                    'fnma4p1', 'fnma4p2'}
        # because other internal fnm ports are unused currently
        self.fnm_link_speed = '800G'
        self.fnm_internal_link_speed = '50G'

    def _init_eth0_speeds(self):
        super()._init_eth0_speeds()
        self.supported_eth0_speeds += ['10M']

    def _init_ib_speeds(self):
        super()._init_ib_speeds()
        self.supported_ib_speeds = ("xdr",)

    def _relevant_config_filename_by_version(self, version: str) -> str:
        return 'nvos_config_xdr.yml'

    def _init_boot_time_timeouts(self):
        super()._init_boot_time_timeouts()
        self.timeout_system_is_ready = 15 * MINUTE


# -------------------------- Taipan Switch ----------------------------
class TaipanSwitch(BlackMambaSwitch):  # All values will be updated on Taipan BU

    def __init__(self):
        super().__init__(asic_amount=4, switch_class=NvosConst.TAIPAN_SWITCH)

    def _init_constants(self):
        super()._init_constants()
        self.number_of_transceivers = 18
        self.transceivers_tables_name = "TRANSCEIVER_INFO"
        self.transceiver_list = [f'els{a + 1}' for a in range(18)] + ['fnm1'] + [f'oe{b + 1}' for b in range(72)]

    def _init_psu_list(self):
        self.psu_list = []


# -------------------------- Crocodile Switch ----------------------------
class CrocodileSwitch(IbSwitch):

    def __init__(self):
        super().__init__(asic_amount=2, switch_class=NvosConst.CROCODILE_SWITCH)

    def _init_constants(self):
        super()._init_constants()
        self.ib_ports_num = 64
        self.core_count = 4
        self.split_ports_supported = True
        self.asic_type = NvosConst.QTM3
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-nvidia_qm3400-r0")
        self.show_platform_output.update({
            "product-name": "QM3400",
            "asic-model": self.asic_type,
        })
        self.asic_version = BaseSwitch.AsicImageConsts(
            version="35.2014.2012",
            filename="fw-QTM3-rel-35_2014_2012.mfa"
        )
        self.mst_dev_name = '/dev/mst/mt54004_pciconf0'  # TODO update
        self.ztp_prod_json = 'uninstall_prod.json'
        self.ztp_dev_json = 'uninstall.json'
        self.ztp_complex_prod_json = 'complex_prod.json'
        self.ztp_complex_dev_json = 'complex.json'
        self.voltage_sensors = ['PMIC-1-12V-VDD-ASIC1-In-1', 'PMIC-1-ASIC1-VDD-Out-1',
                                'PMIC-2-12V-HVDD-DVDD-ASIC1-In-1', 'PMIC-2-ASIC1-DVDD-PL0-Out-2',
                                'PMIC-2-ASIC1-HVDD-PL0-Out-1', 'PMIC-3-12V-HVDD-DVDD-ASIC1-In-1',
                                'PMIC-3-ASIC1-DVDD-PL1-Out-2', 'PMIC-3-ASIC1-HVDD-PL1-Out-1',
                                'PMIC-4-12V-VDD-ASIC2-In-1', 'PMIC-4-ASIC2-VDD-Out-1',
                                'PMIC-5-12V-HVDD-DVDD-ASIC2-In-1', 'PMIC-5-ASIC2-DVDD-PL0-Out-2',
                                'PMIC-5-ASIC2-HVDD-PL0-Out-1', 'PMIC-6-12V-HVDD-DVDD-ASIC2-In-1',
                                'PMIC-6-ASIC2-DVDD-PL1-Out-2', 'PMIC-6-ASIC2-HVDD-PL1-Out-1', 'PMIC-7-12V-MAIN-In-1',
                                'PMIC-7-CEX-VDD-Out-1', 'PSU-1-12V-Out', 'PSU-2-12V-Out', 'PSU-3-12V-Out',
                                'PSU-4-12V-Out']
        self.stats_disk_header_num_of_lines = 16
        self.system_profile_default_values = ['enabled', '1792', 'enabled', 'disabled', '1']
        self.stats_cpu_header_num_of_lines = 12
        self.stats_power_header_num_of_lines = 17
        self.stats_temperature_header_num_of_lines = 32
        self.valid_ports_count = 73
        self.number_of_transceivers = 73
        self.transceivers_tables_name = "TRANSCEIVER_FIRMWARE_INFO"
        self.transceiver_list = ['fnm1'] + [f'swA{a + 1}' for a in range(18)] + [f'swB{b + 1}' for b in range(18)]
        self.allow_cpld_update = True
        self.fw_versions_json_file_path = "/auto/sw_system_project/NVOS_INFRA/verification_files/platform_components/crocodile_versions.json"
        self.expected_operation_durations.update({
            "Install BIOS": 500,
        })
        self.constants.firmware.append('CPLD4')

    def get_mgmt_ports(self) -> List[str]:
        return self.mgmt_ports

    def _init_fan_list(self):
        super()._init_fan_list()
        self.fan_list.remove("FAN6/1")
        self.fan_list.remove("FAN6/2")

    def _init_led_list(self):
        super()._init_led_list()
        self.led_list.remove('FAN6')

    def _init_psu_list(self):
        super()._init_psu_list()
        self.psu_list += ["PSU3", "PSU4"]
        self.psu_fan_list += ["PSU3/FAN", "PSU4/FAN"]

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors += ["ASIC2", "PSU-3-Temp", "PSU-4-Temp", "PMIC-2-Temp", "PMIC-7-Temp"]

    def _init_eth0_speeds(self):
        super()._init_eth0_speeds()
        self.supported_eth0_speeds += ['10M']

    def _relevant_config_filename_by_version(self, version: str) -> str:
        return 'nvos_config_xdr_crocodile.yml'

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK.lower(), "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2000, range_max=10000),
            "max-speed": ExpectedString(range_min=20000, range_max=40000)}
        self.platform_inventory_switch_values.update({"hardware-version": None,
                                                      "model": None})

    def _init_interface_lists(self):
        super()._init_interface_lists()
        self.mgmt_ports = ['eth0', 'eth1']
        self.interface_active_internal_fnm_ports = {'fnma0p1', 'fnma1p1'}
        self.default_port = 'swA1p1'
        self.fnm_link_speed = '200G'
        self.fnm_internal_link_speed = '100G'
        traffic_ports = [f'sw{a}{n}p{p}' for a in 'AB' for n in range(1, 19) for p in (1, 2)]
        self.interface_list = self.network_ports + ['eth1', 'fnm1'] + traffic_ports
        self.interface_fae_list = (
            self.interface_list +
            ['fnma0p1', 'fnma0p2', 'fnma1p1'] +
            [f'{port}pl{i}' for port in traffic_ports for i in range(1, 5)]
        )

    def _init_boot_time_timeouts(self):
        super()._init_boot_time_timeouts()
        self.timeout_system_is_ready = 10 * MINUTE


# -------------------------- Crocodile Simx Switch ----------------------------
class CrocodileSimxSwitch(IbSwitch):

    def __init__(self):
        super().__init__(asic_amount=1, switch_class=NvosConst.CROCODILE_SWITCH)


# -------------------------- NvLink Switch ----------------------------
class NvLinkSwitch(IbSwitch):

    def __init__(self, asic_amount):
        super().__init__(switch_type=NvosConst.NVL_SWITCH_TYPE, asic_amount=asic_amount,
                         switch_class=NvosConst.JULIET_SWITCH)

    def _init_interface_lists(self):
        super()._init_interface_lists()
        self.mgmt_ports = ['eth0', 'eth1']

    def _init_constants(self):
        super()._init_constants()
        self.ib_ports_num = 64
        self.core_count = 4
        self.asic_type = NvosConst.QTM3
        self.health_monitor_config_file_path = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(
            "x86_64-mlnx_mqm9700-r0")
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-mlnx_mqm9700-r0")
        self.unset_all_command += "; nv unset cluster"

    def get_mgmt_ports(self) -> List[str]:
        return self.mgmt_ports


# -------------------------- Juliet Switch ----------------------------


class JulietSwitch(NvLinkSwitch):
    FaeImagesTestConsts = namedtuple('FaeImagesTestConsts', ('current_image_version', 'alternate_image_version'))
    NmxClusterAppsConsts = namedtuple('NmxClusterAppsConsts',
                                      ('burn_path', 'burn_version_names'))

    def __init__(self, asic_amount):
        super().__init__(asic_amount=asic_amount)

    def _init_constants(self):
        super()._init_constants()

        self.category_list = ['temperature', 'cpu', 'disk', 'fan', 'mgmt-interface', 'voltage']
        self.category_disabled_dict = {
            self.category_list[0]: self.category_default_disabled_dict,
            self.category_list[1]: self.category_default_disabled_dict,
            self.category_list[2]: self.category_disk_default_disable_dict,
            self.category_list[3]: self.category_default_disabled_dict,
            self.category_list[4]: self.category_default_disabled_dict,
            self.category_list[5]: self.category_default_disabled_dict
        }
        self.category_list_default_dict = {
            self.category_list[0]: self.category_default_dict,
            self.category_list[1]: self.category_default_dict,
            self.category_list[2]: self.category_disk_default_dict,
            self.category_list[3]: self.category_default_dict,
            self.category_list[4]: self.category_default_dict,
            self.category_list[5]: self.category_default_dict
        }
        self.bmc_older_version_path = "/auto/sw_system_release/low_level/openbmc/88.0002.0472/dev/juliet-bmc/erot_sign_debug/cec1736-apfw-000201d8.fwpkg"
        self.fpga_older_version_path = "/auto/sw_system_release/fpga/juliet/V0_15/FPGA_juliet_0v15.fwpkg"
        self.has_nmx = True
        self.has_bmc = True
        self.ztp_prod_json = 'uninstall_juliet_prod.json'
        self.ztp_dev_json = 'uninstall_juliet.json'
        self.ztp_complex_prod_json = 'complex_prod_juliet.json'
        self.ztp_complex_dev_json = 'complex_juliet.json'
        self.show_platform_chassis_location_output = {
            ChassisLocationConsts.TRAY_ID: ExpectedString(range_min=-1, range_max=18),
            ChassisLocationConsts.SLOT_NUM: ExpectedString(range_min=0, range_max=28),
            ChassisLocationConsts.CHAS_SN: ExpectedString(regex="^\\d+$"),
            ChassisLocationConsts.TOPO_ID: ExpectedString(regex=f"^({'|'.join(ChassisLocationConsts.ALLOWED_TOPOLOGIES)})$")
        }
        self.show_platform_cable_cartridge_output = {
            CableCartridgeConsts.KEY_TRAY_ID: ExpectedString(range_min=-1, range_max=18),
            CableCartridgeConsts.KEY_SLOT_ID: ExpectedString(range_min=0, range_max=28),
            CableCartridgeConsts.KEY_SERIAL: ExpectedString(regex="^\\d+$"),
            CableCartridgeConsts.KEY_PART_NUMBER: ExpectedString(regex=f"^({'|'.join(CableCartridgeConsts.ALLOWED_PART_NUMBERS)})$"),
            CableCartridgeConsts.KEY_MANUFACTURING_DATE: ExpectedString(regex="^(0[1-9]|1[0-2])/([0-2][0-9]|3[0-1])/\\d{2} - ([0-1][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])$")
        }
        cluster_files = ['conf', 'nmx-controller', 'nmx-telemetry']
        self.constants = self.constants._replace(cluster_files=cluster_files)
        bmc_dump_files = ['bmc_debug_log_dump.tar']
        self.constants = self.constants._replace(bmc_dump_files=bmc_dump_files)
        self.constants.dump_files.append('BMCeeprom')
        self.constants.dump_files.remove('hdparm')
        self.constants.log_nmx_files.extend(['fabricmanager.log.gz', 'gwapi.log.gz', 'nvlsm.log.gz'])
        stats_dump_files = ["cpu.csv.gz", "disk.csv.gz", "fan.csv.gz",
                            "mgmt-interface.csv.gz", "temperature.csv.gz", "voltage.csv.gz"]
        self.constants = self.constants._replace(stats_dump_files=stats_dump_files)
        self.constants.erots.extend(
            [PlatformConsts.EROT_BMC_PATH_NAME, PlatformConsts.EROT_CPU_PATH_NAME, PlatformConsts.EROT_FPGA_PATH_NAME,
             PlatformConsts.EROT_ASIC1_PATH_NAME, PlatformConsts.EROT_ASIC2_PATH_NAME])

        self.nmx_cluster_apps_versions = self.NmxClusterAppsConsts(
            burn_path={
                ClusterConsts.NMX_CONTROLLER: "/auto/sw/release/NMX/NMX-controller/package/0.8.1/nmx-c-nvlink_0.8.1_2024-12-17_14-24.tar.gz",
                ClusterConsts.NMX_TELEMETRY: "/auto/sw/release/NMX/NMX-telemetry/nmx-telemetry_0.8.6_2024-12-16.tgz"
            },
            burn_version_names={
                ClusterConsts.NMX_CONTROLLER: "0.8.1",
                ClusterConsts.NMX_TELEMETRY: "0.8.6"
            }
        )
        self.supported_commands.extend([ActionConsts.POWER_CYCLE])
        self.asic_version = BaseSwitch.AsicImageConsts(
            version="35.2014.1492",
            filename="fw-QTM3-rel-35_2014_1492.mfa"
        )
        self.bios_image_info = BaseSwitch.BiosImagesConsts(
            current_version={
                'path': '/auto/sw_system_release/sx_mlnx_bios/SnowyOwl/0ACTV_00.00.018/Release/erot_sign_debug/cec1736-apfw-0000012.fwpkg',
                'filename': 'cec1736-apfw-0000012.fwpkg',
                'version_name': '0ACTV_00.00.018d',
                'date': '08/21/2024'},
            alternate_version={
                'path': '/auto/sw_system_release/sx_mlnx_bios/SnowyOwl/0ACTV_00.00.018/Release/erot_sign_debug/cec1736-apfw-0000012.fwpkg',
                'filename': 'cec1736-apfw-0000012.fwpkg',
                'version_name': '0ACTV_00.00.018d',
                'date': '08/21/2024'})

        self.power_cycle_type = 'juliet-power-cycle'
        self.fw_versions_json_file_path = "/auto/sw_system_project/NVOS_INFRA/verification_files/platform_components/juliet_versions.json"
        self.valid_ports_count = 72
        self.module_offset = 9

    def _init_fan_list(self):
        super()._init_fan_list()

    def _init_led_list(self):
        self.led_list = [FansConsts.FAN_STATUS_LED, "STATUS", "UID"]

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_inventory_items.extend([PlatformConsts.FW_BMC])
        self.platform_inventory_items_dict.update({'bmc': [PlatformConsts.FW_BMC]})
        platform_inventory_bmc_values = {
            "hardware-version": NvosConst.NOT_AVAILABLE, "model": None,
            "serial": None, PlatformConsts.INV_STATE: FansConsts.STATE_OK,
            "type": PlatformConsts.FW_BMC.lower()}
        self.platform_inventory_values.update({'bmc': platform_inventory_bmc_values})

    def _init_fae_lists(self):
        super()._init_fae_lists()
        self.fae_eeprom_values = {
            "BMC": {"Manufacturer": "NVIDIA", "Model": None, "PartNumber": ExpectedString(r"[-\d]+"),
                    "SerialNumber": ExpectedString.number_and_string(""), "State": "Enabled"}
        }

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors = [
            'ASIC1', 'ASIC2', 'Ambient-MNG-Temp', 'CPU-Pack-Temp', 'Drive-Temp', 'HSC-VinDC-Temp', 'PDB-Conv-1-Temp',
            'PDB-Conv-2-Temp', 'PDB-Conv-3-Temp', 'PDB-Conv-4-Temp', 'PMIC-1-Temp', 'PMIC-2-Temp', 'PMIC-3-Temp',
            'PMIC-4-Temp', 'PMIC-5-Temp', 'PMIC-6-Temp', 'PMIC-7-Temp', 'PMIC-8-Temp',
            'SWB-ASIC1-PCB-Temp', 'SWB-ASIC2-PCB-Temp', 'SODIMM-1-Temp']

    def _init_gnmi_consts(self):
        super()._init_gnmi_consts()
        self.bmc_xpath = "platform-general/versions/state/fw-version-bmc"
        self.erot_xpath = "platform-general/versions/state/fw-version-erot"
        self.fpga_xpath = "platform-general/versions/state/fw-version-fpga"
        self.components_gnmi_xpath = [self.bmc_xpath, self.bios_xpath, self.erot_xpath, self.fpga_xpath,
                                      self.cpld1_xpath, self.cpld2_xpath, self.cpld3_xpath, self.cpld4_xpath]

    def _init_boot_time_timeouts(self):
        super()._init_boot_time_timeouts()
        self.timeout_system_is_ready = 20 * MINUTE
        self.timeout_reboot_to_grub_menu = 5 * MINUTE

    def get_available_erot_names(self, setup_name: str) -> List[str]:
        available_erots_per_juliet_number: Dict[str, List[str]] = {
            '68': [SPDMComponents.BMC],
            '121': SPDMComponents.ALL_SUPPORTED_COMPONENTS,
            '126': [SPDMComponents.BMC],
            '128': [SPDMComponents.BMC, SPDMComponents.FPGA, SPDMComponents.NVSWITCH_0],
        }
        for juliet_num, available_erots in available_erots_per_juliet_number.items():
            if setup_name.endswith(juliet_num):
                logging.info(f'available ERoTs for {setup_name} - {available_erots}')
                return available_erots
        logging.info(f'no available ERoTs found for {setup_name}')
        return []


# -------------------------- JulietScaleout Switch ----------------------------
class JulietScaleoutSwitch(JulietSwitch):

    def __init__(self):
        super().__init__(asic_amount=2)

    def _init_constants(self):
        super()._init_constants()
        self.asic_type = NvosConst.NVL5
        self.cluster_app_nmx_controller = {'addition-info': ExpectedString(regex=".*"), 'app-id': 'nmx-c-nvos', 'app-ver': None, 'capabilities': 'sm, gfm, fib, gw-api', 'components-ver': None, 'reason': '', 'status': 'ok'}
        self.cluster_app_nmx_telemetry = {'addition-info': ExpectedString(regex=".*"), 'app-id': 'nmx-telemetry', 'app-ver': None, 'capabilities': 'nvl telemetry, gnmi aggregation, syslog aggregation', 'components-ver': None, 'reason': '', 'status': 'ok'}
        self.cluster_app = {
            'nmx-controller': {
                **{  # Unpack
                    key: value
                    for key, value in self.cluster_app_nmx_controller.items()
                    if key not in []
                },
                'manager': {
                    "ca-certificate": "",
                    "certificate": "",
                    "encryption": "disabled",
                    "state": "disabled"
                }
            },
            'nmx-telemetry': {
                **{
                    key: value
                    for key, value in self.cluster_app_nmx_telemetry.items()
                    if key not in []
                },
                'manager': {
                    "ca-certificate": "",
                    "certificate": "",
                    "encryption": "disabled",
                    "state": "disabled"
                }
            }
        }
        # self.cluster_app = {
        #     'nmx-controller': {key: value for key, value in self.cluster_app_nmx_controller.items() if key not in []},
        #     'nmx-telemetry': {key: value for key, value in self.cluster_app_nmx_telemetry.items() if key not in []}
        # }
        self.cluster_app_installed = {
            'nmx-controller': {key: value for key, value in self.cluster_app_nmx_controller.items() if key not in ['reason', 'status', 'addition-info']},
            'nmx-telemetry': {key: value for key, value in self.cluster_app_nmx_telemetry.items() if key not in ['reason', 'status', 'addition-info']}
        }
        # self.cluster_app = {'nmx-controller': self.cluster_app_nmx_controller, 'nmx-telemetry': self.cluster_app_nmx_telemetry}
        self.core_count = 8
        self.reboot_type = 'julietscaleout_reboot'
        self.reset_factory = 'julietscaleout reset factory'
        self.generate_tech_support = 'julietscaleout generate_tech_support'
        self.constants.firmware.extend([PlatformConsts.FW_FPGA, PlatformConsts.FW_BMC])
        self.ssd_image = None
        self.voltage_sensors = [
            'HSC-VinDC-In', 'HSC-VinDC-Out', 'PDB-1-Conv-In-1', 'PDB-1-Conv-Out-1', 'PDB-2-Conv-In-1',
            'PDB-2-Conv-Out-1', 'PDB-3-Conv-In-1', 'PDB-3-Conv-Out-1', 'PDB-4-Conv-In-1', 'PDB-4-Conv-Out-1',
            'PMIC-1-12V-VDD-ASIC1-In-1', 'PMIC-1-ASIC1-VDD-Out-1', 'PMIC-2-12V-HVDD-DVDD-ASIC1-In-1',
            'PMIC-2-ASIC1-DVDD-PL0-Out-2', 'PMIC-2-ASIC1-HVDD-PL0-Out-1', 'PMIC-3-12V-HVDD-DVDD-ASIC1-In-1',
            'PMIC-3-ASIC1-DVDD-PL1-Out-2', 'PMIC-3-ASIC1-HVDD-PL1-Out-1', 'PMIC-4-12V-VDD-ASIC2-In-1',
            'PMIC-4-ASIC2-VDD-Out-1', 'PMIC-5-12V-HVDD-DVDD-ASIC2-In-1', 'PMIC-5-ASIC2-DVDD-PL0-Out-2',
            'PMIC-5-ASIC2-HVDD-PL0-Out-1', 'PMIC-6-12V-HVDD-DVDD-ASIC2-In-1', 'PMIC-6-ASIC2-DVDD-PL1-Out-2',
            'PMIC-6-ASIC2-HVDD-PL1-Out-1', 'PMIC-7-12V-MAIN-In-1', 'PMIC-7-CEX-VDD-Out-1',
            'PMIC-8-COMEX-VDD-MEM-In-1', 'PMIC-8-COMEX-VDD-MEM-Out-1']
        # TBD
        self.health_monitor_config_file_path = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(
            "x86_64-nvidia_n5110_ld-r0")
        self.show_platform_output.update({
            "product-name": "N5110_LD",
            "asic-model": self.asic_type,
        })

        self.stats_disk_header_num_of_lines = 16
        self.stats_cpu_header_num_of_lines = 12
        self.stats_temperature_header_num_of_lines = 25
        self.allow_cpld_update = True

        # Port 1-36 is from asic1/ Port 37-72 is from asic2
        self.nvl5_access_ports_list = ['acp1', 'acp2', 'acp3', 'acp4', 'acp5', 'acp6',
                                       'acp7', 'acp8', 'acp9', 'acp10', 'acp11', 'acp12', 'acp13', 'acp14',
                                       'acp15', 'acp16', 'acp17', 'acp18', 'acp19', 'acp20',
                                       'acp21', 'acp22', 'acp23', 'acp24', 'acp25', 'acp26',
                                       'acp27', 'acp28', 'acp29', 'acp30', 'acp31', 'acp32',
                                       'acp33', 'acp34', 'acp35', 'acp36', 'acp37', 'acp38', 'acp39', 'acp40',
                                       'acp41', 'acp42', 'acp43', 'acp44', 'acp45', 'acp46',
                                       'acp47', 'acp48', 'acp49', 'acp50', 'acp51', 'acp52',
                                       'acp53', 'acp54', 'acp55', 'acp56', 'acp57', 'acp58',
                                       'acp59', 'acp60', 'acp61', 'acp62', 'acp63', 'acp64',
                                       'acp65', 'acp66', 'acp67', 'acp68', 'acp69', 'acp70',
                                       'acp71', 'acp72']

        self.nvl5_trunk_ports_list = ['sw1p1s1', 'sw1p1s2', 'sw1p2s1', 'sw1p2s2',
                                      'sw2p1s1', 'sw2p1s2', 'sw2p2s1', 'sw2p2s2',
                                      'sw3p1s1', 'sw3p1s2', 'sw3p2s1', 'sw3p2s2',
                                      'sw4p1s1', 'sw4p1s2', 'sw4p2s1', 'sw4p2s2',
                                      'sw5p1s1', 'sw5p1s2', 'sw5p2s1', 'sw5p2s2',
                                      'sw6p1s1', 'sw6p1s2', 'sw6p2s1', 'sw6p2s2',
                                      'sw7p1s1', 'sw7p1s2', 'sw7p2s1', 'sw7p2s2',
                                      'sw8p1s1', 'sw8p1s2', 'sw8p2s1', 'sw8p2s2',
                                      'sw9p1s1', 'sw9p1s2', 'sw9p2s1', 'sw9p2s2',
                                      'sw10p1s1', 'sw10p1s2', 'sw10p2s1', 'sw10p2s2',
                                      'sw11p1s1', 'sw11p1s2', 'sw11p2s1', 'sw11p2s2',
                                      'sw12p1s1', 'sw12p1s2', 'sw12p2s1', 'sw12p2s2',
                                      'sw13p1s1', 'sw13p1s2', 'sw13p2s1', 'sw13p2s2',
                                      'sw14p1s1', 'sw14p1s2', 'sw14p2s1', 'sw14p2s2',
                                      'sw15p1s1', 'sw15p1s2', 'sw15p2s1', 'sw15p2s2',
                                      'sw16p1s1', 'sw16p1s2', 'sw16p2s1', 'sw16p2s2',
                                      'sw17p1s1', 'sw17p1s2', 'sw17p2s1', 'sw17p2s2',
                                      'sw18p1s1', 'sw18p1s2', 'sw18p2s1', 'sw18p2s2'
                                      ]
        self.network_ports = ['eth0', 'eth1', 'lo']
        self.all_nvl5_ports_list = self.nvl5_access_ports_list + self.nvl5_trunk_ports_list + self.network_ports
        self.nvl5_fnm_ports = ['fnm1', 'fnm2']
        self.nvl5_internal_fnm_ports = ['fnma0p1', 'fnma1p1']
        self.all_fae_nvl5_ports_list = self.all_nvl5_ports_list + self.nvl5_fnm_ports
        self.nvl5_port = ['sw1p1s1']
        self.nvl5_port_speed = '400G'
        self.fnm_link_speed = '100G'
        self.fnm_fae_link_speed = '100G'
        self.nvl5_port_type = 'nvl'
        self.num_of_cartridges = 4
        # will be updated

    def _init_fan_list(self):
        super()._init_fan_list()
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2", "FAN5/1", "FAN5/2", "FAN6/1", "FAN6/2"]
        self.fan_led_list = []

    def _init_psu_list(self):
        self.psu_list = []
        self.psu_fan_list = []

    def _init_led_list(self):
        super()._init_led_list()

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2000, range_max=10000),
            "max-speed": ExpectedString(range_min=20000, range_max=40000)}
        self.platform_inventory_switch_values.update({"hardware-version": None,
                                                      "model": "692-9K36F-00MV-JS0"})

    def sleep_after_system_reboot(self):
        logger.info("Sleeping for 60 seconds - Reboot takes longer on juliet for now")
        time.sleep(60)

    def _relevant_config_filename_by_version(self, version: str) -> str:
        return 'nvos_config_nvl5.yml'

# -------------------------- JulietTTM Switch ----------------------------


class JulietTTMSwitch(JulietScaleoutSwitch):

    def __init__(self):
        super().__init__()

    def _init_constants(self):
        super()._init_constants()
        self.allow_cpld_update = True

    def _init_fan_list(self):
        super()._init_fan_list()
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2"]
        self.fan_led_list = []

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_inventory_switch_values.update({"model": "692-9K36F-00MV-JSL"})

    def _init_led_list(self):
        super()._init_led_list()

# -------------------------- Ariel Switch ----------------------------


class JulietAriel(JulietTTMSwitch):

    def __init__(self):
        super().__init__()

    def _init_constants(self):
        super()._init_constants()
        # TODO - Need to be changed to correct values for Ariel. Double check with tamuz.
        self.health_monitor_config_file_path = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(
            "x86_64-nvidia_n5112_ld-r0")
        self.show_platform_output.update({
            "product-name": "N5112_LD",
            "asic-model": self.asic_type,
        })
        self.num_of_cartridges = 2
        self.nvl5_access_ports_list = ['acp1', 'acp2', 'acp3', 'acp4', 'acp5', 'acp6',
                                       'acp7', 'acp8', 'acp9', 'acp10', 'acp11', 'acp12', 'acp13', 'acp14',
                                       'acp15', 'acp16', 'acp17', 'acp18', 'acp19', 'acp20',
                                       'acp21', 'acp22', 'acp23', 'acp24', 'acp25', 'acp26',
                                       'acp27', 'acp28', 'acp29', 'acp30', 'acp31', 'acp32',
                                       'acp33', 'acp34', 'acp35', 'acp36', 'acp37', 'acp38', 'acp39', 'acp40',
                                       'acp41', 'acp42', 'acp43', 'acp44', 'acp45', 'acp46',
                                       'acp47', 'acp48', 'acp49', 'acp50', 'acp51', 'acp52',
                                       'acp53', 'acp54', 'acp55', 'acp56', 'acp57', 'acp58',
                                       'acp59', 'acp60', 'acp61', 'acp62', 'acp63', 'acp64',
                                       'acp65', 'acp66', 'acp67', 'acp68', 'acp69', 'acp70',
                                       'acp71', 'acp72']

        self.all_nvl5_ports_list = self.nvl5_access_ports_list + self.nvl5_trunk_ports_list + self.network_ports

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_inventory_switch_values.update({"model": "692-9K36F-A5MV-JQS"})


# -------------------------- ArielPS Switch ----------------------------


class JulietArielPS(JulietTTMSwitch):

    def __init__(self):
        super().__init__()

    def _init_constants(self):
        super()._init_constants()
        # TODO - Need to be changed to correct values for Ariel. Double check with tamuz.
        self.health_monitor_config_file_path = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(
            "x86_64-nvidia_n5112_ld-r0")
        self.show_platform_output.update({
            "product-name": "N5112_LD",
            "asic-model": self.asic_type,
        })

        self.voltage_sensors = ['HSC-VinDC-In', 'HSC-VinDC-Out', 'PDB-1-Conv-In-1', 'PDB-1-Conv-Out-1',
                                'PDB-2-Conv-In-1',
                                'PDB-2-Conv-Out-1', 'PMIC-1-12V-VDD-ASIC1-In-1', 'PMIC-1-ASIC1-VDD-Out-1',
                                'PMIC-2-12V-HVDD-DVDD-ASIC1-In-1',
                                'PMIC-2-ASIC1-DVDD-PL0-Out-2', 'PMIC-2-ASIC1-HVDD-PL0-Out-1',
                                'PMIC-3-12V-HVDD-DVDD-ASIC1-In-1',
                                'PMIC-3-ASIC1-DVDD-PL1-Out-2', 'PMIC-3-ASIC1-HVDD-PL1-Out-1',
                                'PMIC-4-12V-VDD-ASIC2-In-1',
                                'PMIC-4-ASIC2-VDD-Out-1', 'PMIC-5-12V-HVDD-DVDD-ASIC2-In-1',
                                'PMIC-5-ASIC2-DVDD-PL0-Out-2',
                                'PMIC-5-ASIC2-HVDD-PL0-Out-1', 'PMIC-6-12V-HVDD-DVDD-ASIC2-In-1',
                                'PMIC-6-ASIC2-DVDD-PL1-Out-2',
                                'PMIC-6-ASIC2-HVDD-PL1-Out-1', 'PMIC-7-12V-MAIN-In-1', 'PMIC-7-CEX-VDD-Out-1',
                                'PMIC-8-COMEX-VDD-MEM-In-1', 'PMIC-8-COMEX-VDD-MEM-Out-1']

        self.nvl5_access_ports_list = ['acp1', 'acp2', 'acp3', 'acp4', 'acp5', 'acp6',
                                       'acp7', 'acp8', 'acp9', 'acp10', 'acp11', 'acp12', 'acp13', 'acp14',
                                       'acp15', 'acp16', 'acp17', 'acp18', 'acp19', 'acp20',
                                       'acp21', 'acp22', 'acp23', 'acp24', 'acp25', 'acp26',
                                       'acp27', 'acp28', 'acp29', 'acp30', 'acp31', 'acp32',
                                       'acp33', 'acp34', 'acp35', 'acp36', 'acp37', 'acp38', 'acp39', 'acp40',
                                       'acp41', 'acp42', 'acp43', 'acp44', 'acp45', 'acp46',
                                       'acp47', 'acp48', 'acp49', 'acp50', 'acp51', 'acp52',
                                       'acp53', 'acp54', 'acp55', 'acp56', 'acp57', 'acp58',
                                       'acp59', 'acp60', 'acp61', 'acp62', 'acp63', 'acp64',
                                       'acp65', 'acp66', 'acp67', 'acp68', 'acp69', 'acp70',
                                       'acp71', 'acp72']

        self.all_nvl5_ports_list = self.nvl5_access_ports_list + self.nvl5_trunk_ports_list + self.network_ports

    def _init_temperature(self):
        super()._init_temperature()
        sensors_to_remove = ['PDB-Conv-3-Temp', 'PDB-Conv-4-Temp']
        for sensor in sensors_to_remove:
            self.temperature_sensors.remove(sensor)

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_inventory_switch_values.update({"model": "692-9K36F-A5MV-JCR"})


# -------------------------- JulietNonScaleoutSwitch Switch ----------------------------


class JulietNonScaleoutSwitch(JulietScaleoutSwitch):

    def __init__(self):
        super().__init__()

    def _init_constants(self):
        super()._init_constants()
        self.nvl5_access_ports_list = [
            'acp1', 'acp2', 'acp3', 'acp4', 'acp5', 'acp6',
            'acp7', 'acp8', 'acp9', 'acp10', 'acp11', 'acp12',
            'acp13', 'acp14', 'acp15', 'acp16', 'acp17', 'acp18',
            'acp19', 'acp20', 'acp21', 'acp22', 'acp23', 'acp24',
            'acp25', 'acp26', 'acp27', 'acp28', 'acp29', 'acp30',
            'acp31', 'acp32', 'acp33', 'acp34', 'acp35', 'acp36',
            'acp37', 'acp38', 'acp39', 'acp40', 'acp41', 'acp42',
            'acp43', 'acp44', 'acp45', 'acp46', 'acp47', 'acp48',
            'acp49', 'acp50', 'acp51', 'acp52', 'acp53', 'acp54',
            'acp55', 'acp56', 'acp57', 'acp58', 'acp59', 'acp60',
            'acp61', 'acp62', 'acp63', 'acp64', 'acp65', 'acp66',
            'acp67', 'acp68', 'acp69', 'acp70', 'acp71', 'acp72',
            'acp73', 'acp74', 'acp75', 'acp76', 'acp77', 'acp78',
            'acp79', 'acp80', 'acp81', 'acp82', 'acp83', 'acp84',
            'acp85', 'acp86', 'acp87', 'acp88', 'acp89', 'acp90',
            'acp91', 'acp92', 'acp93', 'acp94', 'acp95', 'acp96',
            'acp97', 'acp98', 'acp99', 'acp100', 'acp101', 'acp102',
            'acp103', 'acp104', 'acp105', 'acp106', 'acp107', 'acp108',
            'acp109', 'acp110', 'acp111', 'acp112', 'acp113', 'acp114',
            'acp115', 'acp116', 'acp117', 'acp118', 'acp119', 'acp120',
            'acp121', 'acp122', 'acp123', 'acp124', 'acp125', 'acp126',
            'acp127', 'acp128', 'acp129', 'acp130', 'acp131', 'acp132',
            'acp133', 'acp134', 'acp135', 'acp136', 'acp137', 'acp138',
            'acp139', 'acp140', 'acp141', 'acp142', 'acp143', 'acp144'
        ]
        self.nvl5_trunk_ports_list = []
        self.network_ports = ['eth0', 'eth1', 'lo']
        self.all_nvl5_ports_list = self.nvl5_access_ports_list + self.nvl5_trunk_ports_list + self.network_ports
        self.nvl5_fnm_ports = ['fnm1', 'fnm2']
        self.nvl5_internal_fnm_ports = ['fnma0p1', 'fnma1p1']
        self.all_fae_nvl5_ports_list = self.all_nvl5_ports_list + self.nvl5_fnm_ports
        self.nvl5_port = ['sw1p1s1']
        self.nvl5_port_speed = '400G'
        self.fnm_link_speed = '100G'
        self.fnm_fae_link_speed = '100G'
        self.nvl5_port_type = 'nvl'
        # will be updated
        self.health_monitor_config_file_path = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(
            "x86_64-nvidia_n5100_ld-r0")
        self.show_platform_output.update({
            "product-name": "N5100_LD",
            "asic-model": self.asic_type,
        })

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2", "FAN5/1", "FAN5/2", "FAN6/1", "FAN6/2"]
        self.fan_led_list = []

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2000, range_max=10000),
            "max-speed": ExpectedString(range_min=20000, range_max=40000)}
        self.platform_inventory_switch_values.update({"hardware-version": None,
                                                      "model": ExpectedString(regex="692-9K36F-00MV-JS0")})


# -------------------------- JulietNonScaleoutNoNCISwitch Switch ----------------------------


class JulietNonScaleoutSwitchNoNCI(JulietNonScaleoutSwitch):

    def __init__(self):
        super().__init__()

    def _init_constants(self):
        super()._init_constants()
        self.nvl5_access_ports_list = [
            'acp1', 'acp2', 'acp3', 'acp4', 'acp5', 'acp6',
            'acp7', 'acp8', 'acp9', 'acp10', 'acp11', 'acp12',
            'acp13', 'acp14', 'acp15', 'acp16', 'acp17', 'acp18',
            'acp19', 'acp20', 'acp21', 'acp22', 'acp23', 'acp24',
            'acp25', 'acp26', 'acp27', 'acp28', 'acp29', 'acp30',
            'acp31', 'acp32', 'acp33', 'acp34', 'acp35', 'acp36',
            'acp37', 'acp38', 'acp39', 'acp40', 'acp41', 'acp42',
            'acp43', 'acp44', 'acp45', 'acp46', 'acp47', 'acp48',
            'acp49', 'acp50', 'acp51', 'acp52', 'acp53', 'acp54',
            'acp55', 'acp56', 'acp57', 'acp58', 'acp59', 'acp60',
            'acp61', 'acp62', 'acp63', 'acp64', 'acp65', 'acp66',
            'acp67', 'acp68', 'acp69', 'acp70', 'acp71', 'acp72',
            'acp73', 'acp74', 'acp75', 'acp76', 'acp77', 'acp78',
            'acp79', 'acp80', 'acp81', 'acp82', 'acp83', 'acp84',
            'acp85', 'acp86', 'acp87', 'acp88', 'acp89', 'acp90',
            'acp91', 'acp92', 'acp93', 'acp94', 'acp95', 'acp96',
            'acp97', 'acp98', 'acp99', 'acp100', 'acp101', 'acp102',
            'acp103', 'acp104', 'acp105', 'acp106', 'acp107', 'acp108',
            'acp109', 'acp110', 'acp111', 'acp112', 'acp113', 'acp114',
            'acp115', 'acp116', 'acp117', 'acp118', 'acp119', 'acp120',
            'acp121', 'acp122', 'acp123', 'acp124', 'acp125', 'acp126',
            'acp127', 'acp128', 'acp129', 'acp130', 'acp131', 'acp132',
            'acp133', 'acp134', 'acp135', 'acp136', 'acp137', 'acp138',
            'acp139', 'acp140', 'acp141', 'acp142', 'acp143', 'acp144'
        ]
        self.nvl5_trunk_ports_list = []
        self.network_ports = ['eth0', 'eth1', 'lo']
        self.all_nvl5_ports_list = self.nvl5_access_ports_list + self.nvl5_trunk_ports_list + self.network_ports
        self.nvl5_fnm_ports = ['fnm1', 'fnm2']
        self.nvl5_internal_fnm_ports = ['fnma0p1', 'fnma1p1']
        self.all_fae_nvl5_ports_list = self.all_nvl5_ports_list + self.nvl5_fnm_ports
        self.nvl5_port = ['sw1p1s1']
        self.nvl5_port_speed = '400G'
        self.fnm_link_speed = '100G'
        self.fnm_fae_link_speed = '100G'
        self.nvl5_port_type = 'nvl'
        # will be updated
        self.health_monitor_config_file_path = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(
            "x86_64-nvidia_n5200_ld-r0")
        self.show_platform_output.update({
            "product-name": "N5200_LD",
            "asic-model": self.asic_type,
        })
        self.voltage_sensors = ['HSC-VinDC-In', 'HSC-VinDC-Out', 'PDB-1-Conv-In-1', 'PDB-1-Conv-Out-1', 'PDB-2-Conv-In-1',
                                'PDB-2-Conv-Out-1', 'PMIC-1-12V-VDD-ASIC1-In-1', 'PMIC-1-ASIC1-VDD-Out-1', 'PMIC-2-12V-HVDD-DVDD-ASIC1-In-1',
                                'PMIC-2-ASIC1-DVDD-PL0-Out-2', 'PMIC-2-ASIC1-HVDD-PL0-Out-1', 'PMIC-3-12V-HVDD-DVDD-ASIC1-In-1',
                                'PMIC-3-ASIC1-DVDD-PL1-Out-2', 'PMIC-3-ASIC1-HVDD-PL1-Out-1', 'PMIC-4-12V-VDD-ASIC2-In-1',
                                'PMIC-4-ASIC2-VDD-Out-1', 'PMIC-5-12V-HVDD-DVDD-ASIC2-In-1', 'PMIC-5-ASIC2-DVDD-PL0-Out-2',
                                'PMIC-5-ASIC2-HVDD-PL0-Out-1', 'PMIC-6-12V-HVDD-DVDD-ASIC2-In-1', 'PMIC-6-ASIC2-DVDD-PL1-Out-2',
                                'PMIC-6-ASIC2-HVDD-PL1-Out-1', 'PMIC-7-12V-MAIN-In-1', 'PMIC-7-CEX-VDD-Out-1',
                                'PMIC-8-COMEX-VDD-MEM-In-1', 'PMIC-8-COMEX-VDD-MEM-Out-1']

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2"]
        self.fan_led_list = []

    def _init_temperature(self):
        super()._init_temperature()
        sensors_to_remove = ['PDB-Conv-3-Temp', 'PDB-Conv-4-Temp']
        for sensor in sensors_to_remove:
            self.temperature_sensors.remove(sensor)

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2000, range_max=10000),
            "max-speed": ExpectedString(range_min=20000, range_max=40000)}
        self.platform_inventory_switch_values.update({"hardware-version": None,
                                                      "model": ExpectedString(regex="692-96099-00MV-JS0")})

# -------------------------- JulietNonScaleoutSwitchNoNCI5600 Switch ----------------------------


class JulietNonScaleoutSwitchNoNCI5600(JulietNonScaleoutSwitchNoNCI):

    def __init__(self):
        super().__init__()

    def _init_constants(self):
        super()._init_constants()
        self.health_monitor_config_file_path = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(
            "x86_64-nvidia_n5600_ld-r0")
        self.show_platform_output.update({
            "product-name": "N5600_LD",
            "asic-model": self.asic_type,
        })

    def _init_fan_list(self):
        super()._init_fan_list()

    def _init_temperature(self):
        super()._init_temperature()

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_inventory_switch_values.update({"hardware-version": None,
                                                      "model": ExpectedString(regex="692-9K33R-00MV-JS0")})

# -------------------------- Caiman Switch ----------------------------


class CaimanSwitch(NvLinkSwitch):

    def __init__(self):
        super().__init__(asic_amount=4)

    def _init_constants(self):
        super()._init_constants()
        self.ib_ports_num = 64
        self.core_count = 4
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-mlnx_mqm9700-r0")


# -------------------------- Marlin Switch ----------------------------
class MarlinSwitch(IbSwitch):

    def __init__(self):
        super().__init__(asic_amount=2)

    def _init_constants(self):
        super()._init_constants()
        self.ib_ports_num = 128
        self.core_count = 4
        self.asic_type = NvosConst.QTM2
        self.primary_asic = f"{IbConsts.DEVICE_ASIC_PREFIX}2"
        self.primary_swid = f"{IbConsts.SWID}1"
        self.primary_ipoib_interface = IbConsts.IPOIB_INT1
        self.secondary_ipoib_interface = IbConsts.IPOIB_INT0
        self.multi_asic_system = True
        del self.show_platform_output['manufacturer']

    def _init_available_databases(self):
        super()._init_available_databases()
        self.available_tables_per_asic[DatabaseConst.APPL_DB_ID] = {"ALIAS_PORT_MAP": self.get_ib_ports_num() / 2}
        self.available_tables.update({'database0': self.available_tables_per_asic,
                                      'database1': self.available_tables_per_asic})

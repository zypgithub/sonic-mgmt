import logging
import os
import time
from collections import namedtuple
from typing import List

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import MultiPlanarConsts, PlatformConsts
from ngts.nvos_constants.constants_nvos import (NvosConst, DatabaseConst, IbConsts, StatsConsts, FansConsts,
                                                DocumentsConsts)
from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ExpectedString
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts
from ngts.tools.test_utils.nvos_general_utils import get_version_info

logger = logging.getLogger()


class IbSwitch(BaseSwitch):

    def __init__(self, asic_amount, switch_type=NvosConst.IB_SWITCH_TYPE):
        super().__init__(switch_type=switch_type, asic_amount=asic_amount)
        self.documents_path = None
        self.documents_files = None
        self._init_sensors_dict()
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
        self.kex_algorithms = ['curve25519-sha256', 'curve25519-sha256@libssh.org', 'diffie-hellman-group16-sha512',
                               'diffie-hellman-group18-sha512', 'diffie-hellman-group14-sha256']

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
        self.platform_file_path = ""
        self.primary_asic = f"{IbConsts.DEVICE_ASIC_PREFIX}1"
        self.primary_swid = f"{IbConsts.SWID}0"
        self.primary_ipoib_interface = IbConsts.IPOIB_INT.format(self.asic_amount - 1)
        self.multi_asic_system = False
        self.login_pattern = NvosConst.INSTALL_SUCCESS_PATTERN
        self.install_patterns = {self.login_pattern: 0}
        self.install_success_patterns = list(self.install_patterns.keys())
        self.mst_dev_name = '/dev/mst/mt54002_pciconf0'  # TODO update
        self.category_list = ['temperature', 'cpu', 'disk', 'power', 'fan', 'mgmt-interface', 'voltage']
        self.category_disk_interval_default = '30'
        self.system_profile_default_values = ['enabled', '2048', 'disabled', 'disabled', '1']
        self.current_bios_version_name = "0ACQF_06.01.005"
        self.current_bios_version_path = "/auto/sw_system_release/sx_mlnx_bios/CoffeeLake/0ACQF_06.01.x05_rc1/Release/0ACQF.cab"
        self.previous_bios_version_name = "0ACQF_06.01.004"
        self.previous_bios_version_path = "/auto/sw_system_release/sx_mlnx_bios/CoffeeLake/0ACQF_06.01.x04_rc1/Release/0ACQF.cab"

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

    def get_ib_ports_num(self):
        return self.ib_ports_num

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
        self.fnm_internal_port_list = ['fnma1p236']
        self.fnm_external_port_list = ['fnm1']
        self.fnm_external_child_port = 'fnm1s1'
        self.child_aggregated_port = 'sw10p1s1'
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
        # DutUtilsTool.check_ssh_for_authentication_error(engine, self)
        return DutUtilsTool.wait_for_nvos_to_become_functional(engine)

    def reload_device(self, engine, cmd_list, validate=False):
        return engine.send_config_set(cmd_list, exit_config_mode=False, cmd_verify=False)

    def get_bios_file_name(self):
        return self.current_bios_version_path.split('/')[-1]


# -------------------------- Gorilla Switch ----------------------------


class GorillaSwitch(IbSwitch):

    def __init__(self, asic_amount=1):
        super().__init__(asic_amount=asic_amount)

    def _init_constants(self):
        IbSwitch._init_constants(self)
        self.core_count = 4
        self.asic_type = NvosConst.QTM2
        self.split_ports_supported = True
        self.profile_change_supported = True
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-mlnx_mqm9700-r0")
        self.show_platform_output.update({
            "product-name": "MQM9700",
            "asic-model": self.asic_type,
        })
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
        self.stats_fan_header_num_of_lines = 25
        self.stats_power_header_num_of_lines = 13
        self.stats_temperature_header_num_of_lines = 53

    def get_mgmt_ports(self) -> List[str]:
        return self.mgmt_ports

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
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_switch_values.update({"hardware-version": None,
                                                      "model": ExpectedString(regex="MQM9700.*")})

    def _init_eth0_speeds(self):
        super()._init_eth0_speeds()
        self.supported_eth0_speeds += ['10M']


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
        super().__init__(asic_amount=4)

    def _init_constants(self):
        self.asic_amount = 4
        super()._init_constants()
        self.ib_ports_num = 72
        self.core_count = 4
        self.asic_type = NvosConst.QTM3
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-mlnx_qm8790-r0")
        self.show_platform_output.update({
            "product-name": "Q3400_RA",
            "asic-model": self.asic_type,
        })

        self.voltage_sensors = [
            "PMIC-1-12V-VDD-ASIC1-In-1", "PMIC-1-ASIC1-VDD-Out-1", "PMIC-2-12V-HVDD-DVDD-ASIC1-In-1",
            "PMIC-2-ASIC1-DVDD-PL0-Out-2", "PMIC-2-ASIC1-HVDD-PL0-Out-1", "PMIC-3-12V-HVDD-DVDD-ASIC1-In-1",
            "PMIC-3-ASIC1-DVDD-PL1-Out-2", "PMIC-3-ASIC1-HVDD-PL1-Out-1", "PMIC-4-12V-VDD-ASIC2-In-1",
            "PMIC-4-ASIC2-VDD-Out-1", "PMIC-5-12V-HVDD-DVDD-ASIC2-In-1", "PMIC-5-ASIC2-DVDD-PL0-Out-2",
            "PMIC-5-ASIC2-HVDD-PL0-Out-1", "PMIC-6-12V-HVDD-DVDD-ASIC2-In-1", "PMIC-6-ASIC2-DVDD-PL1-Out-2",
            "PMIC-6-ASIC2-HVDD-PL1-Out-1", "PMIC-7-12V-VDD-ASIC3-In-1", "PMIC-7-ASIC3-VDD-Out-1",
            "PMIC-8-12V-HVDD-DVDD-ASIC3-In-1", "PMIC-8-ASIC3-DVDD-PL0-Out-2", "PMIC-8-ASIC3-HVDD-PL0-Out-1",
            "PMIC-9-12V-HVDD-DVDD-ASIC3-In-1", "PMIC-9-ASIC3-DVDD-PL1-Out-2", "PMIC-9-ASIC3-HVDD-PL1-Out-1",
            "PMIC-10-12V-VDD-ASIC4-In-1", "PMIC-10-ASIC4-VDD-Out-1", "PMIC-11-12V-HVDD-DVDD-ASIC4-In-1",
            "PMIC-11-ASIC4-DVDD-PL0-Out-2", "PMIC-11-ASIC4-HVDD-PL0-Out-1", "PMIC-12-12V-HVDD-DVDD-ASIC4-In-1",
            "PMIC-12-ASIC4-DVDD-PL1-Out-2", "PMIC-12-ASIC4-HVDD-PL1-Out-1", "PMIC-13-12V-MAIN-In-1",
            "PMIC-13-CEX-VDD-Out-1",
            "PSU-1-12V-Out", "PSU-2-12V-Out", "PSU-3-12V-Out", "PSU-4-12V-Out", "PSU-5-12V-Out", "PSU-6-12V-Out",
            "PSU-7-12V-Out", "PSU-8-12V-Out",
        ]

        self.stats_fan_header_num_of_lines = 17
        self.stats_power_header_num_of_lines = 25
        self.stats_temperature_header_num_of_lines = 104
        self.fnm_link_speed = '800G'

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
        self.temperature_sensors += ["ASIC1", "ASIC2", "ASIC3", "ASIC4", "PSU-7-Temp", "SODIMM-2-Temp"]
        self.temperature_sensors.remove("ASIC")
        self.temperature_sensors.remove("PSU-1-Temp")

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
        self.interface_active_internal_fnm_ports = [port for port in self.interface_fae_list
                                                    if port.startswith('fnm') and not port.endswith('p3')]
        # because other internal fnm ports are unused currently

    def _init_eth0_speeds(self):
        super()._init_eth0_speeds()
        self.supported_eth0_speeds += ['10M']

    def _init_ib_speeds(self):
        super()._init_ib_speeds()
        self.supported_ib_speeds = ("sdr", "hdr", "ndr", "xdr")

    def _relevant_config_filename_by_version(self, version: str) -> str:
        return 'nvos_config_xdr.yml'


# -------------------------- Crocodile Switch ----------------------------
class CrocodileSwitch(IbSwitch):

    def __init__(self):
        super().__init__(asic_amount=2)

    def _init_constants(self):
        super()._init_constants()
        self.ib_ports_num = 64
        self.core_count = 4
        self.split_ports_supported = True
        self.asic_type = NvosConst.QTM3
        self.default_port = 'swA1p1'
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-nvidia_qm3400-r0")
        self.show_platform_output.update({
            "product-name": "QM3400",
            "asic-model": self.asic_type,
        })
        self.mst_dev_name = '/dev/mst/mt54004_pciconf0'  # TODO update
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
        self.stats_fan_header_num_of_lines = 23
        self.system_profile_default_values = ['enabled', '1792', 'enabled', 'disabled', '1']
        self.stats_power_header_num_of_lines = 17
        self.stats_temperature_header_num_of_lines = 69
        self.previous_cpld_version = BaseSwitch.CpldImageConsts(
            burn_image_path="/auto/sw_system_project/NVOS_INFRA/verification_files/cpld_fw/OLD/FUI000273_BURN_CROCODILE_CPLD000232_REV0802_CPLD000357_REV0103_CPLD000358_REV0203_CPLD000359_REV0100.vme",
            refresh_image_path="/auto/sw_system_project/NVOS_INFRA/verification_files/cpld_fw/OLD/FUI000273_REFRESH_CROCODILE_CPLD000232_REV0802_CPLD000357_REV0103_CPLD000358_REV0203_CPLD000359_REV0100.vme",
            version_names={
                "CPLD1": "CPLD000232_REV0802",
                "CPLD2": "CPLD000357_REV0103",
                "CPLD3": "CPLD000358_REV0203",
                "CPLD4": "CPLD000359_REV0100",
            }
        )
        self.current_cpld_version = BaseSwitch.CpldImageConsts(
            burn_image_path="/auto/sw_system_project/NVOS_INFRA/verification_files/cpld_fw/FUI000274_BURN_CROCODILE_CPLD000232_REV0802_CPLD000357_REV0104_CPLD000358_REV0203_CPLD000339_REV0100.vme",
            refresh_image_path="/auto/sw_system_project/NVOS_INFRA/verification_files/cpld_fw/FUI000274_REFRESH_CROCODILE_CPLD000232_REV0802_CPLD000357_REV0104_CPLD000358_REV0203_CPLD000339_REV0100.vme",
            version_names={
                "CPLD1": "CPLD000232_REV0802",
                "CPLD2": "CPLD000357_REV0104",
                "CPLD3": "CPLD000358_REV0203",
                "CPLD4": "CPLD000359_REV0100",
            }
        )
        self.fnm_link_speed = '800G'
        self.interface_list = ['eth0', 'eth1', 'fnm1', 'ib0', 'lo', 'swA10p1', 'swA10p2', 'swA11p1', 'swA11p2',
                               'swA12p1', 'swA12p2', 'swA13p1', 'swA13p2', 'swA14p1', 'swA14p2', 'swA15p1', 'swA15p2',
                               'swA16p1', 'swA16p2', 'swA17p1', 'swA17p2', 'swA18p1', 'swA18p2', 'swA1p1', 'swA1p2',
                               'swA2p1', 'swA2p2', 'swA3p1', 'swA3p2', 'swA4p1', 'swA4p2', 'swA5p1', 'swA5p2', 'swA6p1',
                               'swA6p2', 'swA7p1', 'swA7p2', 'swA8p1', 'swA8p2', 'swA9p1', 'swA9p2', 'swB10p1',
                               'swB10p2', 'swB11p1', 'swB11p2', 'swB12p1', 'swB12p2', 'swB13p1', 'swB13p2', 'swB14p1',
                               'swB14p2', 'swB15p1', 'swB15p2', 'swB16p1', 'swB16p2', 'swB17p1', 'swB17p2', 'swB18p1',
                               'swB18p2', 'swB1p1', 'swB1p2', 'swB2p1', 'swB2p2', 'swB3p1', 'swB3p2', 'swB4p1',
                               'swB4p2', 'swB5p1', 'swB5p2', 'swB6p1', 'swB6p2', 'swB7p1', 'swB7p2', 'swB8p1', 'swB8p2',
                               'swB9p1', 'swB9p2']
        self.interface_fae_list = ['eth0', 'eth1', 'fnm1', 'fnm1pl1', 'fnm1pl2', 'fnma0p1', 'fnma0p2', 'fnma0p3',
                                   'fnma0p4', 'fnma1p1', 'fnma1p2', 'ib0', 'lo', 'swA10p1', 'swA10p1pl1', 'swA10p1pl2',
                                   'swA10p1pl3', 'swA10p1pl4', 'swA10p2', 'swA10p2pl1', 'swA10p2pl2', 'swA10p2pl3',
                                   'swA10p2pl4', 'swA11p1', 'swA11p1pl1', 'swA11p1pl2', 'swA11p1pl3', 'swA11p1pl4',
                                   'swA11p2', 'swA11p2pl1', 'swA11p2pl2', 'swA11p2pl3', 'swA11p2pl4', 'swA12p1',
                                   'swA12p1pl1', 'swA12p1pl2', 'swA12p1pl3', 'swA12p1pl4', 'swA12p2', 'swA12p2pl1',
                                   'swA12p2pl2', 'swA12p2pl3', 'swA12p2pl4', 'swA13p1', 'swA13p1pl1', 'swA13p1pl2',
                                   'swA13p1pl3', 'swA13p1pl4', 'swA13p2', 'swA13p2pl1', 'swA13p2pl2', 'swA13p2pl3',
                                   'swA13p2pl4', 'swA14p1', 'swA14p1pl1', 'swA14p1pl2', 'swA14p1pl3', 'swA14p1pl4',
                                   'swA14p2', 'swA14p2pl1', 'swA14p2pl2', 'swA14p2pl3', 'swA14p2pl4', 'swA15p1',
                                   'swA15p1pl1', 'swA15p1pl2', 'swA15p1pl3', 'swA15p1pl4', 'swA15p2', 'swA15p2pl1',
                                   'swA15p2pl2', 'swA15p2pl3', 'swA15p2pl4', 'swA16p1', 'swA16p1pl1', 'swA16p1pl2',
                                   'swA16p1pl3', 'swA16p1pl4', 'swA16p2', 'swA16p2pl1', 'swA16p2pl2', 'swA16p2pl3',
                                   'swA16p2pl4', 'swA17p1', 'swA17p1pl1', 'swA17p1pl2', 'swA17p1pl3', 'swA17p1pl4',
                                   'swA17p2', 'swA17p2pl1', 'swA17p2pl2', 'swA17p2pl3', 'swA17p2pl4', 'swA18p1',
                                   'swA18p1pl1', 'swA18p1pl2', 'swA18p1pl3', 'swA18p1pl4', 'swA18p2', 'swA18p2pl1',
                                   'swA18p2pl2', 'swA18p2pl3', 'swA18p2pl4', 'swA1p1', 'swA1p1pl1', 'swA1p1pl2',
                                   'swA1p1pl3', 'swA1p1pl4', 'swA1p2', 'swA1p2pl1', 'swA1p2pl2', 'swA1p2pl3',
                                   'swA1p2pl4', 'swA2p1', 'swA2p1pl1', 'swA2p1pl2', 'swA2p1pl3', 'swA2p1pl4',
                                   'swA2p2', 'swA2p2pl1', 'swA2p2pl2', 'swA2p2pl3', 'swA2p2pl4', 'swA3p1', 'swA3p1pl1',
                                   'swA3p1pl2', 'swA3p1pl3', 'swA3p1pl4', 'swA3p2', 'swA3p2pl1', 'swA3p2pl2',
                                   'swA3p2pl3', 'swA3p2pl4', 'swA4p1', 'swA4p1pl1', 'swA4p1pl2', 'swA4p1pl3',
                                   'swA4p1pl4', 'swA4p2', 'swA4p2pl1', 'swA4p2pl2', 'swA4p2pl3', 'swA4p2pl4', 'swA5p1',
                                   'swA5p1pl1', 'swA5p1pl2', 'swA5p1pl3', 'swA5p1pl4', 'swA5p2', 'swA5p2pl1',
                                   'swA5p2pl2', 'swA5p2pl3', 'swA5p2pl4', 'swA6p1', 'swA6p1pl1', 'swA6p1pl2',
                                   'swA6p1pl3', 'swA6p1pl4', 'swA6p2', 'swA6p2pl1', 'swA6p2pl2', 'swA6p2pl3',
                                   'swA6p2pl4', 'swA7p1', 'swA7p1pl1', 'swA7p1pl2', 'swA7p1pl3', 'swA7p1pl4', 'swA7p2',
                                   'swA7p2pl1', 'swA7p2pl2', 'swA7p2pl3', 'swA7p2pl4', 'swA8p1', 'swA8p1pl1',
                                   'swA8p1pl2', 'swA8p1pl3', 'swA8p1pl4', 'swA8p2', 'swA8p2pl1', 'swA8p2pl2',
                                   'swA8p2pl3', 'swA8p2pl4', 'swA9p1', 'swA9p1pl1', 'swA9p1pl2', 'swA9p1pl3',
                                   'swA9p1pl4', 'swA9p2', 'swA9p2pl1', 'swA9p2pl2', 'swA9p2pl3', 'swA9p2pl4', 'swB10p1',
                                   'swB10p1pl1', 'swB10p1pl2', 'swB10p1pl3', 'swB10p1pl4', 'swB10p2', 'swB10p2pl1',
                                   'swB10p2pl2', 'swB10p2pl3', 'swB10p2pl4', 'swB11p1', 'swB11p1pl1', 'swB11p1pl2',
                                   'swB11p1pl3', 'swB11p1pl4', 'swB11p2', 'swB11p2pl1', 'swB11p2pl2', 'swB11p2pl3',
                                   'swB11p2pl4', 'swB12p1', 'swB12p1pl1', 'swB12p1pl2', 'swB12p1pl3', 'swB12p1pl4',
                                   'swB12p2', 'swB12p2pl1', 'swB12p2pl2', 'swB12p2pl3', 'swB12p2pl4', 'swB13p1',
                                   'swB13p1pl1', 'swB13p1pl2', 'swB13p1pl3', 'swB13p1pl4', 'swB13p2', 'swB13p2pl1',
                                   'swB13p2pl2', 'swB13p2pl3', 'swB13p2pl4', 'swB14p1', 'swB14p1pl1', 'swB14p1pl2',
                                   'swB14p1pl3', 'swB14p1pl4', 'swB14p2', 'swB14p2pl1', 'swB14p2pl2', 'swB14p2pl3',
                                   'swB14p2pl4', 'swB15p1', 'swB15p1pl1', 'swB15p1pl2', 'swB15p1pl3', 'swB15p1pl4',
                                   'swB15p2', 'swB15p2pl1', 'swB15p2pl2', 'swB15p2pl3', 'swB15p2pl4', 'swB16p1',
                                   'swB16p1pl1', 'swB16p1pl2', 'swB16p1pl3', 'swB16p1pl4', 'swB16p2', 'swB16p2pl1',
                                   'swB16p2pl2', 'swB16p2pl3', 'swB16p2pl4', 'swB17p1', 'swB17p1pl1', 'swB17p1pl2',
                                   'swB17p1pl3', 'swB17p1pl4', 'swB17p2', 'swB17p2pl1', 'swB17p2pl2', 'swB17p2pl3',
                                   'swB17p2pl4', 'swB18p1', 'swB18p1pl1', 'swB18p1pl2', 'swB18p1pl3', 'swB18p1pl4',
                                   'swB18p2', 'swB18p2pl1', 'swB18p2pl2', 'swB18p2pl3', 'swB18p2pl4', 'swB1p1',
                                   'swB1p1pl1', 'swB1p1pl2', 'swB1p1pl3', 'swB1p1pl4', 'swB1p2', 'swB1p2pl1',
                                   'swB1p2pl2', 'swB1p2pl3', 'swB1p2pl4', 'swB2p1', 'swB2p1pl1', 'swB2p1pl2',
                                   'swB2p1pl3', 'swB2p1pl4', 'swB2p2', 'swB2p2pl1', 'swB2p2pl2', 'swB2p2pl3',
                                   'swB2p2pl4', 'swB3p1', 'swB3p1pl1', 'swB3p1pl2', 'swB3p1pl3', 'swB3p1pl4', 'swB3p2',
                                   'swB3p2pl1', 'swB3p2pl2', 'swB3p2pl3', 'swB3p2pl4', 'swB4p1', 'swB4p1pl1',
                                   'swB4p1pl2', 'swB4p1pl3', 'swB4p1pl4', 'swB4p2', 'swB4p2pl1', 'swB4p2pl2',
                                   'swB4p2pl3', 'swB4p2pl4', 'swB5p1', 'swB5p1pl1', 'swB5p1pl2', 'swB5p1pl3',
                                   'swB5p1pl4', 'swB5p2', 'swB5p2pl1', 'swB5p2pl2', 'swB5p2pl3', 'swB5p2pl4', 'swB6p1',
                                   'swB6p1pl1', 'swB6p1pl2', 'swB6p1pl3', 'swB6p1pl4', 'swB6p2', 'swB6p2pl1',
                                   'swB6p2pl2', 'swB6p2pl3', 'swB6p2pl4', 'swB7p1', 'swB7p1pl1', 'swB7p1pl2',
                                   'swB7p1pl3', 'swB7p1pl4', 'swB7p2', 'swB7p2pl1', 'swB7p2pl2', 'swB7p2pl3',
                                   'swB7p2pl4', 'swB8p1', 'swB8p1pl1', 'swB8p1pl2', 'swB8p1pl3', 'swB8p1pl4', 'swB8p2',
                                   'swB8p2pl1', 'swB8p2pl2', 'swB8p2pl3', 'swB8p2pl4', 'swB9p1', 'swB9p1pl1',
                                   'swB9p1pl2', 'swB9p1pl3', 'swB9p1pl4', 'swB9p2', 'swB9p2pl1', 'swB9p2pl2',
                                   'swB9p2pl3', 'swB9p2pl4']

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
        self.temperature_sensors += ["ASIC1", "ASIC2", "PSU-3-Temp", "PSU-4-Temp", "PMIC-2-Temp", "PMIC-7-Temp"]
        self.temperature_sensors.remove("ASIC")

    def _init_eth0_speeds(self):
        super()._init_eth0_speeds()
        self.supported_eth0_speeds += ['10M']

    def _relevant_config_filename_by_version(self, version: str) -> str:
        return 'nvos_config_xdr.yml'

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
        self.interface_active_internal_fnm_ports = ['fnma0p1', 'fnma1p1']


# -------------------------- Crocodile Simx Switch ----------------------------
class CrocodileSimxSwitch(IbSwitch):

    def __init__(self):
        super().__init__(asic_amount=1)


# -------------------------- NvLink Switch ----------------------------
class NvLinkSwitch(IbSwitch):

    def __init__(self, asic_amount):
        super().__init__(switch_type="NVL", asic_amount=asic_amount)

    def _init_constants(self):
        super()._init_constants()
        self.ib_ports_num = 64
        self.core_count = 4
        self.mgmt_ports = ['eth0', 'eth1']
        self.asic_type = NvosConst.QTM3
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-mlnx_mqm9700-r0")

    def get_mgmt_ports(self) -> List[str]:
        return self.mgmt_ports


# -------------------------- Juliet Switch ----------------------------


class JulietSwitch(NvLinkSwitch):
    FaeImagesTestConsts = namedtuple('FaeImagesTestConsts', ('current_image_version', 'alternate_image_version'))

    def __init__(self, asic_amount):
        super().__init__(asic_amount=asic_amount)

    def show_setup_versions(self, dut_engine: LinuxSshEngine = None):
        get_bmc_version_cmd = 'curl -k -u root:{} -X GET https://10.0.1.1/redfish/v1/UpdateService/FirmwareInventory/MGX_FW_BMC_0'
        psws = ['0penBmc', 'Test123!', 'ABYX12#14artb']
        outputs = {
            'system version': dut_engine.run_cmd('nv show system version'),
            'platform firmware': dut_engine.run_cmd('nv show platform firmware'),
        }
        for i, pw in enumerate(psws):
            outputs[f'bmc version {i} (redfish)'] = dut_engine.run_cmd(get_bmc_version_cmd.format(pw))
        res = [f'{title.upper()}:\n{output}\n' for title, output in outputs.items()]
        return '\n'.join(res)

    def _init_constants(self):
        super()._init_constants()
        self.bmc_image_info = self.FaeImagesTestConsts(current_image_version='bmc_1.pkg', alternate_image_version='bmc_2.pkg')
        self.fpga_image_info = self.FaeImagesTestConsts(current_image_version='fpga_1.pkg', alternate_image_version='fpga_2.pkg')
        self.current_bios_version_name = "0ACTV_00.00.x07_rc5"
        self.current_bios_version_path = "/auto/sw_system_release/sx_mlnx_bios/SnowyOwl/0ACTV_00.00.x07_rc5/Release/0ACTV.rom"
        self.previous_bios_version_name = "0ACTV_00.00.x07_rc4"
        self.previous_bios_version_path = "/auto/sw_system_release/sx_mlnx_bios/SnowyOwl/0ACTV_00.00.x07_rc4/Release/0ACTV.rom"

    def _init_fan_list(self):
        super()._init_fan_list()

    def _init_led_list(self):
        self.led_list = ['FAN1', 'FAN2', 'FAN3', 'FAN4', 'FAN5', 'FAN6', "STATUS", "UID"]


# -------------------------- JulietScaleout Switch ----------------------------
class JulietScaleoutSwitch(JulietSwitch):

    def __init__(self):
        super().__init__(asic_amount=2)

    def _init_constants(self):
        super()._init_constants()
        self.reboot_type = 'julietscaleout_reboot'
        self.core_count = 8
        self.constants.firmware.extend([PlatformConsts.FW_FPGA, PlatformConsts.FW_BMC])
        self.ssd_image = None
        self.category_list = ['temperature', 'cpu', 'disk', 'fan', 'mgmt-interface', 'voltage']
        self.voltage_sensors = [
            "HSC-VinDC-In",
            "HSC-VinDC-Out",
            "PDB-1-Conv-In-1",
            "PDB-1-Conv-Out-1",
            "PDB-2-Conv-In-1",
            "PDB-2-Conv-Out-1",
            "PDB-3-Conv-In-1",
            "PDB-3-Conv-Out-1",
            "PDB-4-Conv-In-1",
            "PDB-4-Conv-Out-1",
            "PMIC-1-12V-VDD-ASIC1-In-1",
            "PMIC-1-ASIC1-VDD-Out-1",
            "PMIC-2-12V-HVDD-DVDD-ASIC1-In-1",
            "PMIC-2-ASIC1-DVDD-PL0-Out-2",
            "PMIC-2-ASIC1-HVDD-PL0-Out-1",
            "PMIC-3-12V-HVDD-DVDD-ASIC1-In-1",
            "PMIC-3-ASIC1-DVDD-PL1-Out-2",
            "PMIC-3-ASIC1-HVDD-PL1-Out-1",
            "PMIC-4-12V-VDD-ASIC2-In-1",
            "PMIC-4-ASIC2-VDD-Out-1",
            "PMIC-5-12V-HVDD-DVDD-ASIC2-In-1",
            "PMIC-5-ASIC2-DVDD-PL0-Out-2",
            "PMIC-5-ASIC2-HVDD-PL0-Out-1",
            "PMIC-6-12V-HVDD-DVDD-ASIC2-In-1",
            "PMIC-6-ASIC2-DVDD-PL1-Out-2",
            "PMIC-6-ASIC2-HVDD-PL1-Out-1",
            "PMIC-7-12V-MAIN-In-1",
            "PMIC-7-CEX-VDD-Out-1",
            "PMIC-8-COMEX-VDD-MEM-In-1",
            "PMIC-8-COMEX-VDD-MEM-Out-1"
        ]
        # TBD
        self.show_platform_output.update({
            "product-name": "N5110_LD",
            "asic-model": self.asic_type,
        })
        self.current_bios_version_name = "0ACTV_0.00.007"
        self.current_bios_version_path = "/auto/sw_system_release/sx_mlnx_bios/SnowyOwl/BringUp/0ACTV000_07_BU3/Release/0ACTV000_07.rom"
        self.previous_bios_version_name = "0ACTV_0.00.007"
        self.previous_bios_version_path = "/auto/sw_system_release/sx_mlnx_bios/SnowyOwl/BringUp/0ACTV000_07_BU3/Release/0ACTV000_07.rom"
        self.bios_version_name = '0ACTV000_07.rom'

        self.current_cpld_version = BaseSwitch.CpldImageConsts(
            burn_image_path="/auto/sysgwork/eabboud/Juliet_CPLD_updated_26_05_24.vme",
            refresh_image_path="/auto/sysgwork/eabboud/Juliet_CPLD_updated_26_05_24.vme",
            version_names={
                "CPLD1": "CPLD000370_REV0010",
                "CPLD2": "CPLD000371_REV0010",
                "CPLD3": "CPLD000373_REV0009",
                "CPLD4": "CPLD000372_REV0002"
            }
        )
        self.previous_cpld_version = BaseSwitch.CpldImageConsts(
            burn_image_path="/auto/sysgwork/eabboud/Juliet_CPLD_updated_26_05_24.vme",
            refresh_image_path="/auto/sysgwork/eabboud/Juliet_CPLD_updated_26_05_24.vme",
            version_names={
                "CPLD1": "CPLD000370_REV0010",
                "CPLD2": "CPLD000371_REV0010",
                "CPLD3": "CPLD000373_REV0009",
                "CPLD4": "CPLD000372_REV0002"
            }
        )
        # self.stats_fan_header_num_of_lines = 25
        # self.stats_power_header_num_of_lines = 13
        # self.stats_temperature_header_num_of_lines = 53
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
        self.nvl5_fnm_ports = ['fnm1', 'fnm2', 'fnma0p1', 'fnma1p1']
        self.all_fae_nvl5_ports_list = self.all_nvl5_ports_list + self.nvl5_fnm_ports
        self.nvl5_port = ['sw1p1s1']
        self.nvl5_port_speed = '400G'
        self.nvl5_port_type = 'nvl'
        # will be updated

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors = ["ASIC", "Ambient-Port-Side-Temp",
                                    "CPU-Core-0-Temp", "CPU-Core-1-Temp", "CPU-Core-2-Temp", "CPU-Core-3-Temp",
                                    "swb_asic1", "swb_asic2", "SODIMM-1-Temp"]

    def _init_fan_list(self):
        super()._init_fan_list()
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
                                                      "model": ExpectedString(regex="N5110_LD.*")})

    def sleep_after_system_reboot(self):
        logger.info("Sleeping for 80 seconds - Reboot takes longer on juliet for now")
        time.sleep(80)

    def _relevant_config_filename_by_version(self, version: str) -> str:
        return 'nvos_config_nvl5.yml'

    def wait_for_os_to_become_functional(self, engine, find_prompt_tries=60, find_prompt_delay=10):
        logger.info("Sleeping for 300 seconds - Since bios update on juliet enters ONIE Update menu and takes longer")
        time.sleep(300)
        DutUtilsTool.check_ssh_for_authentication_error(engine, self)
        return DutUtilsTool.wait_for_nvos_to_become_functional(engine)

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

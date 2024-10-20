import logging
import os
import time
from collections import namedtuple
from typing import List, Dict

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import MultiPlanarConsts, PlatformConsts, HealthConsts, \
    ActionConsts
from ngts.nvos_constants.constants_nvos import (NvosConst, DatabaseConst, IbConsts, StatsConsts, FansConsts,
                                                DocumentsConsts)
from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.tests_nvos.cluster.cluster_consts import ClusterConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.infra.ValidationTool import ExpectedString
from ngts.nvos_tools.system.Spdm import SPDMComponents
from ngts.tests_nvos.constants import MINUTE
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
        self.init_documents_consts()
        self.init_cli_coverage_prop("nvos")

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

    def _init_ib_speeds(self):
        self.invalid_ib_speeds = {'qdr': '40G'}
        self.supported_ib_speeds = {'hdr': '200G', 'edr': '100G', 'fdr': '56G', 'sdr': '10G', 'ndr': '400G'}

    def _init_eth0_speeds(self):
        self.supported_eth0_speeds = ['100M', '1G']

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
        self.health_monitor_config_file_path = ""
        self.platform_file_path = ""
        self.ib_ports_num = 64
        self.primary_asic = f"{IbConsts.DEVICE_ASIC_PREFIX}1"
        self.primary_swid = f"{IbConsts.SWID}0"
        self.primary_ipoib_interface = IbConsts.IPOIB_INT0
        self.multi_asic_system = False
        self.login_pattern = NvosConst.INSTALL_SUCCESS_PATTERN
        self.install_patterns = {self.login_pattern: 0}
        self.install_success_patterns = list(self.install_patterns.keys())
        self.mst_dev_name = '/dev/mst/mt54002_pciconf0'  # TODO update
        self.category_list = ['temperature', 'cpu', 'disk', 'power', 'fan', 'mgmt-interface', 'voltage']
        self.category_disk_interval_default = '30'
        self.system_profile_default_values = ['enabled', '2048', 'disabled', 'disabled', '1']
        self.bios_image_info = BaseSwitch.BiosImagesConsts(
            current_version={
                'path': "/auto/sw_system_release/sx_mlnx_bios/CoffeeLake/0ACQF_06.01.x05_rc1/Release/0ACQF.cab",
                'filename': '0ACQF.cab',
                'version_name': '0ACQF_06.01.005',
                'date': '04/28/2024'},
            alternate_version={
                'path': '/auto/sw_system_release/sx_mlnx_bios/CoffeeLake/0ACQF_06.01.x04_rc1/Release/0ACQF.cab',
                'filename': '0ACQF.cab',
                'version_name': '0ACQF_06.01.004',
                'date': '11/12/2023'})
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
        self.fnm_plane_port_list = ['fnm1pl1', 'fnm1pl2']  # total 2 ports
        self.network_ports = ['eth0', 'ib0', 'lo']  # total 3 ports
        self.non_aggregated_port_list = ['sw10p1', 'sw10p2', 'sw11p1', 'sw11p2', 'sw12p1', 'sw12p2', 'sw13p1', 'sw13p2',
                                         'sw14p1', 'sw14p2', 'sw15p1', 'sw15p2', 'sw16p1', 'sw16p2', 'sw17p1', 'sw17p2',
                                         'sw18p1', 'sw18p2', 'sw19p1', 'sw19p2', 'sw20p1', 'sw20p2', 'sw21p1', 'sw21p2',
                                         'sw22p1', 'sw22p2', 'sw23p1', 'sw23p2', 'sw24p1', 'sw24p2', 'sw25p1', 'sw25p2',
                                         'sw26p1', 'sw26p2', 'sw27p1', 'sw27p2', 'sw28p1', 'sw28p2', 'sw29p1', 'sw29p2',
                                         'sw30p1', 'sw3p1', 'sw3p2', 'sw4p1', 'sw4p2', 'sw5p1', 'sw5p2', 'sw6p1',
                                         'sw6p2',
                                         'sw7p1', 'sw7p2', 'sw8p1', 'sw8p2', 'sw9p1', 'sw9p2']  # total 55 ports
        self.all_plane_port_list = ['sw1p1pl1', 'sw1p1pl2', 'sw2p1pl1', 'sw2p1pl2', 'sw32p1pl1', 'sw32p1pl2']
        self.all_port_list = self.non_aggregated_port_list + self.aggregated_port_list + self.fnm_external_port_list
        self.all_port_list += self.fnm_external_port_list + self.network_ports
        self.fnm_link_speed = '400G'
        # TODO, ADD MORE PORTS, WE WANT IT TO BE MORE REALISTIC. MAYBE WE CAN USE THE FULL LIST OF ALL PORTS FOR NVL5
        self.fnm_port_type = 'fnm'
        self.all_fae_port_list = self.all_port_list + self.all_plane_port_list + self.fnm_plane_port_list
        self.asic0 = 'asic0'
        self.asic1 = 'asic1'
        self.counters_db_name = 'COUNTERS_DB'
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

    def wait_for_os_to_become_functional(self, engine, find_prompt_tries=60, find_prompt_delay=10):
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
        self.mgmt_ports = ['eth0']
        self.asic_type = NvosConst.QTM2
        self.health_monitor_config_file_path = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(
            "x86_64-mlnx_mqm9700-r0")
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-mlnx_mqm9700-r0")
        self.show_platform_output.update({
            "product-name": "MQM9700",
            "asic-model": self.asic_type,
        })
        self.asic_version = BaseSwitch.AsicImageConsts(
            version="31_2014_1462",
            filename="fw-QTM2-rel-31_2014_1462.mfa"
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
        self.stats_fan_header_num_of_lines = 25
        self.stats_cpu_header_num_of_lines = 10
        self.stats_temperature_header_num_of_lines = 53
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
        self.mgmt_ports = ['eth0']
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
        self.ib_ports_num = 64
        self.core_count = 4
        self.mgmt_ports = ['eth0']  # 'eth1' disabled for now
        self.asic_type = NvosConst.QTM3
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-mlnx_qm8790-r0")
        self.show_platform_output.update({
            "product-name": "Q3400_RA",
            "asic-model": self.asic_type,
        })
        self.asic_version = BaseSwitch.AsicImageConsts(
            version="35.2014.2012",
            filename="fw-QTM3-rel-35_2014_2012.mfa"
        )
        self.voltage_sensors = ["PMIC-1+12V_VDD_ASIC1+Vol+In+1", "PMIC-1+ASIC1_VDD+Vol+Out+1",
                                "PMIC-2+12V_HVDD_DVDD_ASIC1+Vol+In+1", "PMIC-2+ASIC1_DVDD_PL0+Vol+Out+2",
                                "PMIC-2+ASIC1_HVDD_PL0+Vol+Out+1", "PMIC-3+12V_HVDD_DVDD_ASIC1+Vol+In+1",
                                "PMIC-3+ASIC1_DVDD_PL1+Vol+Out+2", "PMIC-3+ASIC1_HVDD_PL1+Vol+Out+1",
                                "PMIC-4+12V_VDD_ASIC2+Vol+In+1", "PMIC-4+ASIC2_VDD+Vol+Out+1",
                                "PMIC-5+12V_HVDD_DVDD_ASIC2+Vol+In+1", "PMIC-5+ASIC2_DVDD_PL0+Vol+Out+2",
                                "PMIC-5+ASIC2_HVDD_PL0+Vol+Out+1", "PMIC-6+12V_HVDD_DVDD_ASIC2+Vol+In+1",
                                "PMIC-6+ASIC2_DVDD_PL1+Vol+Out+2", "PMIC-6+ASIC2_HVDD_PL1+Vol+Out+1",
                                "PMIC-7+12V_VDD_ASIC3+Vol+In+1", "PMIC-7+ASIC3_VDD+Vol+Out+1",
                                "PMIC-8+12V_HVDD_DVDD_ASIC3+Vol+In+1", "PMIC-8+ASIC3_DVDD_PL0+Vol+Out+2",
                                "PMIC-8+ASIC3_HVDD_PL0+Vol+Out+1", "PMIC-9+12V_HVDD_DVDD_ASIC3+Vol+In+1",
                                "PMIC-9+ASIC3_DVDD_PL1+Vol+Out+2", "PMIC-9+ASIC3_HVDD_PL1+Vol+Out+1",
                                "PMIC-10+12V_VDD_ASIC4+Vol+In+1", "PMIC-10+ASIC4_VDD+Vol+Out+1",
                                "PMIC-11+12V_HVDD_DVDD_ASIC4+Vol+In+1", "PMIC-11+ASIC4_DVDD_PL0+Vol+Out+2",
                                "PMIC-11+ASIC4_HVDD_PL0+Vol+Out+1", "PMIC-12+12V_HVDD_DVDD_ASIC4+Vol+In+1",
                                "PMIC-12+ASIC4_DVDD_PL1+Vol+Out+2", "PMIC-12+ASIC4_HVDD_PL1+Vol+Out+1",
                                "PMIC-13+12V_MAIN+Vol+In+1", "PMIC-13+CEX_VDD+Vol+Out+1", "PSU-1+12V+Vol+Out",
                                "PSU-2+12V+Vol+Out", "PSU-3+12V+Vol+Out", "PSU-4+12V+Vol+Out", "PSU-5+12V+Vol+Out",
                                "PSU-6+12V+Vol+Out", "PSU-7+12V+Vol+Out", "PSU-8+12V+Vol+Out"]

        self.stats_fan_header_num_of_lines = 17
        self.stats_cpu_header_num_of_lines = 12
        self.stats_temperature_header_num_of_lines = 104
        self.fnm_link_speed = '800G'
        self.interface_list = ['eth0', 'eth1', 'fnm1', 'ib0', 'lo', 'sw10p1', 'sw10p2', 'sw11p1', 'sw11p2', 'sw12p1',
                               'sw12p2', 'sw13p1', 'sw13p2', 'sw14p1', 'sw14p2', 'sw15p1', 'sw15p2', 'sw16p1', 'sw16p2',
                               'sw17p1', 'sw17p2', 'sw18p1', 'sw18p2', 'sw19p1', 'sw19p2', 'sw1p1', 'sw1p2', 'sw20p1',
                               'sw20p2', 'sw21p1', 'sw21p2', 'sw22p1', 'sw22p2', 'sw23p1', 'sw23p2', 'sw24p1', 'sw24p2',
                               'sw25p1', 'sw25p2', 'sw26p1', 'sw26p2', 'sw27p1', 'sw27p2', 'sw28p1', 'sw28p2', 'sw29p1',
                               'sw29p2', 'sw2p1', 'sw2p2', 'sw30p1', 'sw30p2', 'sw31p1', 'sw31p2', 'sw32p1', 'sw32p2',
                               'sw33p1', 'sw33p2', 'sw34p1', 'sw34p2', 'sw35p1', 'sw35p2', 'sw36p1', 'sw36p2', 'sw37p1',
                               'sw37p2', 'sw38p1', 'sw38p2', 'sw39p1', 'sw39p2', 'sw3p1', 'sw3p2', 'sw40p1', 'sw40p2',
                               'sw41p1', 'sw41p2', 'sw42p1', 'sw42p2', 'sw43p1', 'sw43p2', 'sw44p1', 'sw44p2', 'sw45p1',
                               'sw45p2', 'sw46p1', 'sw46p2', 'sw47p1', 'sw47p2', 'sw48p1', 'sw48p2', 'sw49p1', 'sw49p2',
                               'sw4p1', 'sw4p2', 'sw50p1', 'sw50p2', 'sw51p1', 'sw51p2', 'sw52p1', 'sw52p2', 'sw53p1',
                               'sw53p2', 'sw54p1', 'sw54p2', 'sw55p1', 'sw55p2', 'sw56p1', 'sw56p2', 'sw57p1', 'sw57p2',
                               'sw58p1', 'sw58p2', 'sw59p1', 'sw59p2', 'sw5p1', 'sw5p2', 'sw60p1', 'sw60p2', 'sw61p1',
                               'sw61p2', 'sw62p1', 'sw62p2', 'sw63p1', 'sw63p2', 'sw64p1', 'sw64p2', 'sw65p1', 'sw65p2',
                               'sw66p1', 'sw66p2', 'sw67p1', 'sw67p2', 'sw68p1', 'sw68p2', 'sw69p1', 'sw69p2', 'sw6p1',
                               'sw6p2', 'sw70p1', 'sw70p2', 'sw71p1', 'sw71p2', 'sw72p1', 'sw72p2', 'sw7p1', 'sw7p2',
                               'sw8p1', 'sw8p2', 'sw9p1', 'sw9p2']
        self.interface_fae_list = ['eth0', 'eth1', 'fnm1', 'fnm1pl1', 'fnm1pl2', 'fnm1pl3', 'fnm1pl4', 'fnma1p1',
                                   'fnma1p2', 'fnma1p3', 'fnma2p1', 'fnma2p2', 'fnma2p3', 'fnma3p1', 'fnma3p2',
                                   'fnma3p3', 'fnma4p1', 'fnma4p2', 'fnma4p3', 'ib0', 'lo', 'sw10p1', 'sw10p1pl1',
                                   'sw10p1pl2', 'sw10p1pl3', 'sw10p1pl4', 'sw10p2', 'sw10p2pl1', 'sw10p2pl2',
                                   'sw10p2pl3', 'sw10p2pl4', 'sw11p1', 'sw11p1pl1', 'sw11p1pl2', 'sw11p1pl3',
                                   'sw11p1pl4', 'sw11p2', 'sw11p2pl1', 'sw11p2pl2', 'sw11p2pl3', 'sw11p2pl4', 'sw12p1',
                                   'sw12p1pl1', 'sw12p1pl2', 'sw12p1pl3', 'sw12p1pl4', 'sw12p2', 'sw12p2pl1',
                                   'sw12p2pl2', 'sw12p2pl3', 'sw12p2pl4', 'sw13p1', 'sw13p1pl1', 'sw13p1pl2',
                                   'sw13p1pl3', 'sw13p1pl4', 'sw13p2', 'sw13p2pl1', 'sw13p2pl2', 'sw13p2pl3',
                                   'sw13p2pl4', 'sw14p1', 'sw14p1pl1', 'sw14p1pl2', 'sw14p1pl3', 'sw14p1pl4', 'sw14p2',
                                   'sw14p2pl1', 'sw14p2pl2', 'sw14p2pl3', 'sw14p2pl4', 'sw15p1', 'sw15p1pl1',
                                   'sw15p1pl2', 'sw15p1pl3', 'sw15p1pl4', 'sw15p2', 'sw15p2pl1', 'sw15p2pl2',
                                   'sw15p2pl3', 'sw15p2pl4', 'sw16p1', 'sw16p1pl1', 'sw16p1pl2', 'sw16p1pl3',
                                   'sw16p1pl4', 'sw16p2', 'sw16p2pl1', 'sw16p2pl2', 'sw16p2pl3', 'sw16p2pl4', 'sw17p1',
                                   'sw17p1pl1', 'sw17p1pl2', 'sw17p1pl3', 'sw17p1pl4', 'sw17p2', 'sw17p2pl1',
                                   'sw17p2pl2', 'sw17p2pl3', 'sw17p2pl4', 'sw18p1', 'sw18p1pl1', 'sw18p1pl2',
                                   'sw18p1pl3', 'sw18p1pl4', 'sw18p2', 'sw18p2pl1', 'sw18p2pl2', 'sw18p2pl3',
                                   'sw18p2pl4', 'sw19p1', 'sw19p1pl1', 'sw19p1pl2', 'sw19p1pl3', 'sw19p1pl4', 'sw19p2',
                                   'sw19p2pl1', 'sw19p2pl2', 'sw19p2pl3', 'sw19p2pl4', 'sw1p1', 'sw1p1pl1', 'sw1p1pl2',
                                   'sw1p1pl3', 'sw1p1pl4', 'sw1p2', 'sw1p2pl1', 'sw1p2pl2', 'sw1p2pl3', 'sw1p2pl4',
                                   'sw20p1', 'sw20p1pl1', 'sw20p1pl2', 'sw20p1pl3', 'sw20p1pl4', 'sw20p2', 'sw20p2pl1',
                                   'sw20p2pl2', 'sw20p2pl3', 'sw20p2pl4', 'sw21p1', 'sw21p1pl1', 'sw21p1pl2',
                                   'sw21p1pl3', 'sw21p1pl4', 'sw21p2', 'sw21p2pl1', 'sw21p2pl2', 'sw21p2pl3',
                                   'sw21p2pl4', 'sw22p1', 'sw22p1pl1', 'sw22p1pl2', 'sw22p1pl3', 'sw22p1pl4', 'sw22p2',
                                   'sw22p2pl1', 'sw22p2pl2', 'sw22p2pl3', 'sw22p2pl4', 'sw23p1', 'sw23p1pl1',
                                   'sw23p1pl2', 'sw23p1pl3', 'sw23p1pl4', 'sw23p2', 'sw23p2pl1', 'sw23p2pl2',
                                   'sw23p2pl3', 'sw23p2pl4', 'sw24p1', 'sw24p1pl1', 'sw24p1pl2', 'sw24p1pl3',
                                   'sw24p1pl4', 'sw24p2', 'sw24p2pl1', 'sw24p2pl2', 'sw24p2pl3', 'sw24p2pl4', 'sw25p1',
                                   'sw25p1pl1', 'sw25p1pl2', 'sw25p1pl3', 'sw25p1pl4', 'sw25p2', 'sw25p2pl1',
                                   'sw25p2pl2', 'sw25p2pl3', 'sw25p2pl4', 'sw26p1', 'sw26p1pl1', 'sw26p1pl2',
                                   'sw26p1pl3', 'sw26p1pl4', 'sw26p2', 'sw26p2pl1', 'sw26p2pl2', 'sw26p2pl3',
                                   'sw26p2pl4', 'sw27p1', 'sw27p1pl1', 'sw27p1pl2', 'sw27p1pl3', 'sw27p1pl4', 'sw27p2',
                                   'sw27p2pl1', 'sw27p2pl2', 'sw27p2pl3', 'sw27p2pl4', 'sw28p1', 'sw28p1pl1',
                                   'sw28p1pl2', 'sw28p1pl3', 'sw28p1pl4', 'sw28p2', 'sw28p2pl1', 'sw28p2pl2',
                                   'sw28p2pl3', 'sw28p2pl4', 'sw29p1', 'sw29p1pl1', 'sw29p1pl2', 'sw29p1pl3',
                                   'sw29p1pl4', 'sw29p2', 'sw29p2pl1', 'sw29p2pl2', 'sw29p2pl3', 'sw29p2pl4', 'sw2p1',
                                   'sw2p1pl1', 'sw2p1pl2', 'sw2p1pl3', 'sw2p1pl4', 'sw2p2', 'sw2p2pl1', 'sw2p2pl2',
                                   'sw2p2pl3', 'sw2p2pl4', 'sw30p1', 'sw30p1pl1', 'sw30p1pl2', 'sw30p1pl3', 'sw30p1pl4',
                                   'sw30p2', 'sw30p2pl1', 'sw30p2pl2', 'sw30p2pl3', 'sw30p2pl4', 'sw31p1', 'sw31p1pl1',
                                   'sw31p1pl2', 'sw31p1pl3', 'sw31p1pl4', 'sw31p2', 'sw31p2pl1', 'sw31p2pl2',
                                   'sw31p2pl3', 'sw31p2pl4', 'sw32p1', 'sw32p1pl1', 'sw32p1pl2', 'sw32p1pl3',
                                   'sw32p1pl4', 'sw32p2', 'sw32p2pl1', 'sw32p2pl2', 'sw32p2pl3', 'sw32p2pl4', 'sw33p1',
                                   'sw33p1pl1', 'sw33p1pl2', 'sw33p1pl3', 'sw33p1pl4', 'sw33p2', 'sw33p2pl1',
                                   'sw33p2pl2', 'sw33p2pl3', 'sw33p2pl4', 'sw34p1', 'sw34p1pl1', 'sw34p1pl2',
                                   'sw34p1pl3', 'sw34p1pl4', 'sw34p2', 'sw34p2pl1', 'sw34p2pl2', 'sw34p2pl3',
                                   'sw34p2pl4', 'sw35p1', 'sw35p1pl1', 'sw35p1pl2', 'sw35p1pl3', 'sw35p1pl4', 'sw35p2',
                                   'sw35p2pl1', 'sw35p2pl2', 'sw35p2pl3', 'sw35p2pl4', 'sw36p1', 'sw36p1pl1',
                                   'sw36p1pl2', 'sw36p1pl3', 'sw36p1pl4', 'sw36p2', 'sw36p2pl1', 'sw36p2pl2',
                                   'sw36p2pl3', 'sw36p2pl4', 'sw37p1', 'sw37p1pl1', 'sw37p1pl2', 'sw37p1pl3',
                                   'sw37p1pl4', 'sw37p2', 'sw37p2pl1', 'sw37p2pl2', 'sw37p2pl3', 'sw37p2pl4', 'sw38p1',
                                   'sw38p1pl1', 'sw38p1pl2', 'sw38p1pl3', 'sw38p1pl4', 'sw38p2', 'sw38p2pl1',
                                   'sw38p2pl2', 'sw38p2pl3', 'sw38p2pl4', 'sw39p1', 'sw39p1pl1', 'sw39p1pl2',
                                   'sw39p1pl3', 'sw39p1pl4', 'sw39p2', 'sw39p2pl1', 'sw39p2pl2', 'sw39p2pl3',
                                   'sw39p2pl4', 'sw3p1', 'sw3p1pl1', 'sw3p1pl2', 'sw3p1pl3', 'sw3p1pl4', 'sw3p2',
                                   'sw3p2pl1', 'sw3p2pl2', 'sw3p2pl3', 'sw3p2pl4', 'sw40p1', 'sw40p1pl1', 'sw40p1pl2',
                                   'sw40p1pl3', 'sw40p1pl4', 'sw40p2', 'sw40p2pl1', 'sw40p2pl2', 'sw40p2pl3',
                                   'sw40p2pl4', 'sw41p1', 'sw41p1pl1', 'sw41p1pl2', 'sw41p1pl3', 'sw41p1pl4', 'sw41p2',
                                   'sw41p2pl1', 'sw41p2pl2', 'sw41p2pl3', 'sw41p2pl4', 'sw42p1', 'sw42p1pl1',
                                   'sw42p1pl2', 'sw42p1pl3', 'sw42p1pl4', 'sw42p2', 'sw42p2pl1', 'sw42p2pl2',
                                   'sw42p2pl3', 'sw42p2pl4', 'sw43p1', 'sw43p1pl1', 'sw43p1pl2', 'sw43p1pl3',
                                   'sw43p1pl4', 'sw43p2', 'sw43p2pl1', 'sw43p2pl2', 'sw43p2pl3', 'sw43p2pl4', 'sw44p1',
                                   'sw44p1pl1', 'sw44p1pl2', 'sw44p1pl3', 'sw44p1pl4', 'sw44p2', 'sw44p2pl1',
                                   'sw44p2pl2', 'sw44p2pl3', 'sw44p2pl4', 'sw45p1', 'sw45p1pl1', 'sw45p1pl2',
                                   'sw45p1pl3', 'sw45p1pl4', 'sw45p2', 'sw45p2pl1', 'sw45p2pl2', 'sw45p2pl3',
                                   'sw45p2pl4', 'sw46p1', 'sw46p1pl1', 'sw46p1pl2', 'sw46p1pl3', 'sw46p1pl4', 'sw46p2',
                                   'sw46p2pl1', 'sw46p2pl2', 'sw46p2pl3', 'sw46p2pl4', 'sw47p1', 'sw47p1pl1',
                                   'sw47p1pl2', 'sw47p1pl3', 'sw47p1pl4', 'sw47p2', 'sw47p2pl1', 'sw47p2pl2',
                                   'sw47p2pl3', 'sw47p2pl4', 'sw48p1', 'sw48p1pl1', 'sw48p1pl2', 'sw48p1pl3',
                                   'sw48p1pl4', 'sw48p2', 'sw48p2pl1', 'sw48p2pl2', 'sw48p2pl3', 'sw48p2pl4', 'sw49p1',
                                   'sw49p1pl1', 'sw49p1pl2', 'sw49p1pl3', 'sw49p1pl4', 'sw49p2', 'sw49p2pl1',
                                   'sw49p2pl2', 'sw49p2pl3', 'sw49p2pl4', 'sw4p1', 'sw4p1pl1', 'sw4p1pl2', 'sw4p1pl3',
                                   'sw4p1pl4', 'sw4p2', 'sw4p2pl1', 'sw4p2pl2', 'sw4p2pl3', 'sw4p2pl4', 'sw50p1',
                                   'sw50p1pl1', 'sw50p1pl2', 'sw50p1pl3', 'sw50p1pl4', 'sw50p2', 'sw50p2pl1',
                                   'sw50p2pl2', 'sw50p2pl3', 'sw50p2pl4', 'sw51p1', 'sw51p1pl1', 'sw51p1pl2',
                                   'sw51p1pl3', 'sw51p1pl4', 'sw51p2', 'sw51p2pl1', 'sw51p2pl2', 'sw51p2pl3',
                                   'sw51p2pl4', 'sw52p1', 'sw52p1pl1', 'sw52p1pl2', 'sw52p1pl3', 'sw52p1pl4', 'sw52p2',
                                   'sw52p2pl1', 'sw52p2pl2', 'sw52p2pl3', 'sw52p2pl4', 'sw53p1', 'sw53p1pl1',
                                   'sw53p1pl2', 'sw53p1pl3', 'sw53p1pl4', 'sw53p2', 'sw53p2pl1', 'sw53p2pl2',
                                   'sw53p2pl3', 'sw53p2pl4', 'sw54p1', 'sw54p1pl1', 'sw54p1pl2', 'sw54p1pl3',
                                   'sw54p1pl4', 'sw54p2', 'sw54p2pl1', 'sw54p2pl2', 'sw54p2pl3', 'sw54p2pl4', 'sw55p1',
                                   'sw55p1pl1', 'sw55p1pl2', 'sw55p1pl3', 'sw55p1pl4', 'sw55p2', 'sw55p2pl1',
                                   'sw55p2pl2', 'sw55p2pl3', 'sw55p2pl4', 'sw56p1', 'sw56p1pl1', 'sw56p1pl2',
                                   'sw56p1pl3', 'sw56p1pl4', 'sw56p2', 'sw56p2pl1', 'sw56p2pl2', 'sw56p2pl3',
                                   'sw56p2pl4', 'sw57p1', 'sw57p1pl1', 'sw57p1pl2', 'sw57p1pl3', 'sw57p1pl4', 'sw57p2',
                                   'sw57p2pl1', 'sw57p2pl2', 'sw57p2pl3', 'sw57p2pl4', 'sw58p1', 'sw58p1pl1',
                                   'sw58p1pl2', 'sw58p1pl3', 'sw58p1pl4', 'sw58p2', 'sw58p2pl1', 'sw58p2pl2',
                                   'sw58p2pl3', 'sw58p2pl4', 'sw59p1', 'sw59p1pl1', 'sw59p1pl2', 'sw59p1pl3',
                                   'sw59p1pl4', 'sw59p2', 'sw59p2pl1', 'sw59p2pl2', 'sw59p2pl3', 'sw59p2pl4', 'sw5p1',
                                   'sw5p1pl1', 'sw5p1pl2', 'sw5p1pl3', 'sw5p1pl4', 'sw5p2', 'sw5p2pl1', 'sw5p2pl2',
                                   'sw5p2pl3', 'sw5p2pl4', 'sw60p1', 'sw60p1pl1', 'sw60p1pl2', 'sw60p1pl3', 'sw60p1pl4',
                                   'sw60p2', 'sw60p2pl1', 'sw60p2pl2', 'sw60p2pl3', 'sw60p2pl4', 'sw61p1', 'sw61p1pl1',
                                   'sw61p1pl2', 'sw61p1pl3', 'sw61p1pl4', 'sw61p2', 'sw61p2pl1', 'sw61p2pl2',
                                   'sw61p2pl3', 'sw61p2pl4', 'sw62p1', 'sw62p1pl1', 'sw62p1pl2', 'sw62p1pl3',
                                   'sw62p1pl4', 'sw62p2', 'sw62p2pl1', 'sw62p2pl2', 'sw62p2pl3', 'sw62p2pl4', 'sw63p1',
                                   'sw63p1pl1', 'sw63p1pl2', 'sw63p1pl3', 'sw63p1pl4', 'sw63p2', 'sw63p2pl1',
                                   'sw63p2pl2', 'sw63p2pl3', 'sw63p2pl4', 'sw64p1', 'sw64p1pl1', 'sw64p1pl2',
                                   'sw64p1pl3', 'sw64p1pl4', 'sw64p2', 'sw64p2pl1', 'sw64p2pl2', 'sw64p2pl3',
                                   'sw64p2pl4', 'sw65p1', 'sw65p1pl1', 'sw65p1pl2', 'sw65p1pl3', 'sw65p1pl4', 'sw65p2',
                                   'sw65p2pl1', 'sw65p2pl2', 'sw65p2pl3', 'sw65p2pl4', 'sw66p1', 'sw66p1pl1',
                                   'sw66p1pl2', 'sw66p1pl3', 'sw66p1pl4', 'sw66p2', 'sw66p2pl1', 'sw66p2pl2',
                                   'sw66p2pl3', 'sw66p2pl4', 'sw67p1', 'sw67p1pl1', 'sw67p1pl2', 'sw67p1pl3',
                                   'sw67p1pl4', 'sw67p2', 'sw67p2pl1', 'sw67p2pl2', 'sw67p2pl3', 'sw67p2pl4', 'sw68p1',
                                   'sw68p1pl1', 'sw68p1pl2', 'sw68p1pl3', 'sw68p1pl4', 'sw68p2', 'sw68p2pl1',
                                   'sw68p2pl2', 'sw68p2pl3', 'sw68p2pl4', 'sw69p1', 'sw69p1pl1', 'sw69p1pl2',
                                   'sw69p1pl3', 'sw69p1pl4', 'sw69p2', 'sw69p2pl1', 'sw69p2pl2', 'sw69p2pl3',
                                   'sw69p2pl4', 'sw6p1', 'sw6p1pl1', 'sw6p1pl2', 'sw6p1pl3', 'sw6p1pl4', 'sw6p2',
                                   'sw6p2pl1', 'sw6p2pl2', 'sw6p2pl3', 'sw6p2pl4', 'sw70p1', 'sw70p1pl1', 'sw70p1pl2',
                                   'sw70p1pl3', 'sw70p1pl4', 'sw70p2', 'sw70p2pl1', 'sw70p2pl2', 'sw70p2pl3',
                                   'sw70p2pl4', 'sw71p1', 'sw71p1pl1', 'sw71p1pl2', 'sw71p1pl3', 'sw71p1pl4', 'sw71p2',
                                   'sw71p2pl1', 'sw71p2pl2', 'sw71p2pl3', 'sw71p2pl4', 'sw72p1', 'sw72p1pl1',
                                   'sw72p1pl2', 'sw72p1pl3', 'sw72p1pl4', 'sw72p2', 'sw72p2pl1', 'sw72p2pl2',
                                   'sw72p2pl3', 'sw72p2pl4', 'sw7p1', 'sw7p1pl1', 'sw7p1pl2', 'sw7p1pl3', 'sw7p1pl4',
                                   'sw7p2', 'sw7p2pl1', 'sw7p2pl2', 'sw7p2pl3', 'sw7p2pl4', 'sw8p1', 'sw8p1pl1',
                                   'sw8p1pl2', 'sw8p1pl3', 'sw8p1pl4', 'sw8p2', 'sw8p2pl1', 'sw8p2pl2', 'sw8p2pl3',
                                   'sw8p2pl4', 'sw9p1', 'sw9p1pl1', 'sw9p1pl2', 'sw9p1pl3', 'sw9p1pl4', 'sw9p2',
                                   'sw9p2pl1', 'sw9p2pl2', 'sw9p2pl3', 'sw9p2pl4']

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
        self.temperature_sensors += ["ASIC2", "ASIC3", "ASIC4", "PSU-7-Temp", "SODIMM-2-Temp"]
        self.temperature_sensors.remove("PSU-1-Temp")

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK.lower(), "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2000, range_max=10000),
            "max-speed": ExpectedString(range_min=20000, range_max=40000)}
        self.platform_inventory_switch_values.update({"hardware-version": None,
                                                      "model": None})

    def _init_eth0_speeds(self):
        super()._init_eth0_speeds()
        self.supported_eth0_speeds += ['10M']

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
        self.asic_type = NvosConst.QTM3
        self.system_is_ready_wait_timeout = 10 * MINUTE
        self.allow_cpld_update = True
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
        self.stats_cpu_header_num_of_lines = 12
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
        self.temperature_sensors += ["ASIC2", "PSU-3-Temp", "PSU-4-Temp", "PMIC-2-Temp", "PMIC-7-Temp"]

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
        self.health_monitor_config_file_path = HealthConsts.HEALTH_MONITOR_CONFIG_FILE_PATH.format(
            "x86_64-mlnx_mqm9700-r0")
        self.platform_file_path = MultiPlanarConsts.PLATFORM_FILE_FULL_PATH.format("x86_64-mlnx_mqm9700-r0")

    def get_mgmt_ports(self) -> List[str]:
        return self.mgmt_ports


# -------------------------- Juliet Switch ----------------------------


class JulietSwitch(NvLinkSwitch):
    FaeImagesTestConsts = namedtuple('FaeImagesTestConsts', ('current_image_version', 'alternate_image_version'))
    NmxClusterAppsConsts = namedtuple('NmxClusterAppsConsts',
                                      ('burn_path', 'burn_version_names'))
    BiosImagesTestConsts = namedtuple('BiosImagesTestConsts', ('current_version', 'alternate_version'))

    def __init__(self, asic_amount):
        super().__init__(asic_amount=asic_amount)

    def show_setup_versions(self, dut_engine: LinuxSshEngine = None):
        get_bmc_version_cmd = 'curl -k -u root:{} -X GET https://10.0.1.1/redfish/v1/UpdateService/FirmwareInventory/MGX_FW_BMC_0'
        psws = ['0penBmc', 'Test123!', 'ABYX12#14artb']
        outputs = {
            'system version': dut_engine.run_cmd('nv show system version'),
            'platform firmware': dut_engine.run_cmd('nv show platform firmware'),
            'fae platform firmware': dut_engine.run_cmd('nv show fae platform firmware'),
        }
        for pw in psws:
            out = dut_engine.run_cmd(get_bmc_version_cmd.format(pw))
            if 'error' not in out:
                outputs['bmc version (redfish)'] = out
                break
        res = [f'{title.upper()}:\n{output}\n' for title, output in outputs.items()]
        return '\n'.join(res)

    def _init_constants(self):
        super()._init_constants()
        self.system_is_ready_wait_timeout = 20 * MINUTE
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
        self.is_standalone = True
        self.show_platform_chassis_location_output = {
            PlatformConsts.CHASSIS_LOCATION_TRAY_ID: ExpectedString(range_min=-1, range_max=9),
            PlatformConsts.CHASSIS_LOCATION_SLOT_ID: ExpectedString(range_min=4, range_max=18),
            PlatformConsts.CHASSIS_LOCATION_CHAS_ID: "",
            PlatformConsts.CHASSIS_LOCATION_TOPO_ID: ExpectedString(regex=r"^(Loopback|GB200 NVL36|GB200 NVL72|\d+)$")
        }
        cluster_files = ['conf', 'nmx-controller', 'nmx-telemetry']
        self.constants = self.constants._replace(cluster_files=cluster_files)
        bmc_dump_files = ['bmc_debug_log_dump.tar']
        self.constants = self.constants._replace(bmc_dump_files=bmc_dump_files)
        self.constants.dump_files.append('BMCeeprom')
        self.constants.erots.extend(['ERoT_BMC_0', 'ERoT_CPU_0', 'ERoT_FPGA_0', 'ERoT_NVSwitch_0', 'ERoT_NVSwitch_1'])

        self.nmx_cluster_apps_versions = self.NmxClusterAppsConsts(
            burn_path={
                ClusterConsts.NMX_CONTROLLER: "/auto/sw/release/NMX/NMX-controller/package/0.6.0/nmx-c-nvlink_0.6.0_2024-08-27_17-17.tar.gz",
                ClusterConsts.NMX_TELEMETRY: "/auto/sw/release/NMX/NMX-telemetry/nmx-telemetry_0.6.2_2024-08-20.tgz"
            },
            burn_version_names={
                ClusterConsts.NMX_CONTROLLER: "0.6.0",
                ClusterConsts.NMX_TELEMETRY: "0.6.2"
            }
        )
        self.supported_commands.extend([ActionConsts.POWER_CYCLE])
        self.asic_version = BaseSwitch.AsicImageConsts(
            version="35.2014.1476",
            filename="fw-QTM3-rel-35_2014_1476.mfa"
        )
        self.bios_image_info = BaseSwitch.BiosImagesConsts(
            current_version={
                'path': '/auto/sw_system_release/sx_mlnx_bios/SnowyOwl/0ACTV_00.00.016/Release/erot_sign_debug/cec1736-apfw-0000010.fwpkg',
                'filename': 'cec1736-apfw-0000010.fwpkg',
                'version_name': '00.00.016',
                'date': '08/05/2024'},
            alternate_version={
                'path': '/auto/sw_system_release/sx_mlnx_bios/SnowyOwl/0ACTV_00.00.015_rc7/Release/erot_sign_debug/cec1736-apfw-000000f.fwpkg',
                'filename': 'cec1736-apfw-000000f.fwpkg',
                'version_name': '00.00.015_rc7',
                'date': '08/05/2024'})

        self.power_cycle_type = 'juliet-power-cycle'

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
            'PMIC-4-Temp', 'PMIC-5-Temp', 'PMIC-6-Temp', 'PMIC-7-Temp', 'PMIC-8-Temp', 'SODIMM-1-Temp',
            'SWB-ASIC1-PCB-Temp', 'SWB-ASIC2-PCB-Temp']

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
        self.cluster_app_nmx_controller = {'app-id': 'nmx-c-nvos', 'app-ver': None, 'capabilities': 'sm, gfm, fib, gw-api', 'components-ver': None, 'reason': '', 'status': 'ok'}
        self.cluster_app_nmx_telemetry = {'app-id': 'nmx-telemetry', 'app-ver': None, 'capabilities': 'ib-telemetry', 'components-ver': None, 'reason': '', 'status': 'ok'}
        self.cluster_app = {
            'nmx-controller': {key: value for key, value in self.cluster_app_nmx_controller.items() if key not in ['reason', 'status']},
            'nmx-telemetry': {key: value for key, value in self.cluster_app_nmx_telemetry.items() if key not in ['reason', 'status']}
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

        self.stats_fan_header_num_of_lines = 21
        self.stats_cpu_header_num_of_lines = 10
        self.stats_temperature_header_num_of_lines = 48

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
        self.fnm_link_speed = '100G'
        self.fnm_fae_link_speed = '100G'
        self.nvl5_port_type = 'nvl'
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
        logger.info("Sleeping for 80 seconds - Reboot takes longer on juliet for now")
        time.sleep(80)

    def _relevant_config_filename_by_version(self, version: str) -> str:
        return 'nvos_config_nvl5.yml'

# -------------------------- JulietTTM Switch ----------------------------


class JulietTTMSwitch(JulietScaleoutSwitch):

    def __init__(self):
        super().__init__()

    def _init_constants(self):
        super()._init_constants()
        self.allow_cpld_update = True
        self.current_cpld_version = BaseSwitch.CpldImageConsts(
            burn_image_path="/auto/swgwork/omerr/Juliet_QS/Secured_CPLD/FUI000349/FUI000349_BURN_JULIET_TTM_CPLD000370_REV0109_CPLD000377_REV0307_CPLD000373_REV0204_CPLD000390_REV0103_IPN.vme",
            refresh_image_path="",
            version_names={
                "CPLD1": "CPLD000370_REV0109",
                "CPLD2": "CPLD000377_REV0307",
                "CPLD3": "CPLD000373_REV0204",
                "CPLD4": "CPLD000390_REV0103"
            }
        )
        self.previous_cpld_version = BaseSwitch.CpldImageConsts(
            burn_image_path="/auto/swgwork2/rlupovich/CPLD/Juliet_QS/FUI000343/FUI000343_BURN_JULIET_TTM_CPLD000370_REV0109_CPLD000377_REV0305_CPLD000373_REV0203_CPLD000390_REV0103_IPN.vme",
            refresh_image_path="",
            version_names={
                "CPLD1": "CPLD000370_REV0109",
                "CPLD2": "CPLD000377_REV0305",
                "CPLD3": "CPLD000373_REV0203",
                "CPLD4": "CPLD000390_REV0103"
            }
        )

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
        self.platform_inventory_switch_values.update({"model": "692-9K36F-A5MV-JS0"})


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
        self.nvl5_fnm_ports = ['fnm1', 'fnm2', 'fnma0p1', 'fnma1p1']
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

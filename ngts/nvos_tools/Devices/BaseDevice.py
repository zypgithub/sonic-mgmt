import logging
import os
import time
from abc import abstractmethod, ABCMeta, ABC
from collections import namedtuple
from typing import Tuple, List

from ngts.nvos_constants.constants_nvos import DatabaseConst, FansConsts, NvosConst, PlatformConsts, SystemConsts, \
    DiskConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.infra.DatabaseTool import DatabaseTool
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.nvos_tools.infra.ValidationTool import ExpectedString
from ngts.tools.test_utils.nvos_general_utils import get_version_info

logger = logging.getLogger()


# -------------------------- Base Device ----------------------------
class BaseDevice(ABC):

    def __init__(self, switch_type="", asic_amount=1):
        self.default_password = ""
        self.default_username = ""
        self.prev_default_password = ""
        self.open_api_port = ""
        self.dependent_dockers = []
        self.asic_amount = asic_amount
        self.switch_type = switch_type
        self.cli_coverage_path = ""
        self.cli_coverage_project_name = ""

        self._init_constants()
        self._init_available_databases()
        self._init_services()
        self._init_dependent_services()
        self._init_dockers()
        self._init_fan_list()
        self._init_led_list()
        self._init_psu_list()
        self._init_fan_direction_dir()
        self._init_temperature()
        self._init_health_components()
        self._init_platform_lists()
        self._init_system_lists()
        self._init_security_lists()
        self._init_password_hardening_lists()

    def init_documents_consts(self):
        self.documents_path = {}
        self.documents_files = {}

    def _init_available_databases(self):
        self.available_databases = {}
        self.available_tables = {}
        self.available_tables_per_asic = {}

    def _init_services(self):
        self.available_services = []

    def _init_dependent_services(self):
        self.dependent_services = []

    def _init_dockers(self):
        self.available_dockers = []

    def _init_constants(self):
        self.pre_login_message = ""
        self.post_login_message = ""
        self.install_from_onie_timeout = 7 * 60  # seconds
        self.install_success_patterns = ""
        self.core_count = 1
        self.asic_type = ""
        self.ib_ports_num = 0
        self.mst_dev_name = ""
        self.constants = None
        self.voltage_sensors = []

    def _init_fan_list(self):
        self.fan_list = []

    def _init_led_list(self):
        self.led_list = []

    def _init_psu_list(self):
        self.psu_list = []
        self.psu_fan_list = []
        self.platform_env_psu_prop = []

    def _init_fan_direction_dir(self):
        self.fan_direction_dir = ""

    def _init_temperature(self):
        self.temperature_sensors = []

    def _init_health_components(self):
        self.health_components = []

    def _init_platform_lists(self):
        self.platform_hw_list = []

    def _init_system_lists(self):
        self.user_fields = []

    def _init_security_lists(self):
        self.kex_algorithms = []

    def _init_password_hardening_lists(self):
        self.local_test_users = []

    def init_cli_coverage_prop(self, cli_coverage_project_name):
        self.cli_coverage_project_name = cli_coverage_project_name
        self.cli_coverage_path = f"/auto/sw/tools/comet/{self.cli_coverage_project_name}/"

    @abstractmethod
    def get_ib_ports_num(self):
        pass

    def get_mgmt_ports(self) -> List[str]:
        return None

    def get_default_password_by_version(self, version: str):
        return self.default_password

    def get_test_config_file_by_version(self, version: str) -> Tuple[str, str]:
        ngts_path = os.path.join(os.path.abspath(__file__).split('ngts', 1)[0], 'ngts')
        config_filename = self._relevant_config_filename_by_version(version)
        config_file_path = os.path.join(ngts_path, 'tools', 'test_utils', 'nvos_resources', config_filename)
        logger.info(f'NGTS_PATH: {ngts_path}')
        logger.info(f'CONF_YML_FILE_PATH: {config_file_path}')
        return config_file_path, config_filename

    def _relevant_config_filename_by_version(self, version: str) -> str:
        version_num, _ = get_version_info(version)
        if version_num:
            version_num = int(version_num.split('.')[-1])
            return f'nvos_config_ga_{(version_num // 1000) * 1000}.yml'
        return 'nvos_config_ga_3000.yml'

    def verify_databases(self, dut_engine):
        """
        validate the redis includes all expected tables
        :param dut_engine: ssh dut engine
        Return result_obj with True result if all tables exists, False and a relevant info if one or more tables are missing
        """
        time.sleep(10)
        result_obj = ResultObj(True, "")
        for db_name, db_id in self.available_databases.items():
            if db_name == DatabaseConst.STATE_DB_NAME:
                continue

            for database_docker in self.available_tables.keys():
                table_info = self.available_tables[database_docker][db_id]
                for table_name, expected_entries in table_info.items():
                    output = self.get_all_table_names_in_database(dut_engine, db_name, table_name,
                                                                  database_docker=database_docker).returned_value
                    if len(output) < expected_entries:
                        result_obj.result = False
                        result_obj.info += "Database docker: {database_docker} DB: {db_name}, Table: {table_name}. Table count mismatch, Expected: {expected} != Actual {actual}\n" \
                            .format(database_docker=database_docker, db_name=db_name, table_name=table_name,
                                    expected=str(expected_entries),
                                    actual=str(len(output)))

        return result_obj

    def verify_dockers(self, dut_engine, dockers_list=""):
        """
        Validate existing dockers
        """
        result_obj = ResultObj(True, "")
        cmd_output = dut_engine.run_cmd('docker ps --format \"table {{.Names}}\"')
        list_of_dockers = dockers_list or self.available_dockers
        for docker in list_of_dockers:
            if docker not in cmd_output:
                result_obj.result = False
                result_obj.info += "{} docker is not active.\n".format(docker)

        return result_obj

    def verify_services(self, dut_engine):
        """
        Validate expected dockers
        """
        result_obj = ResultObj(True, "")
        for service in self.available_services:
            cmd_output = dut_engine.run_cmd('systemctl --type=service | grep {}'.format(service))
            if NvosConst.SERVICE_STATUS_ACTIVE not in cmd_output:
                result_obj.result = False
                result_obj.info += "{} service is not active. {} \n".format(service, cmd_output)

        temp_res = self.verify_nvue_service(dut_engine)
        if not temp_res.result:
            result_obj.result = False
            result_obj.info += temp_res.info

        return result_obj

    def verify_nvue_service(self, dut_engine):
        logging.info("Verify nvued service is active")
        nvued_cmd_output = dut_engine.run_cmd("sudo systemctl status nvued")
        if NvosConst.SERVICE_STATUS_ACTIVE not in nvued_cmd_output:
            return ResultObj(False, "nvued service is not active. info: {}".format(nvued_cmd_output))
        return ResultObj(True)

    def get_database_id(self, db_name):
        return self.available_databases[db_name]

    def get_all_table_names_in_database(self, engine, database_name, table_name_substring='.', database_docker=None):
        """
        :param engine: dut engine
        :param database_name: database name
        :param table_name_substring: full or partial table name
        :return: any database table that includes the substring, if table_name_substring is none we will return all the tables
        """
        result_obj = ResultObj(True, "")
        # docker_exec_cmd = 'docker exec -it {database_docker} '.format(database_docker=database_docker) if database_docker else ''
        output = DatabaseTool.sonic_db_run_get_keys_in_docker(
            docker_name=database_docker if database_docker else '', engine=engine, asic="",
            db_name=DatabaseConst.REDIS_DB_NUM_TO_NAME[self.get_database_id(database_name)],
            grep_str=table_name_substring)

        # cmd = docker_exec_cmd + "redis-cli -n {database_name} keys * | grep {prefix}".format(
        #    database_name=self.get_database_id(database_name), prefix=table_name_substring)
        # output = engine.run_cmd(cmd)
        result_obj.returned_value = output.splitlines()
        return result_obj

    @abstractmethod
    def wait_for_os_to_become_functional(self, engine, find_prompt_tries=60, find_prompt_delay=10):
        raise Exception(f"Not implemented for this switch {self.__class__.__name__}")

    @abstractmethod
    def reload_device(self, engine, cmd_list, validate=False):
        raise Exception(f"Not implemented for this switch {self.__class__.__name__}")

    @abstractmethod
    def get_voltage_sensors(self, dut_engine=None):
        raise Exception(f"Not implemented for this switch {self.__class__.__name__}")

# -------------------------- Base Appliance ----------------------------


class BaseAppliance(BaseDevice):
    def __init__(self):
        BaseDevice.__init__(self)

    @abstractmethod
    def eth_ports_num(self):
        pass


# -------------------------- Base Switch ----------------------------
class BaseSwitch(BaseDevice):
    __metaclass__ = ABCMeta

    Constants = namedtuple('Constants', ['system', 'dump_files', 'sdk_dump_files', 'firmware', 'log_dump_files',
                                         'stats_dump_files', 'hw_mgmt_files', 'cluster_files'])
    CpldImageConsts = namedtuple('CpldImageConsts', ('burn_image_path', 'refresh_image_path', 'version_names'))
    SsdImageConsts = namedtuple('SsdImageConsts', ('file', 'current_version', 'alternate_version'))

    def init_documents_consts(self):
        super().init_documents_consts()

    def _init_available_databases(self):
        super()._init_available_databases()

    def _init_services(self):
        super()._init_services()

    def get_ib_ports_num(self):
        return self.ib_ports_num

    def _init_dockers(self):
        super()._init_dockers()

    def _init_constants(self):
        super()._init_constants()
        system_dic = {
            'system': [SystemConsts.BUILD, SystemConsts.HOSTNAME, SystemConsts.PLATFORM, SystemConsts.PRODUCT_NAME,
                       SystemConsts.PRODUCT_RELEASE, SystemConsts.SWAP_MEMORY, SystemConsts.SYSTEM_MEMORY,
                       SystemConsts.UPTIME, SystemConsts.TIMEZONE, SystemConsts.HEALTH_STATUS, SystemConsts.DATE_TIME,
                       SystemConsts.STATUS],
            'message': [SystemConsts.PRE_LOGIN_MESSAGE, SystemConsts.POST_LOGIN_MESSAGE],
            'reboot': [SystemConsts.REBOOT_REASON],
            'version': [SystemConsts.VERSION_BUILD_DATE, SystemConsts.VERSION_IMAGE, SystemConsts.VERSION_KERNEL,
                        SystemConsts.VERSION_ONIE]
        }
        dump_files = ['APPL_DB.json', 'ASIC_DB.json', 'boot.conf', 'bridge.fdb', 'bridge.vlan', 'CONFIG_DB.json',
                      'COUNTERS_DB_1.json', 'COUNTERS_DB_2.json', 'COUNTERS_DB.json', 'date.counter_1',
                      'date.counter_2', 'df', 'dmesg', 'docker.pmon', 'docker.ps', 'docker.stats',
                      'docker.swss-ibv0.log', 'dpkg', 'fan', 'FLEX_COUNTER_DB.json', 'free', 'hdparm',
                      'ifconfig.counters_1', 'ifconfig.counters_2', 'interface.status', 'interface.xcvrs.eeprom',
                      'interface.xcvrs.presence', 'ip.addr', 'ip.interface', 'ip.link', 'ip.link.stats', 'ip.neigh',
                      'ip.neigh.noarp', 'ip.route', 'ip.rule', 'lspci', 'lsusb', 'machine.conf', 'mount',
                      'netstat.counters_1', 'netstat.counters_2', 'platform.summary', 'ps.aux', 'ps.extended',
                      'psustatus', 'queue.counters_1', 'queue.counters_2', 'reboot.cause',
                      'saidump', 'sensors', 'services.summary', 'ssdhealth', 'STATE_DB.json', 'swapon', 'sysctl',
                      'syseeprom', 'systemd.analyze.blame', 'systemd.analyze.dump', 'systemd.analyze.plot.svg',
                      'temperature', 'top', 'version', 'vlan.summary', 'vmstat', 'vmstat.m', 'vmstat.s', 'who']
        sdk_dump_files = ['fw_trace_attr.json', 'fw_trace_string_db.json', 'sai_sdk_dump.gz',
                          'sdk_dump_ext_dev1_summary.txt.gz', 'sdk_dump_ext_dev1_cr_space_2.udmp.gz',
                          'sdk_dump_ext_dev1_gw.udmp.gz', 'sdk_dump_ext_dev1_dpt.txt.gz',
                          'sdk_dump_ext_dev1_fw_trace.txt.gz', 'fw_trace_attr.json.gz', 'fw_trace_string_db.json.gz',
                          'sai_sdk_dump.json.gz', 'sdk_dump_ext_dev1_cr_space_1.udmp.gz',
                          'sdk_dump_ext_dev1_cr_space_3.udmp.gz', 'sdk_dump_ext_dev1_driver.txt.gz',
                          'sdk_dump_ext_dev1_amber.hex.gz']
        log_dump_files = ["access.log.gz", "audit.log.gz", "auth.log.gz", "btmp.gz", "cron.log.gz", "error.log.gz",
                          "firewall_packet_capture.log.gz", "fw_trace_attr.json.gz", "health_history.gz",
                          "nv-cli.log.gz", "nvued.log.gz", "syslog.gz", "tc_log.gz", "wtmp.gz", "ztp.log.gz"]

        stats_dump_files = ["cpu.csv.gz", "disk.csv.gz", "fan.csv.gz", "power.csv.gz",
                            "mgmt-interface.csv.gz", "temperature.csv.gz", "voltage.csv.gz"]
        hw_mgmt_files = ['hw-mgmt-dump.tar.gz']

        cluster_files = None

        firmware = [PlatformConsts.FW_ASIC, PlatformConsts.FW_BIOS, PlatformConsts.FW_SSD,
                    PlatformConsts.FW_CPLD + '1', PlatformConsts.FW_CPLD + '2', PlatformConsts.FW_CPLD + '3']
        self.constants = BaseSwitch.Constants(system_dic, dump_files, sdk_dump_files, firmware, log_dump_files,
                                              stats_dump_files, hw_mgmt_files, cluster_files)

        self.current_bios_version_name = ""
        self.current_bios_version_path = ""
        self.previous_bios_version_name = ""
        self.previous_bios_version_path = ""
        self.current_cpld_version = None
        self.previous_cpld_version = None
        self.show_platform_output = {
            "system-mac": ExpectedString(regex=r"([\dA-F]{2}:){5}[\dA-F]{2}"),
            "manufacturer": "Nvidia",
            "product-name": "",     # These fields need to be updated in subclasses.
            "cpu": None,            # `None` means we expect any string not in ['', 'N/A'].
            "memory": ExpectedString.number_and_string('GB', range_min=6),  # Expects "x GB" where x > 6
            "disk-size": ExpectedString.number_and_string('GB', range_min=14.0),
            "port-layout": None,
            "part-number": None,
            "serial-number": None,
            "asic-model": "",
            "system-uuid": ExpectedString(regex=r"[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}"),
        }
        self.disk_default_partition_name = DiskConsts.DEFAULT_PARTITION_NAME
        self.disk_partition_capacity_limit = DiskConsts.PARTITION_CAPACITY_LIMIT
        self.disk_minimum_free_space = DiskConsts.MINIMUM_FREE_SPACE
        self.reboot_type = 'reboot'  # If system has special reboot (in terms of time) this var will describe it. Useful when extracting THRESHOLDS
        self.generate_tech_support = 'generate tech-support'
        self.reset_factory = 'reset factory'

    def _init_psu_list(self):
        super()._init_psu_list()
        self.psu_list = ["PSU1", "PSU2"]
        self.psu_fan_list = ["PSU1/FAN", "PSU2/FAN"]
        self.platform_env_psu_prop = ["capacity", "current", "power", "state", "voltage"]

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors = ["ASIC", "Ambient-Fan-Side-Temp", "Ambient-Port-Side-Temp",
                                    "CPU-Core-0-Temp", "CPU-Core-1-Temp", "CPU-Pack-Temp",
                                    "PSU-1-Temp"]

    def _init_health_components(self):
        super()._init_health_components()
        self.health_components = self.fan_list + self.psu_list + self.psu_fan_list + \
            ["ASIC Temperature", "Containers", "CPU utilization", "Disk check", "Disk space",
             "Disk space log"]

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_hw_list = ["asic-count", "cpu", "cpu-load-averages", "disk-size", "hw-revision", "manufacturer",
                                 "memory", "model", "onie-version", "part-number", "product-name", "serial-number",
                                 "system-mac", "system-uuid"]
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_inventory_items = self.fan_list + self.psu_list + [PlatformConsts.HW_COMP_SWITCH]
        self.platform_inventory_items_dict = {
            'fan': self.fan_list, 'psu': self.psu_list, 'switch': [PlatformConsts.HW_COMP_SWITCH]}
        self.platform_inventory_fields = ["hardware-version", "model", "serial", "state", "type"]
        self.platform_inventory_fan_values = {
            "hardware-version": NvosConst.NOT_AVAILABLE, "model": NvosConst.NOT_AVAILABLE,
            "serial": NvosConst.NOT_AVAILABLE, "state": FansConsts.STATE_OK, "type": PlatformConsts.ENV_FAN}
        self.platform_inventory_psu_values = {
            "hardware-version": None, "model": None,
            "serial": None, "state": FansConsts.STATE_OK, "type": PlatformConsts.ENV_PSU}
        self.platform_inventory_switch_values = {
            "hardware-version": "", "model": "",  # update these in subclasses
            "serial": None, "state": FansConsts.STATE_OK, "type": PlatformConsts.HW_COMP_SWITCH.lower()}
        self.platform_port_state = {
            "polling-physical-state": IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_POLLING
        }
        self.platform_inventory_values = {"fan": self.platform_inventory_fan_values,
                                          "psu": self.platform_inventory_psu_values,
                                          "switch": self.platform_inventory_switch_values}

    def _init_fan_direction_dir(self):
        super()._init_fan_direction_dir()
        self.fan_direction_dir = "/var/run/hw-management/thermal"

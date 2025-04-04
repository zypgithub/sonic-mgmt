import logging
import os
from typing import List

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_constants.constants_nvos import NvosConst, FansConsts, PlatformConsts, CumulusConsts
from ngts.nvos_tools.Devices.BaseDevice import BaseSwitch
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.ValidationTool import ExpectedString
from ngts.tests_nvos.general.security.security_test_tools.constants import AaaConsts
from ngts.tools.test_utils.nvos_config_utils import clear_cl_conf

logger = logging.getLogger()


class EthSwitch(BaseSwitch):

    def __init__(self, asic_amount):
        super().__init__()
        self.asic_amount = asic_amount
        self.mgmt_ports = ['eth0']
        self._init_sensors_dict()
        self.open_api_port = "8765"
        self.default_password = os.environ["CUMULUS_SWITCH_PASSWORD"]
        self.default_username = os.environ["CUMULUS_SWITCH_USER"]
        self.manufacture_password = "cumulus"
        self.switch_type = CumulusConsts.ETH_SWITCH_TYPE
        self.init_documents_consts()
        self.init_cli_coverage_prop("cumulus")
        self._init_eth0_speeds()
        self._init_eth0_duplex()

    def init_documents_consts(self):
        super().init_documents_consts()

    def verify_sed_password(self, tpm_tool, sed_default_password=""):
        pass  # This should be ignored on eth switches, overrides method from base switch

    def get_voltage_sensors(self, dut_engine=None):
        return self.voltage_sensors

    def get_default_nvue_config(self, dut_engine=None):
        default_conf = NvosConst.DEFAULT_CL_CONFIG
        default_conf["interface"] = NvosConst.DEFAULT_CL_IFACE_CONFIG
        return default_conf

    def show_setup_versions(self, dut_engine: LinuxSshEngine = None):
        outputs = {
            'system version': dut_engine.run_cmd('nv show system version'),
            'platform firmware': dut_engine.run_cmd('nv show platform firmware'),
        }
        res = [f'{title.upper()}:\n{output}\n' for title, output in outputs.items()]
        return '\n'.join(res)

    def clear_config(self, dut_engine, markers=None, default_yml_path=None, root_dir=""):
        clear_cl_conf(dut_engine, markers, self)

    def _init_constants(self):
        super()._init_constants()
        self.pre_login_message = "None\n"
        self.post_login_message = "\nWelcome to NVIDIA Cumulus (R) Linux (R)\n\nFor support and online " \
                                  "technical documentation, visit\nhttps://www.nvidia.com/en-us/support\n\nThe " \
                                  "registered trademark Linux (R) is used pursuant to a sublicense from LMI,\nthe " \
                                  "exclusive licensee of Linus Torvalds, owner of the mark on a world-wide\nbasis.\n"
        self.install_from_onie_timeout = 10 * 60
        self.login_pattern = CumulusConsts.LINUX_BOOT_PATTERN
        self.install_patterns = {self.login_pattern: 0, NvosConst.INSTALL_BOOT_PATTERN: 1,
                                 CumulusConsts.LOGIN_BOOT_PATTERN: 2}
        self.install_success_patterns = list(self.install_patterns.keys())

        self.voltage_sensors = ["PMIC-1-PSU-12V-RAIL-IN", "PMIC-2-PSU-12V-RAIL-IN",
                                "PMIC-2-ASIC-1.2V_MAIN-RAIL-OUT2", "PMIC-2-ASIC-1.8V_MAIN-RAIL-OUT1",
                                "PMIC-3-ASIC-1.8V_T0_3-RAIL-OUT2", "PMIC-3-COMEX-1.05V-RAIL-OUT",
                                "PMIC-3-PSU-12V-RAIL-IN", "PMIC-3-PSU-12V-RAIL-IN1",
                                "PMIC-5-ASIC-1.2V_T0_3-RAIL-OUT1", "PMIC-5-ASIC-1.2V_T4_7-RAIL-OUT2",
                                "PMIC-5-PSU-12V-RAIL-IN", "PMIC-6-COMEX-1.8V-RAIL-OUT1",
                                "PMIC-6-PSU-12V-RAIL-IN1", "PMIC-6-PSU-12V-RAIL-IN2",
                                "PMIC-7-COMEX-1.2V-RAIL-OUT", "PMIC-7-PSU-12V-RAIL-IN1",
                                "PMIC-7-PSU-12V-RAIL-IN2", "PSU-2L-12V-RAIL-OUT",
                                "PSU-2L-220V-RAIL-IN"]
        self.constants.firmware.remove(PlatformConsts.FW_ASIC)

        self.show_platform_output.update({
            "system-mac": ExpectedString(regex=r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}"),
            "manufacturer": "Mellanox"
        })

        self.disk_partition_capacity_limit = 70  # Percent value
        self.disk_minimum_free_space = 5.5  # Gig
        self.ib_ports_num = 32
        self.supports_tpm_testing = False

    def wait_for_os_to_become_functional(self, engine, find_prompt_tries=60, find_prompt_delay=10):
        return DutUtilsTool.wait_for_cumulus_to_become_functional(engine)

    def reload_device(self, engine, cmd_set, validate=False):
        engine.run_cmd_set(cmd_set, validate=False)

    def get_mgmt_ports(self) -> List[str]:
        return self.mgmt_ports

    def get_admins_group(self):
        return 'cumulus'

    def _init_eth0_speeds(self):
        self.supported_eth0_speeds = ['10M', '100M', '1G']

    def _init_eth0_duplex(self):
        self.supported_eth0_duplex = ['full']

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2",
                         "FAN5/1", "FAN5/2", "FAN6/1", "FAN6/2"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "FAN4", "FAN5", "FAN6", "PSU", "SYSTEM"]

    def _init_platform_lists(self):
        super()._init_platform_lists()
        self.platform_hw_list = ["base-mac", "cpu", "disk-size", "manufacturer", "memory", "model", "onie-version",
                                 "part-number", "platform-name", "port-layout", "product-name", "serial-number",
                                 "system-mac", "asic-model", "asic-vendor"]
        self.hw_comp_list = ["device"]
        self.hw_comp_prop = ["model", "type"]
        self.fan_prop = ["max-speed", "min-speed", "speed", "state"]
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2000, range_max=10000),
            "max-speed": ExpectedString(range_min=19500, range_max=40000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list + self.psu_fan_list \
            + [PlatformConsts.HW_COMP_SWITCH]
        self.platform_inventory_switch_values.update({"hardware-version": None,
                                                      "model": ExpectedString(regex="MSN.*")})

    def _init_psu_list(self):
        self.psu_list = ["PSU1", "PSU2"]
        self.psu_fan_list = ["PSU1/FAN", "PSU2/FAN"]
        self.platform_env_psu_prop = ["state"]

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Package-Sensor", "Main-Board-Ambient-Sensor",
                                    "CPU-Core-Sensor-0", "CPU-Core-Sensor-1",
                                    "CPU-Core-Sensor-2", "CPU-Core-Sensor-3",
                                    "PSU1-Temp-Sensor", "PSU2-Temp-Sensor",
                                    "CPU-Core-Sensor-0", "CPU-Core-Sensor-1", "Port-Ambient-Sensor"]

    def _init_sensors_dict(self):
        self.sensors_dict = {"VOLTAGE": self.voltage_sensors,
                             "TEMPERATURE": self.temperature_sensors}

    def _init_system_lists(self):
        self.user_fields = ['root', 'cumulus']

    def _init_security_lists(self):
        super()._init_security_lists()
        self.kex_algorithms = ['ecdh-sha2-nistp521', 'diffie-hellman-group-exchange-sha256',
                               'curve25519-sha256@libssh.org', 'diffie-hellman-group18-sha512',
                               'kex-strict-s-v00@openssh.com', 'ecdh-sha2-nistp256',
                               'curve25519-sha256', 'ecdh-sha2-nistp384', 'diffie-hellman-group14-sha256',
                               'sntrup761x25519-sha512@openssh.com', 'diffie-hellman-group16-sha512']
        self.aaa_cleanup_cmds = [
            'nv unset system aaa authentication-order',
            'nv config apply -y'
        ]

    def _init_password_hardening_lists(self):
        self.aaa_admin_role = 'nvue-admin'
        self.aaa_monitor_role = 'nvue-monitor'
        self.local_test_users = [{AaaConsts.USERNAME: AaaConsts.LOCALADMIN,
                                  AaaConsts.PASSWORD: AaaConsts.STRONG_PASSWORD,
                                  AaaConsts.ROLE: self.aaa_admin_role},
                                 {AaaConsts.USERNAME: AaaConsts.LOCALMONITOR,
                                  AaaConsts.PASSWORD: AaaConsts.STRONG_PASSWORD,
                                  AaaConsts.ROLE: self.aaa_monitor_role}]

    def _init_available_databases(self):
        super()._init_available_databases()

    def _init_services(self):
        super()._init_services()

    def _init_dependent_services(self):
        super()._init_dependent_services()

    def _init_dockers(self):
        super()._init_dockers()

    def setup_base_aaa_config(self, dut_engine: LinuxSshEngine):
        dut_engine.run_cmd('nv set system config apply ignore "/etc/hosts"')
        dut_engine.run_cmd("nv set system aaa role admin class nvapply")
        dut_engine.run_cmd("nv set system aaa role admin class sudo")
        dut_engine.run_cmd("nv set system aaa role monitor class nvshow")
        dut_engine.run_cmd("nv config apply --assume-yes")

    def cleanup_base_aaa_config(self, dut_engine: LinuxSshEngine):
        dut_engine.run_cmd('nv unset system config apply ignore "/etc/hosts"')
        dut_engine.run_cmd("nv unset system aaa role admin")
        dut_engine.run_cmd("nv unset system aaa role monitor")
        dut_engine.run_cmd("nv config apply --assume-yes")

    def bypass_password_on_sudo_commands(self, dut_engine: LinuxSshEngine):
        dut_engine.run_cmd(f"echo '{dut_engine.password}' | sudo -S echo")

# -------------------------- Mlx3700 Anaconda Switch ----------------------------


class Mlx3700Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 8
        self.asic_type = 'Spectrum-2'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM2)
        self.show_platform_output.update({
            "product-name": "MSN3700",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["PMIC-1-PSU-12V-RAIL-IN1", "PMIC-1-PSU-12V-RAIL-IN2", "PMIC-2-PSU-12V-RAIL-IN1", "PMIC-2-PSU-12V-RAIL-IN2",
                                "PMIC-3-COMEX-1.8V-RAIL-OUT", "PMIC-3-PSU-12V-RAIL-IN1", "PMIC-3-PSU-12V-RAIL-IN2", "PMIC-4-COMEX-1.2V-RAIL-OUT",
                                "PMIC-4-PSU-12V-RAIL-IN1", "PMIC-4-PSU-12V-RAIL-IN2", "PSU-1-12V-RAIL-OUT", "PSU-1-220V-RAIL-IN", "PSU-2-12V-RAIL-OUT", "PSU-2-220V-RAIL-IN"]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Package-Sensor", "Main-Board-Ambient-Sensor",
                                    "CPU-Core-Sensor-0", "CPU-Core-Sensor-1",
                                    "CPU-Core-Sensor-2", "CPU-Core-Sensor-3",
                                    "PSU1-Temp-Sensor", "PSU2-Temp-Sensor",
                                    "Port-Ambient-Sensor"]

# -------------------------- Mlx2410 Switch -----------------------------


class Mlx2410Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 2
        self.ib_ports_num = 56
        self.asic_type = 'Spectrum'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM1)

        self.show_platform_output.update({
            "product-name": "MSN2410",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["VIN", "VOUT1", "VOUT2"]

    def _init_platform_lists(self):
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=1500, range_max=10000),
            "max-speed": ExpectedString(range_min=18000, range_max=40000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list + self.psu_fan_list \
            + [PlatformConsts.HW_COMP_SWITCH]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0",
                                    "CPU-Core-Sensor-1",
                                    "CPU-Package-Sensor", "Main-Board-Ambient-Sensor",
                                    "PSU1-Temp-Sensor", "PSU2-Temp-Sensor",
                                    "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "FAN4", "PSU", "SYSTEM"]


# -------------------------- Mlx4600 Switch -----------------------------


class Mlx4600Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 8
        self.ib_ports_num = 64
        self.asic_type = 'Spectrum-3'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM3)

        self.show_platform_output.update({
            "product-name": "MSN4600",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["PMIC-1-PSU-12V-RAIL-IN1", "PMIC-2-PSU-12V-RAIL-IN1",
                                "PMIC-2-PSU-12V-RAIL-IN2", "PMIC-3-PSU-12V-RAIL-IN1",
                                "PMIC-3-PSU-12V-RAIL-IN2", "PMIC-4-PSU-12V-RAIL-IN1",
                                "PMIC-4-PSU-12V-RAIL-IN2", "PMIC-5-PSU-12V-RAIL-IN1",
                                "PMIC-5-PSU-12V-RAIL-IN2", "PMIC-6-PSU-12V-RAIL-IN1",
                                "PMIC-6-PSU-12V-RAIL-IN2", "PMIC-7-PSU-12V-RAIL-IN1",
                                "PMIC-7-PSU-12V-RAIL-IN2", "PMIC-8-COMEX-1.8V-RAIL-OUT",
                                "PMIC-8-PSU-12V-RAIL-IN1", "PMIC-8-PSU-12V-RAIL-IN2",
                                "PMIC-9-COMEX-1.2V-RAIL-OUT", "PMIC-9-PSU-12V-RAIL-IN1",
                                "PMIC-9-PSU-12V-RAIL-IN2", "PSU-2R-12V-RAIL-OUT",
                                "PSU-2R-220V-RAIL-IN"]

    def _init_platform_lists(self):
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2000, range_max=10000),
            "max-speed": ExpectedString(range_min=10000, range_max=40000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list + self.psu_fan_list \
            + [PlatformConsts.HW_COMP_SWITCH]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0", "CPU-Core-Sensor-1",
                                    "CPU-Core-Sensor-2", "CPU-Core-Sensor-3",
                                    "CPU-Package-Sensor", "Main-Board-Ambient-Sensor",
                                    "PSU1-Temp-Sensor", "PSU2-Temp-Sensor",
                                    "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN2/1", "FAN3/1"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "PSU", "SYSTEM"]


# -------------------------- Mlx4600C Switch -----------------------------


class Mlx4600cSwitch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 8
        self.ib_ports_num = 64
        self.asic_type = 'Spectrum-3'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM3)

        self.show_platform_output.update({
            "product-name": "MSN4600C",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["PMIC-1-PSU-12V-RAIL-IN1", "PMIC-2-PSU-12V-RAIL-IN1",
                                "PMIC-2-PSU-12V-RAIL-IN2", "PMIC-3-PSU-12V-RAIL-IN1",
                                "PMIC-3-PSU-12V-RAIL-IN2", "PMIC-4-PSU-12V-RAIL-IN1",
                                "PMIC-4-PSU-12V-RAIL-IN2", "PMIC-5-PSU-12V-RAIL-IN1",
                                "PMIC-5-PSU-12V-RAIL-IN2", "PMIC-6-PSU-12V-RAIL-IN1",
                                "PMIC-6-PSU-12V-RAIL-IN2", "PMIC-7-PSU-12V-RAIL-IN1",
                                "PMIC-7-PSU-12V-RAIL-IN2", "PMIC-8-COMEX-1.8V-RAIL-OUT1",
                                "PMIC-8-PSU-12V-RAIL-IN1", "PMIC-8-PSU-12V-RAIL-IN2",
                                "PMIC-9-COMEX-1.2V-RAIL-OUT", "PMIC-9-PSU-12V-RAIL-IN1",
                                "PMIC-9-PSU-12V-RAIL-IN2", "PSU-1R-12V-RAIL-OUT",
                                "PSU-1R-220V-RAIL-IN"]

    def _init_platform_lists(self):
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2000, range_max=10000),
            "max-speed": ExpectedString(range_min=10000, range_max=40000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list + self.psu_fan_list \
            + [PlatformConsts.HW_COMP_SWITCH]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0", "CPU-Core-Sensor-1",
                                    "CPU-Core-Sensor-2", "CPU-Core-Sensor-3",
                                    "CPU-Package-Sensor", "Main-Board-Ambient-Sensor",
                                    "PSU1-Temp-Sensor", "PSU2-Temp-Sensor",
                                    "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN2/1", "FAN3/1"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "PSU", "SYSTEM"]


# -------------------------- Mlx4700 Switch -----------------------------


class Mlx4700Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 8
        self.asic_type = 'Spectrum-3'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM3)

        self.show_platform_output.update({
            "product-name": "MSN4700",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["PMIC-1-PSU-12V-RAIL-IN1", "PMIC-2-PSU-12V-RAIL-IN1", "PMIC-2-PSU-12V-RAIL-IN2",
                                "PMIC-3-PSU-12V-RAIL-IN1", "PMIC-3-PSU-12V-RAIL-IN2", "PMIC-4-PSU-12V-RAIL-IN1",
                                "PMIC-4-PSU-12V-RAIL-IN2", "PMIC-5-PSU-12V-RAIL-IN1", "PMIC-5-PSU-12V-RAIL-IN2",
                                "PMIC-6-PSU-12V-RAIL-IN1", "PMIC-6-PSU-12V-RAIL-IN2", "PMIC-7-PSU-12V-RAIL-IN1",
                                "PMIC-7-PSU-12V-RAIL-IN2", "PMIC-8-COMEX-1.8V-RAIL-OUT", "PMIC-8-PSU-12V-RAIL-IN1",
                                "PMIC-8-PSU-12V-RAIL-IN2", "PMIC-9-COMEX-1.2V-RAIL-OUT", "PMIC-9-PSU-12V-RAIL-IN1",
                                "PMIC-9-PSU-12V-RAIL-IN2", "PSU-2R-12V-RAIL-OUT", "PSU-2R-220V-RAIL-IN"]

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0", "CPU-Core-Sensor-1",
                                    "CPU-Core-Sensor-2", "CPU-Core-Sensor-3", "CPU-Package-Sensor",
                                    "Main-Board-Ambient-Sensor", "PSU1-Temp-Sensor", "PSU2-Temp-Sensor",
                                    "Port-Ambient-Sensor"]


# -------------------------- Mlx5600 Switch -----------------------------


class Mlx5600Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 12
        self.ib_ports_num = 65
        self.asic_type = 'Spectrum-4'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM4)
        self.show_platform_output.update({
            "product-name": "SN5600",
            "asic-model": self.asic_type
        })
        self.voltage_sensors = ["ADAPTER", "IBC-1-13V5-RAIL-OUT", "IBC-1-PWR-CONV-54V-RAIL-IN1",
                                "IBC-2-13V5-RAIL-OUT", "IBC-2-PWR-CONV-54V-RAIL-IN1", "IBC-3-13V5-RAIL-OUT",
                                "IBC-3-PWR-CONV-54V-RAIL-IN1", "IBC-4-13V5-RAIL-OUT", "IBC-4-PWR-CONV-54V-RAIL-IN1",
                                "PMIC-1-PSU-13V5-RAIL-IN1", "PMIC-2-PSU-13V5-RAIL-IN1", "PMIC-3-PSU-13V5-RAIL-IN1",
                                "PMIC-4-PSU-13V5-RAIL-IN1", "PMIC-5-PSU-13V5-RAIL-IN1", "PMIC-6-PSU-13V5-RAIL-IN1",
                                "PMIC-7-PSU-13V5-RAIL-IN1", "PMIC-8-PSU-13V5-RAIL-IN1", "PMIC-9-PSU-13V5-RAIL-IN1",
                                "PMIC-10-HVDD_T03-1V2-RAIL-OUT1", "PMIC-10-HVDD_T47-1V2-RAIL-OUT2", "PMIC-10-PSU-13V5-RAIL-IN1",
                                "PMIC-11-PSU-13V5-RAIL-IN1", "PMIC-11-VDDSCC-0V75-RAIL-OUT1", "PMIC-12-COMEX-VCCSA-OUT2",
                                "PMIC-12-COMEX-VCORE-OUT1", "PMIC-12-PSU-13V5-RAIL-VIN", "PSU-1L-54V-RAIL-OUT",
                                "PSU-1L-220V-RAIL-IN"]

    def _init_platform_lists(self):
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2800, range_max=10000),
            "max-speed": ExpectedString(range_min=10000, range_max=40000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list + self.psu_fan_list \
            + [PlatformConsts.HW_COMP_SWITCH]

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0", "CPU-Core-Sensor-1",
                                    "CPU-Core-Sensor-2", "CPU-Core-Sensor-3", "CPU-Core-Sensor-4",
                                    "CPU-Core-Sensor-5", "CPU-Package-Sensor", "Main-Board-Ambient-Sensor",
                                    "PSU1-Temp-Sensor", "PSU2-Temp-Sensor", "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "FAN4", "PSU", "SYSTEM"]


# -------------------------- Mlx5400 Switch -----------------------------


class Mlx5400Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 12
        self.ib_ports_num = 66
        self.asic_type = 'Spectrum-4'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM4)
        self.show_platform_output.update({
            "product-name": "SN5400",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["ADAPTER", "IBC-1-13V5-RAIL-OUT", "IBC-1-PWR-CONV-54V-RAIL-IN1",
                                "IBC-2-13V5-RAIL-OUT", "IBC-2-PWR-CONV-54V-RAIL-IN1", "IBC-3-13V5-RAIL-OUT",
                                "IBC-3-PWR-CONV-54V-RAIL-IN1", "IBC-4-13V5-RAIL-OUT", "IBC-4-PWR-CONV-54V-RAIL-IN1",
                                "PMIC-1-PSU-13V5-RAIL-IN1", "PMIC-2-PSU-13V5-RAIL-IN1", "PMIC-3-PSU-13V5-RAIL-IN1",
                                "PMIC-4-PSU-13V5-RAIL-IN1", "PMIC-5-PSU-13V5-RAIL-IN1", "PMIC-6-PSU-13V5-RAIL-IN1",
                                "PMIC-7-PSU-13V5-RAIL-IN1", "PMIC-8-PSU-13V5-RAIL-IN1", "PMIC-9-PSU-13V5-RAIL-IN1",
                                "PMIC-10-HVDD_T03-1V2-RAIL-OUT1", "PMIC-10-HVDD_T47-1V2-RAIL-OUT2", "PMIC-10-PSU-13V5-RAIL-IN1",
                                "PMIC-11-PSU-13V5-RAIL-IN1", "PMIC-11-VDDSCC-0V75-RAIL-OUT1", "PMIC-12-COMEX-VCCSA-OUT2",
                                "PMIC-12-COMEX-VCORE-OUT1", "PMIC-12-PSU-13V5-RAIL-VIN", "PSU-1L-54V-RAIL-OUT",
                                "PSU-1L-220V-RAIL-IN"]

    def _init_platform_lists(self):
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2800, range_max=10000),
            "max-speed": ExpectedString(range_min=10000, range_max=40000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list + self.psu_fan_list \
            + [PlatformConsts.HW_COMP_SWITCH]

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0", "CPU-Core-Sensor-1",
                                    "CPU-Core-Sensor-2", "CPU-Core-Sensor-3", "CPU-Core-Sensor-4",
                                    "CPU-Core-Sensor-5", "CPU-Package-Sensor", "Main-Board-Ambient-Sensor",
                                    "PSU1-Temp-Sensor", "PSU2-Temp-Sensor", "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "FAN4", "PSU", "SYSTEM"]

# -------------------------- Mlx5640 Switch -----------------------------


class Mlx5640Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 16
        self.ib_ports_num = 66
        self.asic_type = 'Spectrum-5'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM5)
        self.show_platform_output.update({
            "product-name": "SN5640",
            "asic-model": self.asic_type
        })
        self.voltage_sensors = ["PMIC-1-PSU-13V5-RAIL-IN1", "PMIC-2-PSU-13V5-RAIL-IN1", "PMIC-3-PSU-13V5-RAIL-IN1",
                                "PMIC-4-PSU-13V5-RAIL-IN1", "PMIC-5-PSU-13V5-RAIL-IN1", "PMIC-6-PSU-13V5-RAIL-IN1",
                                "PMIC-7-PSU-13V5-RAIL-IN1", "PMIC-8-PSU-13V5-RAIL-IN1", "PMIC-9-PSU-13V5-RAIL-IN1",
                                "PMIC-10-HVDD_T03-1V2-RAIL-OUT1", "PMIC-10-HVDD_T47-1V2-RAIL-OUT2", "PMIC-10-PSU-13V5-RAIL-IN1",
                                "PMIC-11-PSU-13V5-RAIL-IN1", "PMIC-11-VDDSCC-0V75-RAIL-OUT1", "PMIC-12-COMEX-IN-VDDCR-INPUT-VOLT ",
                                "PMIC-12-COMEX-OUT2-VDDCR_SOC-VOLT", "PMIC-12-COMEX-OUT-VDDCR_CPU-VOLT", "PMIC-13-COMEX-VDD_MEM-INPUT-VOLT",
                                "PMIC-13-COMEX-VDD_MEM-OUTPUT-VOLT", "PSU-1L-12V-RAIL-OUT", "PSU-1L-220V-RAIL-IN", "PSU-2L-12V-RAIL-OUT", "PSU-2L-220V-RAIL-IN",
                                "PSU-3R-12V-RAIL-OUT", "PSU-3R-220V-RAIL-IN", "PSU-4R-12V-RAIL-OUT", "PSU-4R-220V-RAIL-IN"]

    def _init_platform_lists(self):
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2800, range_max=10000),
            "max-speed": ExpectedString(range_min=10000, range_max=40000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list + self.psu_fan_list \
            + [PlatformConsts.HW_COMP_SWITCH]

    def _init_temperature(self):
        super()._init_temperature()
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Package-Sensor", "Main-Board-Ambient-Sensor",
                                    "PSU1-Temp-Sensor", "PSU2-Temp-Sensor", "PSU3-Temp-Sensor", "PSU4-Temp-Sensor",
                                    "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2", "Fan5/1", "Fan5/2"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "FAN4", "FAN5", "PSU", "SYSTEM"]

# -------------------------- Mlx410 Switch -----------------------------


class Mlx4410Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 8
        self.ib_ports_num = 32
        self.asic_type = 'Spectrum-3'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM3)

        self.show_platform_output.update({
            "product-name": "MSN4410",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["PMIC-1-PSU-12V-RAIL-IN", "PMIC-2-PSU-12V-RAIL-IN", "PMIC-3-COMEX-1.05V-RAIL-OUT",
                                "PMIC-3-COMEX-1.8V-RAIL-OUT", "PMIC-3-PSU-12V-RAIL-IN", "PMIC-3-PSU-12V-RAIL-IN1",
                                "PMIC-5-PSU-12V-RAIL-IN", "PMIC-6-COMEX-1.8V-RAIL-OUT1", "PMIC-6-PSU-12V-RAIL-IN1",
                                "PMIC-6-PSU-12V-RAIL-IN2", "PMIC-7-COMEX-1.2V-RAIL-OUT", "PMIC-7-PSU-12V-RAIL-IN1",
                                "PMIC-7-PSU-12V-RAIL-IN2", "PSU-2R-12V-RAIL-OUT", "PSU-2R-220V-RAIL-IN"]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0", "CPU-Core-Sensor-1", "CPU-Core-Sensor-2",
                                    "CPU-Core-Sensor-3", "CPU-Package-Sensor", "Main-Board-Ambient-Sensor",
                                    "PSU1-Temp-Sensor", "PSU2-Temp-Sensor", "Port-Ambient-Sensor"]

# -------------------------- Mlx3750sx Switch -----------------------------


class Mlx3750sxSwitch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 8
        self.ib_ports_num = 32
        self.asic_type = 'Spectrum-2'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM2)

        self.show_platform_output.update({
            "product-name": "MSN3750sx",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["ADAPTER", "PMIC-1-ASIC-1.2V-RAIL-OUT",
                                "PMIC-1-PSU-12V-RAIL-IN", "PMIC-2-ASIC-1.8V-RAIL-OUT",
                                "PMIC-2-ASIC-3.3V-RAIL-OUT", "PMIC-2-PSU-12V-RAIL-IN",
                                "PMIC-6-PSU-12V-RAIL-VIN", "PSU-2-12V-RAIL-OUT",
                                "PSU-2-220V-RAIL-IN"]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Package-Sensor", "Main-Board-Ambient-Sensor",
                                    "CPU-Core-Sensor-0", "CPU-Core-Sensor-1",
                                    "PSU1-Temp-Sensor", "PSU2-Temp-Sensor",
                                    "Port-Ambient-Sensor"]


# -------------------------- Mlx3700cs Switch -----------------------------


class Mlx3700csSwitch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 8
        self.ib_ports_num = 32
        self.asic_type = 'Spectrum-2'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM2)

        self.show_platform_output.update({
            "product-name": "MSN3700cs",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["ADAPTER", "PMIC-1-ASIC-0.8V-VCORE-RAIL-OUT",
                                "PMIC-1-PSU-12V-RAIL-IN1", "PMIC-2-ASIC-3.3V-RAIL-OUT",
                                "PMIC-2-PSU-12V-RAIL-IN1", "PMIC-2-PSU-12V-RAIL-IN2",
                                "PSU-2-12V-RAIL-OUT", "PSU-2-220V-RAIL-IN", "VIN"]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0",
                                    "CPU-Core-Sensor-1", "CPU-Package-Sensor",
                                    "Main-Board-Ambient-Sensor", "PSU1-Temp-Sensor",
                                    "PSU2-Temp-Sensor", "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "FAN4", "PSU", "SYSTEM"]


# -------------------------- Mlx3700c Switch -----------------------------


class Mlx3700cSwitch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 8
        self.ib_ports_num = 32
        self.asic_type = 'Spectrum-2'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM2)

        self.show_platform_output.update({
            "product-name": "MSN3700c",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["PMIC-1-PSU-12V-RAIL-IN1", "PMIC-1-PSU-12V-RAIL-IN2", "PMIC-2-PSU-12V-RAIL-IN1",
                                "PMIC-2-PSU-12V-RAIL-IN2", "PMIC-3-COMEX-1.8V-RAIL-OUT", "PMIC-3-PSU-12V-RAIL-IN1",
                                "PMIC-3-PSU-12V-RAIL-IN2", "PMIC-4-COMEX-1.2V-RAIL-OUT", "PMIC-4-PSU-12V-RAIL-IN1",
                                "PMIC-4-PSU-12V-RAIL-IN2", "PSU-2-12V-RAIL-OUT", "PSU-2-220V-RAIL-IN"]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0", "CPU-Core-Sensor-1",
                                    "CPU-Package-Sensor", "Main-Board-Ambient-Sensor", "PSU1-Temp-Sensor",
                                    "PSU2-Temp-Sensor", "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "FAN4", "PSU", "SYSTEM"]


# -------------------------- Mlx3420 Switch -----------------------------


class Mlx3420Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 4
        self.ib_ports_num = 60
        self.asic_type = 'Spectrum-2'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM2)

        self.show_platform_output.update({
            "product-name": "MSN3420",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["PMIC-3-COMEX-1.8V-RAIL-OUT", "PMIC-3-PSU-12V-RAIL-IN1",
                                "PMIC-3-PSU-12V-RAIL-IN2", "PMIC-4-COMEX-1.8V-RAIL-OUT",
                                "PMIC-4-PSU-12V-RAIL-IN1", "PMIC-4-PSU-12V-RAIL-IN2",
                                "PSU-2-12V-RAIL-OUT", "PSU-2-220V-RAIL-IN",
                                "VIN1", "VIN2", "VOUT1", "VOUT2"]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0",
                                    "CPU-Core-Sensor-1", "CPU-Package-Sensor",
                                    "Main-Board-Ambient-Sensor", "PSU1-Temp-Sensor",
                                    "PSU2-Temp-Sensor", "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2", "FAN5/1", "FAN5/2"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "FAN4", "FAN5", "PSU", "SYSTEM"]


# -------------------------- Mlx2700 Switch -----------------------------


class Mlx2700Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 2
        self.ib_ports_num = 32
        self.asic_type = 'Spectrum'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM1)

        self.show_platform_output.update({
            "product-name": "MSN2700",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["VIN", "VOUT1", "VOUT2"]

    def _init_platform_lists(self):
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=1500, range_max=2000),
            "max-speed": ExpectedString(range_min=18000, range_max=25000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list + self.psu_fan_list \
            + [PlatformConsts.HW_COMP_SWITCH]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0",
                                    "CPU-Core-Sensor-1", "CPU-Package-Sensor",
                                    "Main-Board-Ambient-Sensor", "PSU1-Temp-Sensor",
                                    "PSU2-Temp-Sensor", "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN1/2", "FAN2/1", "FAN2/2", "FAN3/1", "FAN3/2", "FAN4/1", "FAN4/2"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "FAN4", "PSU", "SYSTEM"]


# -------------------------- Mlx2201 Switch -----------------------------


class Mlx2201Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 2
        self.ib_ports_num = 32
        self.asic_type = 'Spectrum'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM1)

        self.show_platform_output.update({
            "product-name": "SN2201",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["MONITOR-CPU-BOARD-P0V6_VTT_DIMM", "MONITOR-CPU-BOARD-P2V5_VPP",
                                "MONITOR-CPU-BOARD-V1P05", "MONITOR-CPU-BOARD-V1P8",
                                "MONITOR-CPU-BOARD-V1P24", "MONITOR-CPU-BOARD-V3P3",
                                "MONITOR-CPU-BOARD-VR_VCCRAM_1V15", "MONITOR-CPU-BOARD-VR_VCC_1V15",
                                "MONITOR-CPU-BOARD-VR_VDDQ_1V20", "MONITOR-CPU-BOARD-VR_VNN_1V05",
                                "PSU-2-12V-RAILOUT", "PSU-2-220V-RAILIN", "VR-IC-PSU-12V-RAIL"]

    def _init_platform_lists(self):
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=2200, range_max=2500),
            "max-speed": ExpectedString(range_min=16000, range_max=22000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list + self.psu_fan_list \
            + [PlatformConsts.HW_COMP_SWITCH]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "CPU-Core-Sensor-0",
                                    "CPU-Core-Sensor-1", "CPU-Package-Sensor",
                                    "Main-Board-Ambient-Sensor", "PSU1-Temp-Sensor",
                                    "PSU2-Temp-Sensor", "Port-Ambient-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN2/1", "FAN3/1", "FAN4/1"]

    def _init_led_list(self):
        self.led_list = ["FAN1", "FAN2", "FAN3", "FAN4", "PSU", "SYSTEM"]


# -------------------------- Mlx2100 Switch -----------------------------


class Mlx2100Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 4
        self.ib_ports_num = 16
        self.asic_type = 'Spectrum'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM1)

        self.show_platform_output.update({
            "product-name": "MSN2100",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["VIN", "VOUT1", "VOUT2"]

    def _init_platform_lists(self):
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=1500, range_max=2500),
            "max-speed": ExpectedString(range_min=16000, range_max=25000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list + self.psu_fan_list \
            + [PlatformConsts.HW_COMP_SWITCH]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "Main-Board-Ambient-Sensor",
                                    "Port-Ambient-Sensor", "core0-Sensor",
                                    "core1-Sensor", "core2-Sensor", "core3-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN2/1", "FAN3/1", "FAN4/1"]

    def _init_led_list(self):
        self.led_list = ["FAN", "PSU1", "PSU2", "SYSTEM"]


# -------------------------- Mlx2010 Switch -----------------------------


class Mlx2010Switch(EthSwitch):
    def __init__(self):
        super().__init__(asic_amount=1)

    def _init_constants(self):
        super()._init_constants()
        self.core_count = 4
        self.ib_ports_num = 22
        self.asic_type = 'Spectrum'
        self.constants.firmware.append(PlatformConsts.FW_SPECTRUM1)

        self.show_platform_output.update({
            "product-name": "MSN2010",
            "asic-model": self.asic_type
        })

        self.voltage_sensors = ["VIN", "VOUT1", "VOUT2"]

    def _init_platform_lists(self):
        self.fan_prop_auto = {"Fan State": "state", "Current Speed (RPM)": "current-speed",
                              "Fan Direction": "direction"}
        self.platform_environment_fan_values = {
            "state": FansConsts.STATE_OK, "direction": None, "current-speed": None,
            "min-speed": ExpectedString(range_min=4500, range_max=5000),
            "max-speed": ExpectedString(range_min=20000, range_max=30000)}
        self.platform_environment_absent_fan_values = {
            "state": FansConsts.STATE_ABSENT, "direction": "N/A", "current-speed": "N/A",
            "min-speed": "N/A", "max-speed": "N/A"}
        self.platform_inventory_items = self.fan_list + self.psu_list \
            + [PlatformConsts.HW_COMP_SWITCH]

    def _init_psu_list(self):
        self.psu_list = ["PSU1", "PSU2"]
        self.psu_fan_list = []
        self.platform_env_psu_prop = ["state"]

    def _init_temperature(self):
        self.temperature_sensors = ["Asic-Temp-Sensor", "Main-Board-Ambient-Sensor",
                                    "Port-Ambient-Sensor", "core0-Sensor",
                                    "core1-Sensor", "core2-Sensor", "core3-Sensor"]

    def _init_fan_list(self):
        self.fan_list = ["FAN1/1", "FAN2/1", "FAN3/1", "FAN4/1"]

    def _init_led_list(self):
        self.led_list = ["FAN", "PSU1", "PSU2", "SYSTEM"]

import logging
import allure
import random
import time
import re
from contextlib import contextmanager

from ngts.nvos_constants.constants_nvos import HealthConsts, SystemConsts, FansConsts
from ngts.nvos_tools.infra.FilesTool import FilesTool
from ngts.nvos_tools.system.System import System

logger = logging.getLogger()


class HWSimulator:

    @staticmethod
    def _read_symlink_target(engine, file_path):
        """Read and return the symlink target of a hw-management sysfs file."""
        target = engine.run_cmd(f'readlink {file_path}').strip()
        logger.info(f"Saved symlink target: {file_path} -> {target}")
        return target

    @staticmethod
    def _inject_value(engine, file_path, value):
        """Replace a sysfs symlink with a regular file containing the given value."""
        engine.run_cmd(f"sudo sh -c 'rm -f {file_path} && echo {value} > {file_path}'")

    @staticmethod
    def _restore_symlink(engine, file_path, symlink_target):
        """Restore a sysfs file's original symlink."""
        engine.run_cmd(f"sudo sh -c 'rm -f {file_path} && ln -s {symlink_target} {file_path}'")

    @staticmethod
    def fan_fw_file_value_get(engine, thermal_directory, fan_id):
        if not fan_id:
            logger.info("No fan specified, skip")
            return
        with allure.step("Read fw file".format(fan_id)):
            file = "fan{}_speed_get".format(fan_id)
            fw_file_val = FilesTool.fw_file_read(engine, file, thermal_directory)
            return fw_file_val

    @staticmethod
    def simulate_health_issue_change_fw_file(engine, new_val, file, thermal_directory):
        """Inject a fake value into a hw-management sysfs file.

        Returns the original symlink target for later restoration.
        """
        file_path = f"{thermal_directory}/{file}"
        symlink_target = HWSimulator._read_symlink_target(engine, file_path)
        HWSimulator._inject_value(engine, file_path, new_val)
        return symlink_target

    @staticmethod
    def restore_fw_file(engine, file, thermal_directory, symlink_target):
        """Restore a hw-management sysfs file's original symlink."""
        file_path = f"{thermal_directory}/{file}"
        HWSimulator._restore_symlink(engine, file_path, symlink_target)

    @staticmethod
    def simulate_fan_fault(engine, thermal_directory, fan_id):
        """Simulate fan fault. Returns symlink target for restoration."""
        if not fan_id:
            logger.info("No fan specified, skip")
            return
        with allure.step("Simulate fan {} fault".format(fan_id)):
            logger.info("Simulate fan {} fault".format(fan_id))
            file = "fan{}_fault".format(fan_id)
            return HWSimulator.simulate_health_issue_change_fw_file(engine, 1, file, thermal_directory)

    @staticmethod
    def simulate_fix_fan_fault(engine, thermal_directory, fan_id, symlink_target):
        """Restore fan fault file's original symlink."""
        if not fan_id:
            logger.info("No fan specified, skip")
            return
        with allure.step("Simulate fix fan {} fault".format(fan_id)):
            logger.info("Simulate fix fan {} fault".format(fan_id))
            file = "fan{}_fault".format(fan_id)
            HWSimulator.restore_fw_file(engine, file, thermal_directory, symlink_target)

    @staticmethod
    def simulate_fan_speed_fault(engine, thermal_directory, fan_id, new_val):
        """Simulate fan speed fault. Returns symlink target for restoration."""
        if not fan_id:
            logger.info("No fan specified, skip")
            return
        with allure.step("Simulate fan {} speed fault".format(fan_id)):
            logger.info("Simulate fan {} speed fault".format(fan_id))
            file = "fan{}_speed_get".format(fan_id)
            return HWSimulator.simulate_health_issue_change_fw_file(engine, new_val, file, thermal_directory)

    @staticmethod
    def simulate_fix_fan_speed_fault(engine, thermal_directory, fan_id, symlink_target):
        """Restore fan speed file's original symlink."""
        if not fan_id:
            logger.info("No fan specified, skip")
            return
        with allure.step("Simulate fix fan {} speed fault".format(fan_id)):
            logger.info("Simulate fix fan {} speed fault".format(fan_id))
            file = "fan{}_speed_get".format(fan_id)
            HWSimulator.restore_fw_file(engine, file, thermal_directory, symlink_target)

    @staticmethod
    def simulate_psu_fault(engine, thermal_directory, psu_id):
        """Simulate PSU fault. Returns symlink target for restoration."""
        if not psu_id:
            logger.info("No psu specified, skip")
            return
        with allure.step("Simulate psu {} fault".format(psu_id)):
            logger.info("Simulate psu {} fault".format(psu_id))
            file = "psu{}_status".format(psu_id)
            return HWSimulator.simulate_health_issue_change_fw_file(engine, 0, file, thermal_directory)

    @staticmethod
    def simulate_fix_psu_fault(engine, thermal_directory, psu_id, symlink_target):
        """Restore PSU status file's original symlink."""
        if not psu_id:
            logger.info("No psu specified, skip")
            return
        with allure.step("Simulate fix psu {} fault".format(psu_id)):
            logger.info("Simulate fix psu {} fault".format(psu_id))
            file = "psu{}_status".format(psu_id)
            HWSimulator.restore_fw_file(engine, file, thermal_directory, symlink_target)

    @staticmethod
    def simulate_psu_temp_fault(engine, thermal_directory, psu_id):
        """Simulate PSU temperature fault. Returns symlink target for restoration.

        Reads the PSU's actual temp1_max threshold and injects a value above it,
        so the fault is detected regardless of PSU model.
        """
        if not psu_id:
            logger.info("No psu specified, skip")
            return
        with allure.step("Simulate psu {} temperature fault".format(psu_id)):
            logger.info("Simulate psu {} temperature fault".format(psu_id))
            max_temp_file = "psu{}_temp1_max".format(psu_id)
            max_temp_path = f"{thermal_directory}/{max_temp_file}"
            max_temp_str = engine.run_cmd(f'cat {max_temp_path}').strip()
            try:
                max_temp = int(max_temp_str)
            except ValueError:
                logger.warning("Could not read max temp from {}, using default 80000".format(max_temp_path))
                max_temp = 70000
            fault_temp = max_temp + 10000
            logger.info("PSU {} max temp: {}, injecting fault temp: {}".format(psu_id, max_temp, fault_temp))
            file = "psu{}_temp1".format(psu_id)
            return HWSimulator.simulate_health_issue_change_fw_file(engine, fault_temp, file, thermal_directory)

    @staticmethod
    def simulate_fix_psu_temp_fault(engine, thermal_directory, psu_id, symlink_target):
        """Restore PSU temperature file's original symlink."""
        if not psu_id:
            logger.info("No psu specified, skip")
            return
        with allure.step("Simulate fix psu {} temperature fault".format(psu_id)):
            logger.info("Simulate fix psu {} temperature fault".format(psu_id))
            file = "psu{}_temp1".format(psu_id)
            HWSimulator.restore_fw_file(engine, file, thermal_directory, symlink_target)

    @staticmethod
    def simulate_and_fix_psu_component_error(devices, engines, show_output):
        thermal_directory = devices.dut.fan_direction_dir
        psu_id_list = []
        for key in show_output:
            psu_id = re.search(r"PSU(\d+).*", key)
            if psu_id:
                if show_output[key][SystemConsts.STATE] == FansConsts.STATE_OK:
                    psu_id_list.append(psu_id.group(1))
        psu_id = random.choice(psu_id_list)

        with allure.step("Simulate PSU temperature fault for chosen PSU:{}".format(psu_id)):
            symlink_target = HWSimulator.simulate_psu_temp_fault(engines.dut, thermal_directory, psu_id)
            time.sleep(10)
        with allure.step("Simulate PSU temperature fix for chosen PSU:{}".format(psu_id)):
            HWSimulator.simulate_fix_psu_temp_fault(engines.dut, thermal_directory, psu_id, symlink_target)
            time.sleep(10)

    @staticmethod
    def simulate_and_fix_fan_component_error(devices, engines):
        thermal_directory = devices.dut.fan_direction_dir
        fan_id = random.randrange(1, len(devices.dut.fan_list) + 1)

        with allure.step("Simulate fan error"):
            symlink_target = HWSimulator.simulate_fan_speed_fault(engines.dut, thermal_directory, fan_id, 1)
            time.sleep(20)

        with allure.step("Fix fan error"):
            HWSimulator.simulate_fix_fan_speed_fault(engines.dut, thermal_directory, fan_id, symlink_target)
            time.sleep(10)

    @staticmethod
    def create_health_component_error_fan(devices, engines):
        with allure.step("Check whether the setup has fans"):
            if 'hw-management-tc.service' not in devices.dut.available_services:
                logger.info("No fan available, skip")
                return

        with allure.step("get random fan id from fans folder"):
            thermal_directory = devices.dut.fan_direction_dir
            fan_id = random.randrange(1, len(devices.dut.fan_list) + 1)

        with allure.step("Simulate fan error"):
            symlink_target = HWSimulator.simulate_fan_speed_fault(engines.dut, thermal_directory, fan_id, 1)
            time.sleep(10)

        with allure.step("Fix fan error"):
            HWSimulator.simulate_fix_fan_speed_fault(engines.dut, thermal_directory, fan_id, symlink_target)
            time.sleep(10)

    @staticmethod
    def find_sensor_dir(engine, base_path, sensor_name):
        """Find the filesystem directory for a sensor by its CLI display name.

        The filesystem uses '+' separators and includes extra tokens like '+Vol',
        '+Volt', '+VinDC' that don't appear in the CLI name. We strip those tokens
        and compare only lowercase alphanumeric characters to find the match.
        """
        output = engine.run_cmd(f'find {base_path} -maxdepth 3 -name input')
        dirs = [line.strip().rsplit('/input', 1)[0] for line in output.splitlines() if line.strip()]

        def normalize(name):
            for token in ('+VinDC', '+Volt', '+Vol'):
                name = name.replace(token, '')
            return re.sub(r'[^a-z0-9]', '', name.lower())

        target = normalize(sensor_name)
        for d in dirs:
            dir_name = d.rstrip('/').split('/')[-1]
            if normalize(dir_name) == target:
                return d

        raise FileNotFoundError(
            f"No directory found for sensor '{sensor_name}' under {base_path}. "
            f"Available: {[d.split('/')[-1] for d in dirs]}"
        )

    @staticmethod
    @contextmanager
    def simulate_sensor(engine, input_path, fake_value, stabilize_delay):
        """Context manager: inject a fake sensor value, yield, then restore the original symlink."""
        original_target = HWSimulator._read_symlink_target(engine, input_path)
        try:
            with allure.step(f"Inject fake value '{fake_value}' into {input_path}"):
                HWSimulator._inject_value(engine, input_path, fake_value)
                time.sleep(stabilize_delay)
            yield
        finally:
            with allure.step(f"Restore original symlink for {input_path}"):
                HWSimulator._restore_symlink(engine, input_path, original_target)
                time.sleep(stabilize_delay)

    @staticmethod
    def reset_health_service(engine):
        with allure.step("Restart health-statsd to clear issues history"):
            logger.info("Restarting health-statsd to clear accumulated issues after test")
            engine.run_cmd("sudo systemctl restart health-statsd")
            time.sleep(10)
            System().health.wait_until_health_status_change_after_reboot(HealthConsts.OK)

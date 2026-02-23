import logging
import allure
import random
import time
import re

from ngts.nvos_constants.constants_nvos import HealthConsts, SystemConsts, FansConsts
from ngts.nvos_tools.infra.FilesTool import FilesTool
from ngts.nvos_tools.system.System import System

logger = logging.getLogger()


class HWSimulator:

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
        cmd = "sudo sed -i 's/.*/" + str(new_val) + "/' " + thermal_directory + "/" + file
        engine.run_cmd(cmd)

    @staticmethod
    def simulate_fan_fault(engine, thermal_directory, fan_id):
        if not fan_id:
            logger.info("No fan specified, skip")
            return
        with allure.step("Simulate fan {} fault".format(fan_id)):
            logger.info("Simulate fan {} fault".format(fan_id))
            file = "fan{}_fault".format(fan_id)
            HWSimulator.simulate_health_issue_change_fw_file(engine, 1, file, thermal_directory)

    @staticmethod
    def simulate_fix_fan_fault(engine, thermal_directory, fan_id):
        if not fan_id:
            logger.info("No fan specified, skip")
            return
        with allure.step("Simulate fix fan {} fault".format(fan_id)):
            logger.info("Simulate fix fan {} fault".format(fan_id))
            file = "fan{}_fault".format(fan_id)
            HWSimulator.simulate_health_issue_change_fw_file(engine, 0, file, thermal_directory)

    @staticmethod
    def simulate_fan_speed_fault(engine, thermal_directory, fan_id, new_val):
        if not fan_id:
            logger.info("No fan specified, skip")
            return
        with allure.step("Simulate fan {} speed fault".format(fan_id)):
            logger.info("Simulate fan {} speed fault".format(fan_id))
            file = "fan{}_speed_get".format(fan_id)
            cmd_to_run = "cat " + thermal_directory + "/{file}".format(file=file)
            speed_value = engine.run_cmd(cmd_to_run)
            HWSimulator.simulate_health_issue_change_fw_file(engine, new_val, file, thermal_directory)
            return speed_value

    @staticmethod
    def simulate_fix_fan_speed_fault(engine, thermal_directory, fan_id, speed_value):
        if not fan_id:
            logger.info("No fan specified, skip")
            return
        with allure.step("Simulate fix fan {} speed fault".format(fan_id)):
            logger.info("Simulate fix fan {} speed fault".format(fan_id))
            file = "fan{}_speed_get".format(fan_id)
            HWSimulator.simulate_health_issue_change_fw_file(engine, speed_value, file, thermal_directory)

    @staticmethod
    def simulate_psu_fault(engine, thermal_directory, psu_id):
        if not psu_id:
            logger.info("No psu specified, skip")
            return
        with allure.step("Simulate psu {} fault".format(psu_id)):
            logger.info("Simulate psu {} fault".format(psu_id))
            file = "psu{}_status".format(psu_id)
            HWSimulator.simulate_health_issue_change_fw_file(engine, 0, file, thermal_directory)

    @staticmethod
    def simulate_fix_psu_fault(engine, thermal_directory, psu_id):
        if not psu_id:
            logger.info("No psu specified, skip")
            return
        with allure.step("Simulate fix psu {} fault".format(psu_id)):
            logger.info("Simulate fix psu {} fault".format(psu_id))
            file = "psu{}_status".format(psu_id)
            HWSimulator.simulate_health_issue_change_fw_file(engine, 1, file, thermal_directory)

    @staticmethod
    def simulate_psu_temp_fault(engine, thermal_directory, psu_id, new_val=80000):
        if not psu_id:
            logger.info("No psu specified, skip")
            return
        with allure.step("Simulate psu {} temperature fault".format(psu_id)):
            logger.info("Simulate psu {} temperature fault".format(psu_id))
            file = "psu{}_temp1".format(psu_id)
            cmd_to_run = "cat " + thermal_directory + "/" + file
            temp1_value = engine.run_cmd(cmd_to_run)
            HWSimulator.simulate_health_issue_change_fw_file(engine, new_val, file, thermal_directory)
            return temp1_value

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
            real_temp = HWSimulator.simulate_psu_temp_fault(engines.dut, thermal_directory, psu_id)
            time.sleep(10)
        with allure.step("Simulate PSU temperature fix for chosen PSU:{}".format(psu_id)):
            HWSimulator.simulate_psu_temp_fault(engines.dut, thermal_directory, psu_id, real_temp)
            time.sleep(10)

    @staticmethod
    def simulate_and_fix_fan_component_error(devices, engines):
        thermal_directory = devices.dut.fan_direction_dir
        fan_id = random.randrange(1, len(devices.dut.fan_list) + 1)

        with allure.step("Simulate fan error"):
            real_speed = HWSimulator.simulate_fan_speed_fault(engines.dut, thermal_directory, fan_id, 1)
            time.sleep(20)

        with allure.step("Fix fan error"):
            HWSimulator.simulate_fix_fan_speed_fault(engines.dut, thermal_directory, fan_id, real_speed)
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
            real_speed = HWSimulator.simulate_fan_speed_fault(engines.dut, thermal_directory, fan_id, 1)
            time.sleep(10)

        with allure.step("Fix fan error"):
            HWSimulator.simulate_fix_fan_speed_fault(engines.dut, thermal_directory, fan_id, real_speed)
            time.sleep(10)

    @staticmethod
    def reset_health_service(engine):
        with allure.step("Restart health-statsd to clear issues history"):
            logger.info("Restarting health-statsd to clear accumulated issues after test")
            engine.run_cmd("sudo systemctl restart health-statsd")
            time.sleep(10)
            System().health.wait_until_health_status_change_after_reboot(HealthConsts.OK)

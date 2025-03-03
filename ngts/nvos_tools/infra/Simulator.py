import logging
import allure

logger = logging.getLogger()


class HWSimulator:

    @staticmethod
    def simulate_health_issue_change_fw_file(engine, new_val, file, thermal_directory):
        cmd = "sudo sed -i 's/.*/" + str(new_val) + "/' " + thermal_directory + "/" + file
        engine.run_cmd(cmd)

    @staticmethod
    def simulate_fan_fault(engine, thermal_directory, fan_id):
        with allure.step("Simulate fan {} fault".format(fan_id)):
            logger.info("Simulate fan {} fault".format(fan_id))
            file = "fan{}_fault".format(fan_id)
            HWSimulator.simulate_health_issue_change_fw_file(engine, 1, file, thermal_directory)

    @staticmethod
    def simulate_fix_fan_fault(engine, thermal_directory, fan_id):
        with allure.step("Simulate fix fan {} fault".format(fan_id)):
            logger.info("Simulate fix fan {} fault".format(fan_id))
            file = "fan{}_fault".format(fan_id)
            HWSimulator.simulate_health_issue_change_fw_file(engine, 0, file, thermal_directory)

    @staticmethod
    def simulate_fan_speed_fault(engine, thermal_directory, fan_id, new_val):
        with allure.step("Simulate fan {} speed fault".format(fan_id)):
            logger.info("Simulate fan {} speed fault".format(fan_id))
            file = "fan{}_speed_get".format(fan_id)
            cmd_to_run = "cat " + thermal_directory + "/{file}".format(file=file)
            speed_value = engine.run_cmd(cmd_to_run)
            HWSimulator.simulate_health_issue_change_fw_file(engine, new_val, file, thermal_directory)
            return speed_value

    @staticmethod
    def simulate_fix_fan_speed_fault(engine, thermal_directory, fan_id, speed_value):
        with allure.step("Simulate fix fan {} speed fault".format(fan_id)):
            logger.info("Simulate fix fan {} speed fault".format(fan_id))
            file = "fan{}_speed_get".format(fan_id)
            HWSimulator.simulate_health_issue_change_fw_file(engine, speed_value, file, thermal_directory)

    @staticmethod
    def simulate_psu_fault(engine, thermal_directory, psu_id):
        with allure.step("Simulate psu {} fault".format(psu_id)):
            logger.info("Simulate psu {} fault".format(psu_id))
            file = "psu{}_status".format(psu_id)
            HWSimulator.simulate_health_issue_change_fw_file(engine, 0, file, thermal_directory)

    @staticmethod
    def simulate_fix_psu_fault(engine, thermal_directory, psu_id):
        with allure.step("Simulate fix psu {} fault".format(psu_id)):
            logger.info("Simulate fix psu {} fault".format(psu_id))
            file = "psu{}_status".format(psu_id)
            HWSimulator.simulate_health_issue_change_fw_file(engine, 1, file, thermal_directory)

    @staticmethod
    def simulate_psu_temp_fault(engine, thermal_directory, psu_id, new_val=80000):
        with allure.step("Simulate psu {} temperature fault".format(psu_id)):
            logger.info("Simulate psu {} temperature fault".format(psu_id))
            file = "psu{}_temp1".format(psu_id)
            cmd_to_run = "cat " + thermal_directory + "/" + file
            temp1_value = engine.run_cmd(cmd_to_run)
            HWSimulator.simulate_health_issue_change_fw_file(engine, new_val, file, thermal_directory)
            return temp1_value

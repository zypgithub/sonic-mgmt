import re
import logging

logger = logging.getLogger()


class SonicHwMgmtCli:

    def __init__(self, engine):
        self.engine = engine

    def get_hw_version(self):
        """
        This method is to get hw version
        :return: hw_version
        """
        hw_version_output = self.engine.run_cmd("sudo dpkg -l | grep hw-m")
        reg_hw_version = r".*ii  hw-management.*mlnx.(?P<hw_version>\d+.\d+.*)\s+amd64.*"
        res_hw_version = re.search(reg_hw_version, hw_version_output)
        if res_hw_version:
            hw_version = re.sub(r'[a-zA-Z-\s]', '', res_hw_version.groupdict()["hw_version"])
            logger.info(f"hw_version is :{hw_version}")
            return hw_version
        else:
            raise Exception(f"Did not find the hw version from {hw_version_output}")

    def show_hw_mgmt_status(self):
        """
        This method is to show hw-management service status
        :return: the cmd output
        """
        return self.engine.run_cmd("sudo service hw-management status")

    def start_hw_mgmt(self):
        """
        This method is to start hw-management service
        :return: the cmd output
        """
        return self.engine.run_cmd("sudo service hw-management start")

    def stop_hw_mgmt(self):
        """
        This method is to stop hw-management service
        :return: the cmd output
        """
        return self.engine.run_cmd("sudo service hw-management stop")

    def show_thermal_control_status(self):
        """
        This method is to show thermal control service status
        :return: the cmd output
        """
        return self.engine.run_cmd(" sudo service hw-management-tc status")

    def is_thermal_control_running(self):
        """
        This method is to show thermal control service status
        :return: True or False
        """
        return "active" == self.engine.run_cmd("sudo systemctl is-active hw-management-tc.service").strip()

    def start_thermal_control(self):
        """
        This method is to start thermal control service
        :return: the cmd output
        """
        return self.engine.run_cmd("sudo service hw-management-tc start")

    def stop_thermal_control(self):
        """
        This method is to stop thermal control service
        :return: the cmd output
        """
        return self.engine.run_cmd("sudo service hw-management-tc stop")

    def suspend_thermal_control(self):
        """
        This method is to suspend thermal control service
        :return: the cmd output
        """
        self.engine.run_cmd("sudo touch /var/run/hw-management/config/suspend")
        self.engine.run_cmd("sudo chown admin /var/run/hw-management/config/suspend")
        return self.engine.run_cmd("sudo echo 1 > /var/run/hw-management/config/suspend")

    def resume_thermal_control(self):
        """
        This method is to resume thermal control service
        :return: the cmd output
        """
        return self.engine.run_cmd("sudo rm -f /var/run/hw-management/config/suspend")

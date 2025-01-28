import logging
import os

logger = logging.getLogger()


class CumulusInstallationSteps:

    @staticmethod
    def pre_installation_steps(setup_info, base_version='', target_version=''):
        assert target_version, 'Argument "target_version" must be provided for installing Cumulus'

    @staticmethod
    def post_installation_steps(setup_info):
        """
        Post-installation steps for NVOS NOS
            Update /etc/sudoers file to permit NOPASSWD for sudo
        """
        cl_password = os.getenv("CUMULUS_SWITCH_PASSWORD")
        root_password = os.getenv("CUMULUS_ROOT_PASSWORD")
        for dut in setup_info['duts']:
            logging.info("Updating /etc/sudoers file to permit NOPASSWD for sudo")
            dut['engine'].run_cmd_set(["sudo sed -i --follow-symlinks 's/%sudo.*ALL=(ALL:ALL) ALL/%sudo ALL=(ALL:ALL) NOPASSWD: ALL/' /etc/sudoers",
                                       cl_password], patterns_list=["password_for_cumulus"])
            logging.info("Updated /etc/sudoers file to permit NOPASSWD for sudo")
            logging.info("Permitting root login for dut")
            dut['engine'].run_cmd_set(["sudo passwd root", root_password, root_password], patterns_list=["New password", "Retype new password", "passwd: password updated successfully"])
            dut['engine'].run_cmd_set(["nv set system ssh-server permit-root-login enabled", "nv config apply -y"], patterns_list=["applied_and_saved"])
            logging.info("Root login for dut enabled")
            logging.info("Updating /etc/apt/sources.list")
            CumulusInstallationSteps.update_apt_sources_list(dut)

    @staticmethod
    def update_apt_sources_list(dut):
        cmd = "sudo sed -i  -e \'s/# deb/deb/g\' -e \'2d;3d\' -e \'4i deb  [trusted=yes] https://urm.nvidia.com/artifactory/sw-nbu-cl-debian-local/ CumulusLinux-5 upstream\' /etc/apt/sources.list"
        dut['engine'].run_cmd(cmd)
        logging.info(dut['engine'].run_cmd("sudo cat /etc/apt/sources.list"))

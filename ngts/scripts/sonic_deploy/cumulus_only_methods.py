import logging
import os

logger = logging.getLogger()


class CumulusInstallationSteps:

    @staticmethod
    def pre_installation_steps(setup_info, base_version='', target_version=''):
        assert target_version, 'Argument "target_version" must be provided for installing Cumulus'

    @staticmethod
    def post_installation_steps(setup_info, is_performance):
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
            if is_performance:
                logging.info(f"Updating the hostname for performance setups.")
                dut_hostname = dut['dut_alias'].replace("_", "-")
                dut['engine'].run_cmd_set([f"nv set system hostname {dut_hostname}", "nv config apply -y"], patterns_list=["applied_and_saved"])
                logging.info("Bringing up all the ports")
                dut['cli'].interface.initialize_physical_ports()
                logging.info("Restarting lldpd to clear LLDP neighbors")
                dut['engine'].run_cmd("sudo systemctl restart lldpd")

    @staticmethod
    def update_apt_sources_list(dut):
        #  below command would enable the bookworm debian repository and replace the cumulus dev repository with release one
        bookworm_repo_enable = "\'s/#\\ *deb/deb/g\'"
        cumulus_dev_repo_disable = "\'2d;3d\'"
        cumulus_release_repo_enable = "\'4i deb  https://apt.cumulusnetworks.com/repo CumulusLinux-d12-latest cumulus upstream netq\'"
        cmd = f"sudo sed -i  -e {bookworm_repo_enable} -e {cumulus_dev_repo_disable} -e {cumulus_release_repo_enable} /etc/apt/sources.list"
        dut['engine'].run_cmd(cmd)
        logging.info(dut['engine'].run_cmd("sudo cat /etc/apt/sources.list"))

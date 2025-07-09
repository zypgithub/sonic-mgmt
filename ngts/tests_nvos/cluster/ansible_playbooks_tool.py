import logging
import random

from ngts.tests_nvos.cluster.cluster_consts import AnsbilePlaybooksConsts
from ngts.nvos_tools.infra.DutUtilsTool import run_ssh_command

logger = logging.getLogger()


class AnsiblePlaybooksTool:

    @staticmethod
    def run_playbook_and_check_result(inventory_file, playbook, arguments):
        '''
        @Summary:
            This function will run the given playbook, and check if it failed.
        @param inventory_file:
                Setup info under test.
                /root/.ansible/collections/ansible_collections/nvidia/NVlinkClusterManagement/clusters/inventory/nvos_v2/oberon-gb/8gpus/israel-cluster.yml
        @param playbook:
            Examples:
                run_mpi_basic_test.yml
                provision_compute_node_firmware_cpld.yml
        @param arguments:
                Arguments for the playbook.
                -e "nvflash_path=nvflash/nvflash_eng" --skip-tags 'check_status'
        @return: returns the status of the playbook. True for passed, and false for failed.
        '''
        playbook_cmd = f"{AnsbilePlaybooksConsts.PATH_TO_NVIDIA_CLUSTER_MGMT}playbooks/{playbook} {arguments} -i {inventory_file}"
        logger.info(f"Running command: {playbook_cmd}")
        ansible_machine = random.choice(AnsbilePlaybooksConsts.ANSIBLE_MACHINES)
        # SSH connection information
        username = AnsbilePlaybooksConsts.ANSIBLE_MACHINES_CREDENTIALS[ansible_machine]['user']
        password = AnsbilePlaybooksConsts.ANSIBLE_MACHINES_CREDENTIALS[ansible_machine][
            'pass']  # It's better to use SSH keys
        playbook_output = run_ssh_command(playbook_cmd, ansible_machine, username, password)
        logger.info(f"Playbook output:\n{playbook_output}")
        status = AnsiblePlaybooksTool._check_if_playbook_failed(playbook_output)
        return status

    @staticmethod
    def _check_if_playbook_failed(playbook_output):
        '''
        @Summary:
            This function checks if the playbook failed or not, by checking the output of the playbook run,
            and making sure all the failed are --> failed=0 (which means no failures were detected.
        @param playbook_output:
            Output of a playbook.
        @return: True in case the playbook's output indicates no failures.
                 False in case the playbook's output indicates failures.
        '''
        lines = playbook_output.split('\n')
        # Flags to start processing after detecting "PLAY RECAP"
        process = False
        failed_counts = []
        success = True
        for line in lines:
            if "PLAY RECAP" in line:
                process = True
            elif process:
                if "failed=" in line:
                    # Extract and print the failed count
                    failed_part = line.split('failed=')[1].split()[0]
                    if failed_part != '0':
                        failed_counts.append(line)
        if failed_counts != []:
            print('\n'.join([str(item) for item in failed_counts]))
            success = False
        if not process:
            success = False
            logger.info("PLAY RECAP was not found in playbook's output. Execution was not as expected.")
        return success

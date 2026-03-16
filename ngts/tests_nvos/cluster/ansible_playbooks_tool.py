import logging
import random

from ngts.tests_nvos.cluster.cluster_consts import AnsiblePlaybooksConsts
from ngts.nvos_tools.infra.DutUtilsTool import run_ssh_command

logger = logging.getLogger()


class AnsiblePlaybooksTool:
    """
    Tool for executing Ansible playbooks and validating results.

    Supports both OLD and NEW Ansible collection approaches.
    """

    @staticmethod
    def run_playbook_and_check_result(inventory_file, playbook, arguments):
        """
        OLD METHOD: Run playbook with old NVlinkClusterManagement collection.

        Kept for backward compatibility with existing code.

        Args:
            inventory_file: Path to inventory file
            playbook: Playbook name (e.g., 'provision_compute_node_software_nvl5.yml')
            arguments: Arguments string (e.g., '-vvv')

        Returns:
            bool: True if playbook succeeded, False if failed
        """
        playbook_cmd = f"ansible-playbook {playbook} {arguments} -i {inventory_file}"
        logger.info(f"Running command: {playbook_cmd}")

        ansible_machine = random.choice(AnsiblePlaybooksConsts.ANSIBLE_MACHINES)
        username = AnsiblePlaybooksConsts.ANSIBLE_MACHINES_CREDENTIALS[ansible_machine]['user']
        password = AnsiblePlaybooksConsts.ANSIBLE_MACHINES_CREDENTIALS[ansible_machine]['pass']

        playbook_output = run_ssh_command(playbook_cmd, ansible_machine, username, password)
        logger.info(f"Playbook output:\n{playbook_output}")

        status = AnsiblePlaybooksTool._check_if_playbook_failed(playbook_output)
        return status

    @staticmethod
    def run_playbook_by_key(playbook_key, inventory_file, component_paths_dict,
                            ansible_machine=None, username=None, password=None):
        """
        Run a playbook using its key from AnsiblePlaybooksConsts.PLAYBOOKS.

        Args:
            playbook_key: Key from PLAYBOOKS dict (e.g., 'SOFTWARE_INSTALL')
            inventory_file: Path to inventory YAML file
            component_paths_dict: Dict mapping parameter names to file paths
            ansible_machine: (Optional) Specific ansible server to use (for consistency)
            username: (Optional) SSH username for ansible server
            password: (Optional) SSH password for ansible server

        Returns:
            bool: True if playbook succeeded, False if failed
        """
        # Build the command
        playbook_cmd = AnsiblePlaybooksConsts.get_playbook_command(
            playbook_key, inventory_file, component_paths_dict
        )

        logger.info(f"Running playbook '{playbook_key}'")
        logger.info(f"Command: {playbook_cmd}")

        # Use provided ansible machine or select random
        if not ansible_machine:
            ansible_machine = random.choice(AnsiblePlaybooksConsts.ANSIBLE_MACHINES)
            username = AnsiblePlaybooksConsts.ANSIBLE_MACHINES_CREDENTIALS[ansible_machine]['user']
            password = AnsiblePlaybooksConsts.ANSIBLE_MACHINES_CREDENTIALS[ansible_machine]['pass']

        logger.info(f"Using ansible machine: {ansible_machine}")

        # Execute via SSH
        playbook_output = run_ssh_command(playbook_cmd, ansible_machine, username, password)

        # FIX: Check for None output from SSH failure
        if playbook_output is None:
            logger.error(f"SSH command failed - no output received from {ansible_machine}")
            return False

        logger.info(f"Playbook output:\n{playbook_output}")

        # Check result
        status = AnsiblePlaybooksTool._check_if_playbook_failed(playbook_output)

        if status:
            logger.info(f"Playbook '{playbook_key}' completed successfully")
        else:
            logger.error(f"Playbook '{playbook_key}' FAILED")

        return status

    @staticmethod
    def run_playbook_command(playbook_cmd):
        """
        Run a pre-built ansible-playbook command directly.

        Args:
            playbook_cmd: Complete ansible-playbook command string

        Returns:
            bool: True if playbook succeeded, False if failed

        Example:
            >>> cmd = 'ansible-playbook /path/playbook.yml -i /path/inv.yml -e "param=value"'
            >>> AnsiblePlaybooksTool.run_playbook_command(cmd)
            True
        """
        logger.info(f"Running command: {playbook_cmd}")

        # Select ansible machine
        ansible_machine = random.choice(AnsiblePlaybooksConsts.ANSIBLE_MACHINES)
        username = AnsiblePlaybooksConsts.ANSIBLE_MACHINES_CREDENTIALS[ansible_machine]['user']
        password = AnsiblePlaybooksConsts.ANSIBLE_MACHINES_CREDENTIALS[ansible_machine]['pass']

        # Execute via SSH
        playbook_output = run_ssh_command(playbook_cmd, ansible_machine, username, password)
        logger.info(f"Playbook output:\n{playbook_output}")

        # Check result
        status = AnsiblePlaybooksTool._check_if_playbook_failed(playbook_output)

        if status:
            logger.info("Playbook completed successfully")
        else:
            logger.error("Playbook FAILED")

        return status

    @staticmethod
    def _check_if_playbook_failed(playbook_output):
        """
        Check if playbook failed by analyzing PLAY RECAP section.

        Args:
            playbook_output: Output from ansible-playbook command (can be None)

        Returns:
            bool: True if no failures detected, False if failures found

        Logic:
            - Looks for "PLAY RECAP" section
            - Checks all lines with "failed="
            - If any line has failed!=0, playbook failed
        """
        # FIX: Handle None output gracefully
        if playbook_output is None:
            logger.error("Cannot parse playbook output - output is None")
            return False

        lines = playbook_output.split('\n')
        process = False
        failed_counts = []
        success = True

        for line in lines:
            if "PLAY RECAP" in line:
                process = True
            elif process:
                if "failed=" in line:
                    # Extract failed count
                    failed_part = line.split('failed=')[1].split()[0]
                    if failed_part != '0':
                        failed_counts.append(line)

        if failed_counts:
            logger.error("Failed tasks detected:")
            for line in failed_counts:
                logger.error(f"  {line}")
            success = False

        if not process:
            success = False
            logger.error("PLAY RECAP not found in playbook output - execution may have been interrupted")

        return success

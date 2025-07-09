import os
import logging
import random
import time

from ngts.tools.align_components.Constants import NogaConstants
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.tools.align_components.align_fw_components import get_switch_info, create_json_dict
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.cluster.ansible_playbooks_tool import AnsiblePlaybooksTool
from ngts.tests_nvos.cluster.cluster_consts import AnsbilePlaybooksConsts as Ansible
from ngts.nvos_tools.infra.DutUtilsTool import run_ssh_command

logger = logging.getLogger()


def test_align_cluster_recipe(setup_name, fw_versions_json_file, ansible_inventory_file):
    with allure.step("Extract switch provisioning info - Prod/Dev"):
        switch_info = get_switch_info(setup_name)
        json_dict = create_json_dict(fw_versions_json_file)
        provisioning = switch_info[NogaConstants.ATTRIBUTES][NogaConstants.HARDWARE_COMPONENTS][
            NogaConstants.BIOS_VERSION]
        provisioning = 'prod' if provisioning == 'OPN' else 'dev'

    inventory_file = ansible_inventory_file
    ansible_machine = random.choice(Ansible.ANSIBLE_MACHINES)
    # SSH connection information
    username = Ansible.ANSIBLE_MACHINES_CREDENTIALS[ansible_machine]['user']
    password = Ansible.ANSIBLE_MACHINES_CREDENTIALS[ansible_machine][
        'pass']  # It's better to use SSH keys
    failed_components = []
    for component in Ansible.COMPONENTS:
        package_path = json_dict[provisioning][component]['latest']['path']
        package_name = json_dict[provisioning][component]['latest']['filename']
        try:
            logger.info("Sleeping for 20 seconds between playbooks execution")
            time.sleep(20)
            fetch_and_install(component, package_path, package_name, inventory_file, ansible_machine, username, password)
        except Exception as e:
            failed_components.append(component)
            logger.info(e)

    assert failed_components == [], f"Components {failed_components} align failed - see logs."


def fetch_and_install(component, package_path, package_name, inventory_file, ansible_machine, username, password):
    try:
        package_download_full_path = None
        # RM and CUDA does not need downloading the packages.
        if package_path.startswith("http") and ("cuda" not in component):
            with allure.step(f"Downloading package - {package_path} For Component {component}"):
                download_package = f'curl -s -w "%{{http_code}}" -o /tmp/{package_name} -u \'{NvosConst.SONIC_SERVICE_ACCOUNT}:{NvosConst.SONIC_SERVICE_ACCOUNT_API_KEY}\' "{package_path}" | grep -q "^200$" && echo "Download successful" || echo "Download failed"'
                logger.info(f"Running curl command {download_package}")
                output = run_ssh_command(download_package, ansible_machine, username, password)
                logger.info(f"{output}")
                assert "Download successful" in output, f"Curl command failed - {download_package}"

            logger.info("Verify package is downloaded successfully")
            package_download_full_path = f"/tmp/{package_name}"
            verify_cmd = f'ls -lh {package_download_full_path}'
            logger.info(f"Running cmd {verify_cmd}")
            output = run_ssh_command(verify_cmd, ansible_machine, username, password)
            logger.info(output)
            assert f'/tmp/{package_name}' in output, "File not found after download"

        with allure.step(f"Adjust {Ansible.CONFIG_FILE} content"):
            replace_yaml_value_remote(Ansible.CONFIG_FILE_UPDATE_PER_COMPONENT[component], package_download_full_path if package_download_full_path else package_path, Ansible.CONFIG_FILE, ansible_machine, username, password)

        playbook = Ansible.PLAYBOOKS_NAMES[component]
        with allure.step(f"Updating component {component} - Running playbook {playbook}"):
            status = AnsiblePlaybooksTool.run_playbook_and_check_result(inventory_file, playbook, Ansible.PLAYBOOKS_ARGUMENTS[component])
            assert status, f'Playbook {playbook} failed - Check logs'

    finally:
        if package_download_full_path:
            logger.info("Delete downloaded file")
            try:
                run_ssh_command(f"rm -rf {package_download_full_path}", ansible_machine, username, password)
            except Exception as e:
                logger.info(f"Failed to delete with the following issue {e}")


def replace_yaml_value_remote(key, new_value, file_path_remote, ansible_machine, username, password):
    sed_cmd = f"sed -i 's|^{key}:.*|{key}: \"{new_value}\"|' {file_path_remote}"
    return run_ssh_command(sed_cmd, ansible_machine, username, password)


def check_curl_status(output):
    known_errors = {
        "unauthorized": "Curl failed due to unauthorized access",
        "no such file or directory": "Curl failed to create output file",
        "could not resolve": "Curl failed due to DNS resolution",
        "error": "Curl failed due to general error"
    }
    for substring, message in known_errors.items():
        assert substring not in output.lower(), message

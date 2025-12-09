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
                # ROBUST DOWNLOAD IMPLEMENTATION
                # Previous curl command was flaky due to:
                # 1. Not following redirects (Artifactory often returns 302 to S3)
                # 2. Only checking HTTP code, not curl exit status
                # 3. No protection against partial downloads
                # 4. No built-in retry for network hiccups
                #
                # New approach:
                # - Downloads to .part file first, only moves on complete success
                # - Follows redirects (-L) and fails fast on HTTP errors (-f)
                # - Built-in curl retry (3x) + app-level retry (3x) = up to 9 total attempts
                # - Proper timeouts to prevent hanging
                # - Checks both curl exit code AND HTTP status for reliable error detection
                download_package = f"""
url="{package_path}"
out="/tmp/{package_name}"
temp_out="/tmp/{package_name}.part"

# Remove any existing partial file
rm -f "$temp_out"

# Robust curl with built-in retry, redirect following, and proper error handling
code=$(curl -fL -sS \\
  --retry 3 --retry-delay 2 --retry-all-errors \\
  --connect-timeout 15 --max-time 1800 \\
  -u "{NvosConst.SONIC_SERVICE_ACCOUNT}:{NvosConst.SONIC_SERVICE_ACCOUNT_API_KEY}" \\
  -o "$temp_out" -w '%{{http_code}}' "$url")
rc=$?

if [ $rc -eq 0 ] && [ "$code" = "200" ]; then
  mv "$temp_out" "$out"
  echo "Download successful"
else
  rm -f "$temp_out"
  echo "Download failed (curl_rc=$rc http_code=$code)"
fi
"""
                logger.info(f"Running robust curl command for {package_name}")

                # Application-level retry (in addition to curl's built-in retry)
                download_successful = False
                for attempt in range(1, 4):  # Reduced to 3 since curl has its own retry
                    logger.info(f"Download attempt {attempt}/3")
                    output = run_ssh_command(download_package, ansible_machine, username, password)
                    logger.info(f"Attempt {attempt} output: {output}")

                    if "Download successful" in output:
                        logger.info(f"Download successful on attempt {attempt}")
                        download_successful = True
                        break
                    else:
                        logger.warning(f"Download failed on attempt {attempt}: {output}")
                        if attempt < 3:
                            logger.info("Waiting 10 seconds before retry...")
                            time.sleep(10)

                assert download_successful, f"Curl command failed after 3 attempts with built-in retries - {package_name}"

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

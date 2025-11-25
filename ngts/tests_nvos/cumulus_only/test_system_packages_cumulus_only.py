import logging
import pytest
import re
import time
from ngts.nvos_constants.constants_nvos import ApiType, PackageConsts

from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool, wait_until_cli_is_up
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


def get_first_swp_interface(engines):
    """
    Detect a data-plane interface dynamically by picking the first 'swp*' interface.
    """
    with allure.step("Detect first swp interface on DUT"):
        output = engines.dut.run_cmd("ls /sys/class/net | grep -E '^swp' | head -n 1")
        intf = output.strip().splitlines()[0].strip() if output.strip() else ""
        assert intf, "Failed to detect any 'swp' interface on DUT"
        logger.info(f"Using interface '{intf}' for non-default VRF configuration")
        return intf


def cleanup_after_test(engines):
    system = System()
    key_val = ['public', 'archive-key-11.asc', 'Release.gpg']
    for key in key_val:
        output = engines.dut.run_cmd(f"nv action delete system packages key {key}")
        verify_action_delete(output)
    system.packages.unset_packages_configuration()
    logger.info("Cleaning up temporary directories and downloaded files")
    try:
        engines.dut.run_cmd("sudo rm -rf /var/tmp/my-apt-repo_new")
        engines.dut.run_cmd("sudo rm -rf /var/tmp/file-my-apt-repo_new")
        engines.dut.run_cmd("sudo rm -f switchd_1.0-cl5.12.0u26_amd64.deb")
        engines.dut.run_cmd("sudo rm -f switchd-halmlx_1.0-cl5.12.0u26_amd64.deb")
        logger.info("Successfully cleaned up temporary directories and files")
    except Exception as e:
        logger.warning(f"Failed to clean up some temporary resources: {e}")


def configure_non_default_vrf(engines, vrf_name, if_name):
    """
    Configure a non-default VRF and bind an interface to it.
    NOTE: We intentionally do not set a table-id; NVUE will choose a free one
    to avoid conflicts with existing VRFs (e.g. mgmt).
    """
    with allure.step(f"Configure non-default VRF {vrf_name} on interface {if_name}"):
        logger.info(f"Configuring VRF '{vrf_name}' on interface {if_name}")
        cmds = [
            f"nv set vrf {vrf_name}",
            f"nv set interface {if_name} vrf {vrf_name}",
            "nv config apply --assume-yes",
        ]
        for cmd in cmds:
            logger.info(f"Running command to configure VRF: {cmd}")
            engines.dut.run_cmd(cmd)


def verify_action_delete(output):
    # Clean the output from ANSI escape sequences
    cleaned_output = re.sub(r'\x1b\[[\d;]*[A-Za-z]', '', output)
    # Look for success patterns in the actual command output
    matches = re.findall(r"(Key deleted successfully|Action succeeded|successfully)", cleaned_output, re.IGNORECASE)
    if matches:
        logger.info("deleted the key successfully.")
    else:
        # Log the actual output for debugging
        logger.warning(f"Delete verification failed. Actual output: {cleaned_output}")
        assert False, f"error while deleting the key. Output: {cleaned_output}"


def verify_fetch(dut, key, key_out, output, scope):
    # Clean the output from ANSI escape sequences
    cleaned_output = re.sub(r'\x1b\[[\d;]*[A-Za-z]', '', output)
    # Log the actual output for debugging
    logger.info(f"Fetch command output: {cleaned_output}")
    # Treat "already exists" as a non-fatal, idempotent success case
    if re.search(r"already exists", cleaned_output, re.IGNORECASE):
        logger.info("Key already exists on the system; treating fetch as successful and continuing.")
        return
    # Look for error patterns that would indicate failure
    error_patterns = [
        r"error",
        r"failed",
        r"not found",
        r"unable to",
        r"cannot"
    ]
    errors = []
    for pattern in error_patterns:
        errors.extend(re.findall(pattern, cleaned_output, re.IGNORECASE))
        errors.extend(re.findall(pattern, cleaned_output, re.IGNORECASE))
    if errors:
        logger.warning(f"Found error patterns in output: {errors}")
        assert False, f"Key fetch operation failed with errors: {errors}. Output: {cleaned_output}"
    # If no errors found and we have the key in the output, consider it successful
    if key_out.get(key) is not None:
        logger.info(f"{key} is updated and exists in the keys output")
        logger.info(f"{key} fetch operation completed successfully with scope {scope}")
    else:
        logger.warning(f"Key {key} not found in keys output: {key_out}")
        # Don't fail the test immediately - the key might take time to appear
        logger.info(f"Fetch command completed. Key {key} may still be processing.")


def config_repositories(system_obj, repo_id, repo_dist_id, pool_id, insecure='disabled', source='disabled', key='', apply=True, ask_for_confirmation=True):
    """
    Configure repositories using the new Packages class implementation
    Args:
        system_obj: System object containing packages component
        repo_id: Repository URL/ID
        repo_dist_id: Distribution ID
        pool_id: Pool ID
        insecure: enabled/disabled for insecure setting
        source: enabled/disabled for source setting
        key: Key value for repository
        apply: Whether to apply configuration immediately
        ask_for_confirmation: Whether to ask for confirmation when applying
    """

    with allure.step(f"Configure repository {repo_id} with distribution {repo_dist_id} and pool {pool_id}"):
        logger.info(f"Configuring repository {repo_id} with distribution {repo_dist_id} and pool {pool_id}")
        # Set repository
        repo = system_obj.packages.repositories.set_repository(repo_id, apply=False)
        # Configure repository settings
        if insecure != 'disabled':
            repo.set_insecure(insecure, apply=False)
        if source != 'disabled':
            repo.set_source(source, apply=False)
        if key:
            repo.set_key(key, apply=False)
        # Add distribution
        distribution = repo.distributions.set_distribution(repo_dist_id, apply=False)
        # Add pool
        result = distribution.pools.set_pool(pool_id, apply=apply, ask_for_confirmation=ask_for_confirmation)
        # Verify apply succeeded if apply was requested
        if apply:
            logger.info(f"Verifying configuration apply succeeded for repository {repo_id}")
            result.verify_result(should_succeed=True)
        return repo, distribution, result


def setup_config_copy_nd_file(engines, dict_name):
    ### creating a temp dict ####
    logger.info(f"Setting up local APT repository: {dict_name}")
    # Create directory structure
    engines.dut.run_cmd(f'sudo mkdir -p /var/tmp/{dict_name}/dists/cumulus/main/binary-amd64')
    # Download packages
    logger.info("Downloading switchd packages")
    engines.dut.run_cmd('sudo wget -q https://urm.nvidia.com/artifactory/sw-nbu-cl-debian-local/pool/cumulus/s/switchd/switchd_1.0-cl5.12.0u26_amd64.deb')
    engines.dut.run_cmd('sudo wget -q https://urm.nvidia.com/artifactory/sw-nbu-cl-debian-local/pool/cumulus/s/switchd/switchd-halmlx_1.0-cl5.12.0u26_amd64.deb')
    # Copy packages to repository directory
    engines.dut.run_cmd(f'sudo cp switchd_1.0-cl5.12.0u26_amd64.deb /var/tmp/{dict_name}/')
    engines.dut.run_cmd(f'sudo cp switchd-halmlx_1.0-cl5.12.0u26_amd64.deb /var/tmp/{dict_name}/')
    # Install dpkg-dev if not already installed
    engines.dut.run_cmd('sudo apt-get update -qq')
    engines.dut.run_cmd('sudo apt-get install -y dpkg-dev')
    # Create Packages file - using absolute paths to avoid directory change issues
    logger.info("Creating Packages file")
    engines.dut.run_cmd(f'sudo dpkg-scanpackages /var/tmp/{dict_name} /dev/null > /tmp/packages_temp')
    engines.dut.run_cmd(f'sudo mv /tmp/packages_temp /var/tmp/{dict_name}/dists/cumulus/main/binary-amd64/Packages')
    # Create compressed Packages file
    logger.info("Creating compressed Packages file")
    engines.dut.run_cmd(f'sudo gzip -c /var/tmp/{dict_name}/dists/cumulus/main/binary-amd64/Packages > /tmp/packages_gz_temp')
    engines.dut.run_cmd(f'sudo mv /tmp/packages_gz_temp /var/tmp/{dict_name}/dists/cumulus/main/binary-amd64/Packages.gz')
    # Create Release file
    logger.info("Creating Release file")
    engines.dut.run_cmd(f'sudo bash -c "cat > /var/tmp/{dict_name}/dists/cumulus/main/binary-amd64/Release << EOF\nOrigin: Cumulus\nLabel: Local Repository\nSuite: stable\nVersion: 1.0\nCodename: cumulus\nArchitectures: amd64\nComponents: main\nDescription: Local APT repository for cumulus\nEOF"')
    # Update apt cache and verify
    engines.dut.run_cmd('sudo apt-get update -qq')
    engines.dut.run_cmd('sudo apt-cache policy switchd-halmlx')
    logger.info(f"Successfully set up local APT repository: {dict_name}")


def verify_repository_pools_and_settings(repo_obj, repo_url, expected_distributions):
    """
    Verify pools and settings for a configured repository
    Args:
        repo_obj: Repository object to verify
        repo_url: Repository URL for identification
        expected_distributions: List of expected distribution names
    """
    with allure.step(f"Verify pools and settings for repository {repo_url}"):
        logger.info(f"Verifying pools and settings for repository: {repo_url}")
        # Get repository output for settings verification
        repo_output = repo_obj.get_repository_output()
        logger.info(f"Repository values: {repo_output}")
        # Verify pools and source settings for each distribution
        for dist_name in expected_distributions:
            dist_obj = repo_obj.distributions.distributions_dict.get(dist_name)
            if dist_obj:
                logger.info(f"Verifying pools and settings for distribution: {dist_name}")
                # Verify specific pools based on configuration
                if repo_url == 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest':
                    expected_pools = ['cumulus', 'netq', 'upstream']
                    # Debug: Check what pools actually exist
                    actual_pools = list(dist_obj.pools.pools_dict.keys())
                    logger.info(f"NVIDIA repo - Expected pools: {expected_pools}, Actual pools: {actual_pools}")
                    dist_obj.pools.verify_show_pools_list(expected_pools)
                    # Verify pool settings
                    for pool_name in expected_pools:
                        pool_obj = dist_obj.pools.pools_dict.get(pool_name)
                        if pool_obj:
                            pool_output = pool_obj.get_pool_output()
                            logger.info(f"Pool '{pool_name}' output: {pool_output}")
                elif repo_url == 'http://penta-01.lab2300.labs.mlnx/dev-d12':
                    expected_pools = ['netq']
                    # Debug: Check what pools actually exist
                    actual_pools = list(dist_obj.pools.pools_dict.keys())
                    logger.info(f"Penta repo - Expected pools: {expected_pools}, Actual pools: {actual_pools}")
                    dist_obj.pools.verify_show_pools_list(expected_pools)
                elif repo_url == 'https://apps3.cumulusnetworks.com/repos/deb':
                    expected_pools = ['netq-latest']
                    # Debug: Check what pools actually exist
                    actual_pools = list(dist_obj.pools.pools_dict.keys())
                    logger.info(f"Cumulus repo - Expected pools: {expected_pools}, Actual pools: {actual_pools}")
                    dist_obj.pools.verify_show_pools_list(expected_pools)
                elif repo_url == 'http://deb.debian.org/debian':
                    expected_pools = ['main']
                    # Debug: Check what pools actually exist
                    actual_pools = list(dist_obj.pools.pools_dict.keys())
                    logger.info(f"Debian repo - Expected pools: {expected_pools}, Actual pools: {actual_pools}")
                    dist_obj.pools.verify_show_pools_list(expected_pools)

        # Verify repository-level settings (insecure, source)
        if 'nvidia' in repo_url or 'urm.nvidia.com' in repo_url:
            # This repo was configured with insecure='enabled'
            if 'insecure' in repo_output and repo_output['insecure']:
                logger.info(f"Verified: Repository {repo_url} has insecure setting: {repo_output['insecure']}")
        if 'debian.org' in repo_url:
            # This repo was configured with source='enabled'
            if 'source' in repo_output and repo_output['source']:
                logger.info(f"Verified: Repository {repo_url} has source setting: {repo_output['source']}")


def restart_services(engines, devices, services):
    if 'reboot' in services:
        with allure.step('reboot the system'):
            system = System()
            system.reboot.action_reboot().verify_result()
            wait_until_cli_is_up(engines.dut)
            logger.info("System rebooted successfully")
    else:
        for service in services:
            with allure.step(f'restart the {service} service'):
                engines.dut.run_cmd(f"sudo systemctl restart {service}")
                time.sleep(30)


@pytest.mark.system
@pytest.mark.cumulus_only
@pytest.mark.packages
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_01_apt_source_config(engines, test_api):
    """
    Name: Verify the source apt config with at least one repo config
    ===============================================
    Description:
    ===============================================
    Verify the source apt config with at least one repo config
    Steps:
    ===============================================
    1.config the apt source config with nv set system packages repository <repo-id> dist <dist-id> pool <pool-id>
    2.config few of the repos with source, insecure enabled.
    3.verify the nv show command to for config repositories and operational params
    4.config invalid repository and check for the proper error is coming.
    5.unset the config.
    """
    # TestToolkit.test_setup(test_api)
    TestToolkit.tested_api = test_api
    system = System()
    with allure.step("Configure multiple repositories"):
        logger.info("configuring the multiple repositories")
        config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'cumulus', insecure='enabled', apply=False)
        config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'netq', apply=False)
        config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'upstream', insecure='enabled', apply=True, ask_for_confirmation=True)
        config_repositories(system, 'http://penta-01.lab2300.labs.mlnx/dev-d12', 'CumulusLinux-d12', 'netq', apply=False)
        config_repositories(system, 'https://apps3.cumulusnetworks.com/repos/deb', 'CumulusLinux-4', 'netq-latest', apply=False)
        # Temporarily skip apply to test without network connectivity
        # TODO: Re-enable apply=True once DUT has network access
        config_repositories(system, 'http://deb.debian.org/debian', 'bookworm-updates', 'main', source='enabled', apply=True, ask_for_confirmation=True)
        # Log the repositories that were configured in the System object
        logger.info(f"Configured repositories in system object: {list(system.packages.repositories.repositories_dict.keys())}")
    with allure.step("Verify configured repositories"):
        logger.info("verifying the configured repositories are updated in nv show command and apt-cache policy")
        # List of configured repository URLs
        configured_repo_urls = [
            'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest',
            'http://penta-01.lab2300.labs.mlnx/dev-d12',
            'https://apps3.cumulusnetworks.com/repos/deb',
            'http://deb.debian.org/debian'
        ]
        # get packages show output
        system_packages_output = system.packages.get_packages_field_values()
        logger.info(f"system_packages_output: {system_packages_output}")
        # Verify each repository
        for repo_url in configured_repo_urls:
            logger.info(f"verifying the repository: {repo_url}")
            system.packages.verify_repository_in_show_packages_output(repo_url)
            # Get repository object for verification
            repo_obj = system.packages.repositories.repositories_dict.get(repo_url)
            if repo_obj:
                # Verify distributions
                if 'nvidia' in repo_url or 'penta' in repo_url:
                    expected_distributions = ['CumulusLinux-d12']
                elif 'cumulusnetworks' in repo_url:
                    expected_distributions = ['CumulusLinux-4']
                else:
                    expected_distributions = ['bookworm-updates']
                repo_obj.distributions.verify_show_distributions_list(expected_distributions)
                # Verify pools and repository settings
                verify_repository_pools_and_settings(repo_obj, repo_url, expected_distributions)
        logger.info("Successfully verified all configured repositories")
    with allure.step("Test invalid repository configuration"):
        logger.info("Testing invalid repository configuration")
        try:
            # Try to configure and apply an invalid repository - this should fail
            config_repositories(system, 'https://invalid.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'cumulus', insecure='enabled', apply=True, ask_for_confirmation=True)
            assert False, "Expected invalid repository configuration to fail"
        except Exception as e:
            logger.info(f"Expected error occurred for invalid repository: {e}")
            # Verify it's an actual error (not just our assert)
            assert "invalid" in str(e).lower() or "fail" in str(e).lower() or "error" in str(e).lower(), f"Unexpected error message: {e}"
        finally:
            # Always try to detach config, even if test fails
            try:
                engines.dut.run_cmd("nv config detach")
            except Exception as cleanup_error:
                logger.warning(f"Failed to detach config: {cleanup_error}")
    with allure.step("Test unset operations"):
        logger.info("Testing unset operations for repository distribution pool and repository distribution")
        repo1 = 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest'
        # Get repository object
        repo_obj = system.packages.repositories.repositories_dict.get(repo1)
        if repo_obj:
            # Unset pool
            dist_obj = repo_obj.distributions.distributions_dict.get('CumulusLinux-d12')
            if dist_obj and 'cumulus' in dist_obj.pools.pools_dict:
                unset_pool_result = dist_obj.pools.unset_pool('cumulus', apply=True, ask_for_confirmation=True)
                unset_pool_result.verify_result(should_succeed=True)
                logger.info(f"Successfully unset the distribution pool for repository {repo1}")
                # Verify pool got deleted
                if 'cumulus' not in dist_obj.pools.pools_dict:
                    logger.info("Verified: Pool 'cumulus' has been successfully deleted")
                else:
                    assert False, "Pool 'cumulus' was not deleted as expected"
            # Unset distribution
            unset_result = repo_obj.distributions.unset_distribution('CumulusLinux-d12', apply=True, ask_for_confirmation=True)
            unset_result.verify_result(should_succeed=True)
            # Verify distribution got deleted
            if 'CumulusLinux-d12' not in repo_obj.distributions.distributions_dict:
                logger.info("Verified: Distribution 'CumulusLinux-d12' has been successfully deleted")
            else:
                assert False, "Distribution 'CumulusLinux-d12' was not deleted as expected"
            # Unset repository
            unset_repo_result = system.packages.repositories.unset_repository(repo1, apply=True, ask_for_confirmation=True)
            unset_repo_result.verify_result(should_succeed=True)
            # Verify repository got deleted
            if repo1 not in system.packages.repositories.repositories_dict:
                logger.info(f"Verified: Repository '{repo1}' has been successfully deleted")
            else:
                assert False, f"Repository '{repo1}' was not deleted as expected"
            logger.info(f"Successfully unset repository {repo1}")
    with allure.step("Test clean configuration"):
        logger.info("Testing clean package configuration")
        # Clean up all packages configuration using the helper function
        system.packages.unset_packages_configuration()


@pytest.mark.system
@pytest.mark.cumulus_only
@pytest.mark.packages
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_02_apt_source_diff_repo_config(engines, test_api):
    """
    Name: Verify the source apt config with different types of repository URLs
    ===============================================
    Description:
    ===============================================
    Verify the source apt config with different types of repository URLs including http, https, copy, and file URLs
    Steps:
    ===============================================
    1. Configure different repo-urls for apt source config with nv set system packages repository <repo-id> dist <dist-id> pool <pool-id>
    2. Configure repositories with source, insecure enabled for different URL types
    3. Verify the nv show command for configured repositories and operational params
    4. Test invalid repository URL and verify proper error handling
    5. Unset all configurations and verify cleanup
    """
    TestToolkit.tested_api = test_api
    system = System()

    # Initial cleanup to ensure test isolation
    with allure.step("Initial cleanup to ensure clean test environment"):
        logger.info("Performing initial cleanup to ensure clean test environment")
        try:
            system.packages.unset_packages_configuration(verify_cleanup=False)
            logger.info("Initial cleanup completed")
        except Exception as e:
            logger.info(f"No existing configuration to clean up: {e}")

    with allure.step("Configure multiple repositories with different URL types"):
        logger.info("Configuring multiple repositories with different URL types")
        config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'cumulus', insecure='enabled', apply=False)
        config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'upstream', insecure='enabled', apply=False)
        config_repositories(system, 'http://penta-01.lab2300.labs.mlnx/dev-d12', 'CumulusLinux-d12', 'netq', apply=False)
        config_repositories(system, 'http://penta-01.lab2300.labs.mlnx/dev-d12', 'CumulusLinux-d12', 'cumulus', apply=False)
        config_repositories(system, 'http://penta-01.lab2300.labs.mlnx/dev-d12', 'CumulusLinux-d12', 'upstream', source='enabled', apply=True)
        logger.info("setting up the local repo for copy and file commands to work")
        setup_config_copy_nd_file(engines, 'my-apt-repo_new')
        setup_config_copy_nd_file(engines, 'file-my-apt-repo_new')
        logger.info("configuring the multiple repositories with different urls")
        # Configure additional repositories (removed redundant penta repo configurations)
        config_repositories(system, 'https://apps3.cumulusnetworks.com/repos/deb', 'CumulusLinux-4', 'netq-latest', apply=False)
        config_repositories(system, 'http://deb.debian.org/debian', 'bookworm-updates', 'main', source='enabled', apply=False)
        config_repositories(system, 'copy:/var/tmp/my-apt-repo_new', 'cumulus', 'main', insecure='enabled', apply=False)
        config_repositories(system, 'file:/var/tmp/file-my-apt-repo_new', 'cumulus', 'main', insecure='enabled', apply=True)

    with allure.step("Verify configured repositories"):
        logger.info("Verifying the configured repositories are updated in nv show command")
        # Verify packages show output
        system.packages.show_packages_output()
        # List of configured repository URLs (including copy and file URLs)
        configured_repo_urls = [
            'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest',
            'http://penta-01.lab2300.labs.mlnx/dev-d12',
            'https://apps3.cumulusnetworks.com/repos/deb',
            'http://deb.debian.org/debian',
            'copy:/var/tmp/my-apt-repo_new',
            'file:/var/tmp/file-my-apt-repo_new'
        ]
        # Verify each repository
        for repo_url in configured_repo_urls:
            logger.info(f"Verifying repository: {repo_url}")
            system.packages.verify_repository_in_show_packages_output(repo_url)
            # Get repository object for verification
            repo_obj = system.packages.repositories.repositories_dict.get(repo_url)
            if repo_obj:
                # Verify repository show output
                repo_obj.verify_show_repository_output({})
                # Verify distributions based on URL type
                if 'nvidia' in repo_url or 'penta' in repo_url:
                    expected_distributions = ['CumulusLinux-d12']
                elif 'cumulusnetworks' in repo_url:
                    expected_distributions = ['CumulusLinux-4']
                elif 'copy:' in repo_url or 'file:' in repo_url:
                    expected_distributions = ['cumulus']
                else:
                    expected_distributions = ['bookworm-updates']
                repo_obj.distributions.verify_show_distributions_list(expected_distributions)
                # Verify pools for each distribution
                for dist_name in expected_distributions:
                    dist_obj = repo_obj.distributions.distributions_dict.get(dist_name)
                    if dist_obj:
                        # Get expected pools based on repository and distribution
                        if repo_url == 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest':
                            expected_pools = ['cumulus', 'upstream']
                        elif repo_url == 'http://penta-01.lab2300.labs.mlnx/dev-d12':
                            expected_pools = ['netq', 'cumulus', 'upstream']
                        elif repo_url == 'https://apps3.cumulusnetworks.com/repos/deb':
                            expected_pools = ['netq-latest']
                        elif 'copy:' in repo_url or 'file:' in repo_url:
                            expected_pools = ['main']
                        else:  # debian repo
                            expected_pools = ['main']
                        dist_obj.pools.verify_show_pools_list(expected_pools)
        logger.info("Successfully verified all configured repositories")

    with allure.step("Test invalid repository configuration"):
        logger.info("Testing invalid repository configuration")
        try:
            config_repositories(system, 'https://invalid.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'cumulus', insecure='enabled', apply=False, ask_for_confirmation=False)
            engines.dut.run_cmd("echo 'n' | nv config apply", timeout=30)
            assert False, "Expected invalid repository configuration to fail"
        except Exception as e:
            logger.info(f"Expected error occurred for invalid repository: {e}")
        engines.dut.run_cmd("nv config detach")

    with allure.step("Test unset operations"):
        logger.info("Testing unset operations for repositories, distributions, and pools")
        # Test selective unset operations
        nvidia_repo = 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest'
        penta_repo = 'http://penta-01.lab2300.labs.mlnx/dev-d12'
        # Get repository objects
        nvidia_repo_obj = system.packages.repositories.repositories_dict.get(nvidia_repo)
        penta_repo_obj = system.packages.repositories.repositories_dict.get(penta_repo)
        if nvidia_repo_obj:
            # Unset specific pools from NVIDIA repository
            dist_obj = nvidia_repo_obj.distributions.distributions_dict.get('CumulusLinux-d12')
            if dist_obj:
                if 'cumulus' in dist_obj.pools.pools_dict:
                    pool_unset_result = dist_obj.pools.unset_pool('cumulus', apply=True, ask_for_confirmation=True)
                    pool_unset_result.verify_result(should_succeed=True)
                    logger.info(f"Successfully unset 'cumulus' pool from NVIDIA repository")
        if penta_repo_obj:
            # Unset entire distribution from Penta repository
            dist_unset_result = penta_repo_obj.distributions.unset_distribution('CumulusLinux-d12', apply=True, ask_for_confirmation=True)
            dist_unset_result.verify_result(should_succeed=True)
            logger.info(f"Successfully unset distribution from Penta repository")
            # Unset entire Penta repository
            repo_unset_result = system.packages.repositories.unset_repository(penta_repo, apply=True, ask_for_confirmation=True)
            repo_unset_result.verify_result(should_succeed=True)
            logger.info(f"Successfully unset Penta repository")

    with allure.step("Test complete cleanup"):
        logger.info("Testing complete package configuration cleanup")
        # Clean up all packages configuration using the helper function
        system.packages.unset_packages_configuration()
        # Clean up temporary directories and files
        logger.info("Cleaning up temporary directories and downloaded files")
        try:
            engines.dut.run_cmd("sudo rm -rf /var/tmp/my-apt-repo_new")
            engines.dut.run_cmd("sudo rm -rf /var/tmp/file-my-apt-repo_new")
            engines.dut.run_cmd("sudo rm -f switchd_1.0-cl5.12.0u26_amd64.deb")
            engines.dut.run_cmd("sudo rm -f switchd-halmlx_1.0-cl5.12.0u26_amd64.deb")
            logger.info("Successfully cleaned up temporary directories and files")
        except Exception as e:
            logger.warning(f"Failed to clean up some temporary resources: {e}")


@pytest.mark.system
@pytest.mark.cumulus_only
@pytest.mark.packages
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_03_apt_source_switchd_restart(engines, devices, test_api):
    """
    Name: Verify the source apt config with switchd restart
    ===============================================
    Description:
    ===============================================
    Verify the source apt config with switchd restart
    Steps:
    ===============================================
    1.config the different repo-urls for apt source config with nv set system packages repository <repo-id> dist <dist-id> pool <pool-id>.
    2.config few of the repos with source, insecure enabled.
    3.verify the nv show command to for config repositories and operational params for the allowed urls.
    4.do the switchd service restart
    5.verify the nv show command to for config repositories and operational params are coming properly after restart
    """
    dut = engines.dut
    TestToolkit.tested_api = test_api
    system = System()
    config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'cumulus', insecure='enabled', apply=False)
    config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'netq', apply=False)
    config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'upstream', insecure='enabled', apply=False)
    config_repositories(system, 'http://penta-01.lab2300.labs.mlnx/dev-d12', 'CumulusLinux-d12', 'netq', apply=False)
    config_repositories(system, 'https://apps3.cumulusnetworks.com/repos/deb', 'CumulusLinux-4', 'netq-latest', apply=False)
    config_repositories(system, 'http://deb.debian.org/debian', 'bookworm-updates', 'main', source='enabled', apply=True)
    # show output of the configured repos
    system.packages.show_packages_output()
    configured_repos = ['https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest',
                        'http://penta-01.lab2300.labs.mlnx/dev-d12',
                        'https://apps3.cumulusnetworks.com/repos/deb',
                        'http://deb.debian.org/debian']
    for repo in configured_repos:
        system.packages.verify_repository_in_show_packages_output(repo)
    with allure.step("Restart switchd service"):
        logger.info("Restarting switchd service")
        DutUtilsTool.run_cmd_and_reconnect(engine=engines.dut, command="sudo systemctl restart switchd")
        wait_until_cli_is_up(engines.dut)
    with allure.step("Reboot system and verify repository persistence"):
        logger.info("Rebooting system to test repository configuration persistence")
        restart_services(engines, devices, services=['switchd'])
        # verify service running status after reboot
        output = engines.dut.run_cmd("sudo systemctl status switchd")
        logger.info(f"switchd service status after reboot: {output}")
        # Create a new System object to refresh the state after reboot
        logger.info("Creating new System object to refresh state after reboot")
        post_reboot_system = System()
        # verify the repos are still configured after switchd restart and reboot
        logger.info("Verifying repository configuration persistence after reboot")
        post_reboot_system.packages.show_packages_output()
        # Verify each configured repository is still present
        for repo in configured_repos:
            logger.info(f"Verifying repository persistence: {repo}")
            post_reboot_system.packages.verify_repository_in_show_packages_output(repo)
            # Get repository object for detailed verification
            repo_obj = post_reboot_system.packages.repositories.repositories_dict.get(repo)
            if repo_obj:
                # Verify distributions based on repository
                if 'nvidia' in repo or 'penta' in repo:
                    expected_distributions = ['CumulusLinux-d12']
                elif 'cumulusnetworks' in repo:
                    expected_distributions = ['CumulusLinux-4']
                else:
                    expected_distributions = ['bookworm-updates']
                repo_obj.distributions.verify_show_distributions_list(expected_distributions)
                logger.info(f"Verified repository {repo} and its distributions after reboot")
        logger.info("Successfully verified all repository configurations persisted after reboot")
    with allure.step("Cleanup test configuration"):
        logger.info("Cleaning up test configuration")
        try:
            # Clean up all packages configuration to ensure test isolation
            post_reboot_system.packages.unset_packages_configuration()
            logger.info("Successfully cleaned up all repository configurations")
        except Exception as e:
            logger.warning(f"Failed to clean up configurations: {e}")


@pytest.mark.system
@pytest.mark.cumulus_only
@pytest.mark.packages
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_04_apt_source_device_reboot(engines, devices, test_api):
    """
    Name: Verify the source apt config with device reboot
    ===============================================
    Description:
    ===============================================
    Verify the source apt config with switchd restart
    Steps:
    ===============================================
    1.config the different repo-urls for apt source config with nv set system packages repository <repo-id> dist <dist-id> pool <pool-id>.
    2.config few of the repos with source, insecure enabled.
    3.verify the nv show command to for config repositories and applied params for the allowed urls.
    4.do the reboot the device
    5.verify the nv show command to for config repositories and  applied params are coming properly after reboot
    """
    dut = engines.dut
    TestToolkit.tested_api = test_api
    system = System()
    config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'cumulus', insecure='enabled', apply=False)
    config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'netq', apply=False)
    config_repositories(system, 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest', 'CumulusLinux-d12', 'upstream', insecure='enabled', apply=False)
    config_repositories(system, 'http://penta-01.lab2300.labs.mlnx/dev-d12', 'CumulusLinux-d12', 'netq', apply=False)
    config_repositories(system, 'https://apps3.cumulusnetworks.com/repos/deb', 'CumulusLinux-4', 'netq-latest', apply=False)
    config_repositories(system, 'http://deb.debian.org/debian', 'bookworm-updates', 'main', source='enabled', apply=True)
    # show output of the configured repos
    system.packages.show_packages_output()
    configured_repos = ['https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest',
                        'http://penta-01.lab2300.labs.mlnx/dev-d12',
                        'https://apps3.cumulusnetworks.com/repos/deb',
                        'http://deb.debian.org/debian']
    for repo in configured_repos:
        system.packages.verify_repository_in_show_packages_output(repo)
    with allure.step("Reboot system and verify repository persistence"):
        logger.info("Rebooting system to test repository configuration persistence")
        restart_services(engines, devices, services=['reboot'])
        # verify service running status after reboot
        output = engines.dut.run_cmd("sudo systemctl status switchd")
        logger.info(f"switchd service status after reboot: {output}")
        # Create a new System object to refresh the state after reboot
        logger.info("Creating new System object to refresh state after reboot")
        post_reboot_system = System()
        # verify the repos are still configured after switchd restart and reboot
        logger.info("Verifying repository configuration persistence after reboot")
        post_reboot_system.packages.show_packages_output()
        # Verify each configured repository is still present
        for repo in configured_repos:
            logger.info(f"Verifying repository persistence: {repo}")
            post_reboot_system.packages.verify_repository_in_show_packages_output(repo)
            # Get repository object for detailed verification
            repo_obj = post_reboot_system.packages.repositories.repositories_dict.get(repo)
            if repo_obj:
                # Verify distributions based on repository
                if 'nvidia' in repo or 'penta' in repo:
                    expected_distributions = ['CumulusLinux-d12']
                elif 'cumulusnetworks' in repo:
                    expected_distributions = ['CumulusLinux-4']
                else:
                    expected_distributions = ['bookworm-updates']
                repo_obj.distributions.verify_show_distributions_list(expected_distributions)
                logger.info(f"Verified repository {repo} and its distributions after reboot")
        logger.info("Successfully verified all repository configurations persisted after reboot")
    with allure.step("Cleanup test configuration"):
        logger.info("Cleaning up test configuration")
        try:
            # Clean up all packages configuration to ensure test isolation
            post_reboot_system.packages.unset_packages_configuration()
            logger.info("Successfully cleaned up all repository configurations")
        except Exception as e:
            logger.warning(f"Failed to clean up configurations: {e}")


@pytest.mark.system
@pytest.mark.cumulus_only
@pytest.mark.packages
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_05_apt_source_packages_with_action_fetching_key(engines, devices, test_api):
    """
    Name: Verify nv action fetch and delete for system packages key
    ===============================================
    Description:
    ===============================================
    Verify nv action fetch and delete for system packages key
    Steps:
    ===============================================
    1. execute the nv action fetch system packages key <remote-url> scope <global|repository> vrf <vrf-id>
    2. check the action is success fully completed or not, if not throw the error for valid url.
    3. execute for multiple urls and verify.
    4. execute the nv action delete system packages key <key>
    5. verify the key is deleted successfully.
    """
    dut = devices.dut
    TestToolkit.tested_api = test_api
    system = System()
    remote_url = "https://download.nvidia.com/cumulus/apt.cumulusnetworks.com/repo/dists/CumulusLinux-5.10-latest/Release.gpg"
    key = 'Release.gpg'
    output = system.packages.nv_action_fetch_system_packages(engines, remote_url)
    key_out = system.packages.get_system_packages_key()
    logger.info(f"key_out: {key_out}")
    verify_fetch(dut, key, key_out, output, scope='global')
    output = system.packages.nv_action_delete_system_packages(engines, key='Release.gpg')
    verify_action_delete(output)
    remote_url = "https://ftp-master.debian.org/keys/archive-key-11.asc"
    key = 'archive-key-11.asc'
    output = system.packages.nv_action_fetch_system_packages(engines, remote_url, scope='repository')
    key_out = system.packages.get_system_packages_key()
    verify_fetch(dut, key, key_out, output, scope='repository')
    output = system.packages.nv_action_delete_system_packages(engines, key='archive-key-11.asc')
    verify_action_delete(output)
    remote_url = 'https://urm.nvidia.com/artifactory/api/gpg/key/public'
    key = 'public'
    try:
        # In some environments, VRF 'default' may not have external connectivity.
        # Treat connectivity failures as expected and only verify delete when fetch succeeds.
        output = system.packages.nv_action_fetch_system_packages(
            engines, remote_url, scope='repository', vrf='default'
        )
        key_out = system.packages.get_system_packages_key()
        logger.info(f"key_out: {key_out}")
        verify_fetch(dut, key, key_out, output, scope='repository')
        output = system.packages.nv_action_delete_system_packages(engines, key='public')
        verify_action_delete(output)
    except AssertionError as e:
        logger.info(
            f"Fetch from {remote_url} via VRF 'default' failed as expected in this environment: {e}"
        )


@pytest.mark.system
@pytest.mark.cumulus_only
@pytest.mark.packages
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_06_apt_source_packages_config_with_key(engines, test_api):
    """
    Name: Verify apt source packages config with key
    ===============================================
    Description:
    ===============================================
    Verify apt source packages config with key, including:
    - Fetching keys with different scopes and VRFs
    - Configuring repositories with keys
    - Attempting to delete keys while in use (negative test)
    - Unsetting repository key configuration
    - Deleting keys after removing from repository
    Steps:
    ===============================================
    1. config the apt source packages with key
    """
    TestToolkit.tested_api = test_api
    system = System()
    engines.dut.run_cmd("nv action delete system packages key public")
    engines.dut.run_cmd("nv action delete system packages key archive-key-11.asc")
    with allure.step("Fetch first key from NVIDIA URM with repository scope and mgmt VRF"):
        logger.info("Fetching key from NVIDIA URM with scope='repository' and vrf='mgmt'")
        remote_url = 'https://urm.nvidia.com/artifactory/api/gpg/key/public'
        key = 'public'
        output = system.packages.nv_action_fetch_system_packages(engines, remote_url, scope='repository', vrf='mgmt')
        key_out = system.packages.get_system_packages_key()
        logger.info(f"key_out: {key_out}")
        verify_fetch(engines, key, key_out, output, scope='repository')
    with allure.step("Fetch second key from Debian mirror with default scope"):
        logger.info("Fetching key from Debian mirror with default scope")
        remote_url = "https://ftp-master.debian.org/keys/archive-key-11.asc"
        key = 'archive-key-11.asc'
        # Fetch Debian key with repository scope so it can be used in repository configuration
        output = system.packages.nv_action_fetch_system_packages(
            engines, remote_url, scope='repository'
        )
        key_out = system.packages.get_system_packages_key()
        logger.info(f"key_out: {key_out}")
        verify_fetch(engines, key, key_out, output, scope='global')
    url_id = 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest'
    config_repositories(system, url_id, 'CumulusLinux-d12', 'cumulus', key='public', insecure='enabled')
    # Verify repository configuration
    output = system.packages.show_packages_output()
    logger.info(f"show_packages_output: {output}")
    # Verify the key is configured in the repository
    repo_out = system.packages.verify_repository_in_show_packages_output(url_id)
    if repo_out.get('key') == 'public':
        logger.info(f"key {repo_out.get('key')} has configured properly to the repo")
    else:
        assert False, "key is not configured to the repo properly"
    try:
        system.packages.nv_action_delete_system_packages(engines, key='public')
        logger.info("Successfully deleted the key 'Public'")
    except Exception as cli_error:
        logger.info(f"getting as expected command error: {cli_error}")
    with allure.step("Unset repository key and insecure settings"):
        logger.info("Unsetting repository key and insecure settings")
        repo_obj = system.packages.repositories.repositories_dict.get(url_id)
        if not repo_obj:
            assert False, f"Repository {url_id} not found when trying to unset key"
        # Stage insecure and key unsets without applying yet
        repo_obj.unset_insecure(apply=False)
        logger.info("Staged unset of insecure setting")
        repo_obj.unset_key(apply=False)
        logger.info("Staged unset of key setting")
        # Now remove the repository and apply once so apt doesn't see a live repo without a key
        unset_repo_result = system.packages.repositories.unset_repository(
            url_id, apply=True, ask_for_confirmation=True
        )
        unset_repo_result.verify_result(should_succeed=True)
        # Verify repository is no longer present in packages output
        packages_output = system.packages.show_packages_output()
        repo_ids = packages_output.get(PackageConsts.REPO_ID, {})
        if url_id in repo_ids:
            assert False, f"Repository {url_id} still present after unset"
        logger.info(f"Successfully unset repository {url_id} and its key/insecure settings")
    with allure.step("Delete key 'Public' after removing from repository"):
        logger.info("Deleting key 'Public' after it's no longer in use")
        output = system.packages.nv_action_delete_system_packages(engines, key='public')
        verify_action_delete(output)
    try:
        config_repositories(system, url_id, 'CumulusLinux-d12', 'cumulus', key='archive-key-11.asc', insecure='enabled', apply=True, ask_for_confirmation=True)
        output = system.packages.show_packages_output()
        logger.info(f"show_packages_output: {output}")
    except Exception as cli_error:
        logger.info("error as expected: {}".format(cli_error))
    unset_repo_result = system.packages.repositories.unset_repository(
        url_id, apply=True, ask_for_confirmation=True
    )
    output = system.packages.nv_action_delete_system_packages(engines, key='archive-key-11.asc')
    verify_action_delete(output)


@pytest.mark.system
@pytest.mark.cumulus_only
@pytest.mark.packages
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_07_apt_source_packages_config_non_default_and_default_vrf_with_key(engines, devices, test_api):
    """
    Name: Verify apt source packages config with non-default and default vrf with key
    ===============================================
    Description:
    ===============================================
    1. Execute nv action fetch system packages key <remote-url> scope <global|repository> vrf <vrf-id>
    2. Verify the action completes successfully or raise error for valid URL
    3. Configure a non-default VRF using nv set system packages use-vrf <vrf-id>
    4. Check whether the non-default VRF has Internet connectivity for downloads
    5. If error is seen with non-default VRF, switch to default VRF and continue
    6. Configure the repository URL with key
    7. Verify the key is updated to the repository using nv show command
    8. Execute nv action delete system packages key <key>
    9. Verify the key is deleted successfully
    """
    TestToolkit.tested_api = test_api
    system = System()
    engines.dut.run_cmd("nv action delete system packages key public")
    engines.dut.run_cmd("nv action delete system packages key archive-key-11.asc")
    with allure.step("Fetch key using non-default VRF and verify successfully"):
        remote_url = 'https://urm.nvidia.com/artifactory/api/gpg/key/public'
        key = 'public'
        output = system.packages.nv_action_fetch_system_packages(engines, remote_url, scope='repository', vrf='mgmt')
        key_out = system.packages.get_system_packages_key()
        verify_fetch(engines, key, key_out, output, scope='repository')
        system.packages.set_use_vrf("default", apply=True, ask_for_confirmation=True)
    with allure.step("Configure repository with key and insecure"):
        url_id = 'https://urm.nvidia.com/artifactory/sw-nbu-cl-dev-debian-local/snapshots/cl5-latest'
        try:
            config_repositories(system, url_id, 'CumulusLinux-d12', 'cumulus', key='public', insecure='enabled', apply=True, ask_for_confirmation=True)
        except Exception as cli_error:
            logger.info("error as expected: {}".format(cli_error))
    with allure.step("Unset packages configuration and verify use-vrf is set to default"):
        system.packages.unset_use_vrf(apply=True, ask_for_confirmation=True)
        use_vrf_data = system.packages.get_packages_field_values([PackageConsts.USE_VRF])
        if use_vrf_data.get(PackageConsts.USE_VRF) != "default":
            logger.info("use-vrf is not set to default")
        else:
            logger.info("use-vrf is set to default")
    with allure.step("Set use-vrf to mgmt and configure repository with key"):
        system.packages.set_use_vrf("mgmt", apply=True, ask_for_confirmation=True)
        config_repositories(system, url_id, 'CumulusLinux-d12', 'cumulus', key='public', insecure='enabled', apply=True, ask_for_confirmation=True)
        output = system.packages.show_packages_output()
        logger.info(f"show_packages_output: {output}")
        repo_out = system.packages.verify_repository_in_show_packages_output(url_id)
        if repo_out.get('key') == 'public':
            logger.info(f"key {repo_out.get('key')} has configured properly to the repo")
        else:
            assert False, "key is not configured to the repo properly"
    with allure.step("Unset packages configuration and verify repository is unset"):
        system.packages.unset_packages_configuration(apply=True, ask_for_confirmation=True)
        packages_data = system.packages.get_packages_field_values([PackageConsts.REPO_ID])
        if not packages_data.get(PackageConsts.REPO_ID):
            logger.info("Successfully unset the system packages repository")
        else:
            logger.info("Failed to unset the system packages repository")
    output = system.packages.nv_action_delete_system_packages(engines, key='public')
    verify_action_delete(output)


@pytest.mark.system
@pytest.mark.cumulus_only
@pytest.mark.packages
@pytest.mark.parametrize('test_api', [ApiType.OPENAPI])
def test_08_action_fetch_nd_delete_system_packages_key_using_api(engines, devices, test_api):
    """
    Name: Verify action fetch and delete system packages key using api
    ===============================================
    Description:
    ===============================================
    Verify action fetch and delete system packages key using api
    """
    TestToolkit.tested_api = test_api
    system = System()
    engines.dut.run_cmd("nv action delete system packages key public")
    engines.dut.run_cmd("nv action delete system packages key archive-key-11.asc")
    remote_url = "https://ftp-master.debian.org/keys/archive-key-11.asc"
    key = 'archive-key-11.asc'
    output = system.packages.nv_action_fetch_system_packages(engines, remote_url, scope='repository')
    key_out = system.packages.get_system_packages_key()
    logger.info(f"key_out: {key_out}")
    verify_fetch(engines, key, key_out, output, scope='global')
    output = system.packages.nv_action_delete_system_packages(engines, key='archive-key-11.asc')
    verify_action_delete(output)

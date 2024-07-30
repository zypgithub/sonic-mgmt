import random
import pytest

from ngts.nvos_constants.constants_nvos import ApiType, ClusterConsts, OutputFormat, ActionConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='session', autouse=True)
def clear_cluster_package_files():
    fae = Fae(None)
    nmx_package = fae.cluster.package
    with allure.step('delete fetched nmx package files'):
        files = nmx_package.files.get_files()
        nmx_package.files.delete_files(files_to_delete=files)


@pytest.fixture()
def enable_disable_cluster():
    cluster = Cluster()
    ClusterTools.start_cluster(cluster, OutputFormat.json)
    yield
    ClusterTools.stop_cluster(cluster, OutputFormat.json)


@pytest.fixture()
def install_default_if_needed(devices):
    cluster = Cluster()
    fae = Fae()
    output = cluster.apps.show()
    if not output:
        apps = ClusterConsts.INITIAL_EXPECTED_APPS
        for app in apps:
            default_path = devices.dut.nmx_cluster_apps_versions.default_path[app]
            default_version = devices.dut.nmx_cluster_apps_versions.default_version_names[app]
            filename = fetch_and_verify_package(fae, app, default_path)
            uninstall_install_and_verify_package(fae, app, filename, default_version)


@pytest.mark.fae
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_nmx_package_good_flow(devices, engines, test_api, enable_disable_cluster, install_default_if_needed):
    """
    Test the good flow of NMX package management.

    Steps:
    1. Set the tested API.
    2. Initialize the FAE and cluster objects.
    3. Retrieve the initial expected apps.
    4. For each app:
        a. Retrieve the default and new version names and paths.
        b. Verify the default version of the app.
        c. Fetch and verify the package.
        d. Uninstall the current package and install the new package.
    5. Verify the start and stop operations of the application.
    6. Delete the package file.
    7. Cleanup:
       a. Revert all applications to their default versions.
    """
    TestToolkit.tested_api = test_api
    fae = Fae(None)
    cluster = Cluster()
    apps = ClusterConsts.INITIAL_EXPECTED_APPS

    try:
        for app in apps:
            default_version = devices.dut.nmx_cluster_apps_versions.default_version_names[app]
            new_version = devices.dut.nmx_cluster_apps_versions.new_version_names[app]
            new_path = devices.dut.nmx_cluster_apps_versions.new_path[app]

            # Will be added in future
            # ClusterTools.verify_app_version(fae.cluster, app, default_version)
            test_nmx_package_flow(fae, cluster, app, new_path, new_version)

    finally:
        with allure.step(f'cleanup - returning to default versions'):
            for app in apps:
                default_path = devices.dut.nmx_cluster_apps_versions.default_path[app]
                default_version = devices.dut.nmx_cluster_apps_versions.default_version_names[app]

                test_nmx_package_flow(fae, cluster, app, default_path, default_version)


def fetch_and_verify_package(fae, app, path):
    with allure.step(f'try to fetch nmx cluster package of {app}'):
        fae.cluster.package.action_fetch(path=path).verify_result()

    with allure.step("Validate file was fetched"):
        filename = path.split('/')[-1]
        fae.cluster.package.files.verify_show_files_output([filename])

    return filename


def uninstall_install_and_verify_package(fae, app, filename, expected_version):
    with allure.step(f'try to uninstall nmx package app {app}'):
        fae.cluster.apps.apps_name[app].action_uninstall()

    with allure.step(f'try to install nmx package file {filename}'):
        fae.cluster.package.files.file_name[filename].action_file_install(force=False).verify_result()

    with allure.step(f'verify installation'):
        ClusterTools.verify_app_version(fae.cluster, app, expected_version)


def verify_start_stop(cluster, app):
    with allure.step(f'try to start stop {app}'):
        cluster.apps.apps_name[app].action_start_cluster_apps().verify_result()
        cluster.apps.apps_name[app].action_stop_cluster_apps().verify_result()


def delete_package_file(fae, filename):
    with allure.step(f'try to delete fetched file {filename}'):
        fae.cluster.package.files.file_name[filename].action_delete()
        fae.cluster.package.files.verify_show_files_output()


def test_nmx_package_flow(fae, cluster, app, path, new_version):
    """
    Handle the package flow for a given application.

    Steps:
    1. Fetch and verify the package.
    2. Uninstall the current package and install the new package.
    3. Verify the start and stop operations of the application.
    4. Delete the package file.
    """
    filename = fetch_and_verify_package(fae, app, path)
    uninstall_install_and_verify_package(fae, app, filename, new_version)
    verify_start_stop(cluster, app)
    delete_package_file(fae, filename)


@pytest.mark.fae
@pytest.mark.nmx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_nmx_package_bad_flow(devices, engines, test_name, test_api):
    """
    Test the bad flow of NMX package management.

    Steps:
    1. Set the tested API.
    2. Initialize the FAE and NMX package objects.
    3. Randomly select an application to test.
    4. Attempt to uninstall a non-existing application (expect failure).
    5. Fetch the package for the selected application.
    6. Attempt to install the package without uninstalling the previous version (expect failure).
    7. Verify that the old version is still installed.
    8. Delete the fetched package file and verify its deletion.
    9. Attempt to delete the already deleted file (expect failure).
    """
    TestToolkit.tested_api = test_api
    fae = Fae(None)
    nmx_package = fae.cluster.package
    app_to_test = random.choice(ClusterConsts.INITIAL_EXPECTED_APPS)
    default_version = devices.dut.nmx_cluster_apps_versions.default_version_names[app_to_test]
    new_path = devices.dut.nmx_cluster_apps_versions.default_path[app_to_test]
    filename = new_path.split('/')[-1]
    non_exist_app = RandomizationTool.get_random_string(8)

    with allure.step(f'try to uninstall non existing app {non_exist_app}'):
        fae.cluster.apps.action(action=ActionConsts.UNINSTALL, param_name=ClusterConsts.APP_NAME, param_value=non_exist_app).verify_result(False)

    with allure.step('try to fetch cluster package'):
        nmx_package.action_fetch(path=new_path).verify_result()

    with allure.step(f'try to install nmx package without uninstall {filename} - should fail'):
        fae.cluster.package.files.file_name[filename].action_file_install(force=False).verify_result(False)

    with allure.step(f'verify old version'):
        ClusterTools.verify_app_version(fae.cluster, app_to_test, default_version)

    with allure.step(f'try to delete fetched file {filename}'):
        nmx_package.files.file_name[filename].action_delete()
        nmx_package.files.verify_show_files_output()

    with allure.step(f'try to delete already deleted fetched file {filename}'):
        nmx_package.files.file_name[filename].action_delete(should_succeed=False)
        nmx_package.files.verify_show_files_output()

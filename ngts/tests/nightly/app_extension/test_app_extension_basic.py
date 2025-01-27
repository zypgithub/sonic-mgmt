import allure
import logging
import pytest
import json

from ngts.tests.nightly.app_extension.app_extension_helper import verify_app_repository_list_format, \
    verify_add_app_to_repo, extract_version_info, get_non_semver_version_info, \
    verify_changelog_same_to_manifest, APP_INFO, verify_app_container_up_and_repo_status_installed, app_cleanup

logger = logging.getLogger()


@pytest.mark.app_ext
@allure.title('Test repo management')
def test_repo_management(engines, cli_objects):
    """
    This test case will check the functionality of package repository management
    Firstly, verify sonic-package-manager list, output is as follows:
    Name            Repository                                Description                   Version    Status
    --------------  ----------------------------------------  ----------------------------  ---------  ---------
    database        docker-database                           SONiC database package        1.0.0      Built-In
    dhcp-relay      docker-dhcp-relay                         N/A                           1.0.0      Installed
    fpm-frr         docker-fpm-frr                            SONiC fpm-frr package         1.0.0      Built-In
    lldp            docker-lldp                               SONiC lldp package            1.0.0      Built-In
    Secondly, Add a test repository to the package database with sonic-package-manager repository add <NAME>
    <REPOSITORY>
    and then verify that the new app appears in the package list:
    Name            Repository                                Description                   Version    Status
    --------------  ----------------------------------------  ----------------------------  ---------  ---------
    p4-sampling     nbu-harbor.gtm.nvidia.com/sonic-p4/p4-sampling  N/A                           N/A        Not Installed
    Thirdly, Remove a test repository from the package database with sonic-package-manager repository remove <NAME>
     <REPOSITORY>,
    and verify that the app was removed from the package list..
    :param engines: ssh engine object
    """
    dut_engine = engines.dut
    app_name = APP_INFO["name"]
    app_repository_name = APP_INFO["repository"]

    try:

        with allure.step('Show app package list'):
            app_package_repo_list = cli_objects.dut.app_ext.show_app_list()
            verify_app_repository_list_format(app_package_repo_list)

        with allure.step('Add a test repository to the package database'):
            cli_objects.dut.app_ext.add_repository(app_name, app_repository_name)
            verify_add_app_to_repo(cli_objects.dut, app_name, app_repository_name)

        with allure.step('Remove a test repository from the package database'):
            cli_objects.dut.app_ext.remove_repository(app_name)
            assert app_name not in cli_objects.dut.app_ext.parse_app_package_list_dict(), "{} is not removed ".format(app_name)
    except Exception as err:
        raise AssertionError(err)

    finally:
        # clear app package from repository
        app_cleanup(dut_engine, cli_objects.dut, app_name)


@pytest.mark.app_ext
@allure.title('test show package version')
def test_show_package_version(add_app_into_repo, cli_objects):
    """
    This test case is to show package version and check output format as follows:
    1. spm show package versions cpu-report
    Example output:
        • 1.0.0
        • 2.0.0
    2. spm show package versions cpu-report --all
    Example output:
        • 1.0.0
        • 2.0.0
        • 1.2
        • 1.2.3-0123
    3. spm show package versions cpu-report --plain
    Example output:
        1.0.0
        2.0.0

    """
    dut_engine, app_name, _ = add_app_into_repo
    try:
        with allure.step("Show package versions {} ".format(app_name)):
            output_version = cli_objects.dut.app_ext.show_app_version(app_name)
            is_plain_output, new_versions = extract_version_info(output_version)
            assert not is_plain_output, "Version data not include dot •,  raw version is {}".format(output_version)
            non_semver_versions = get_non_semver_version_info(new_versions)
            assert not non_semver_versions, "Version data include non-semver version:{}".format(non_semver_versions)

        with allure.step("Show package versions {} --all ".format(app_name)):
            output_version = cli_objects.dut.app_ext.show_app_version(app_name, "all")
            is_plain_output, new_versions = extract_version_info(output_version)
            assert not is_plain_output, "Version data not include dot • raw version is {}".format(output_version)
            non_semver_versions = get_non_semver_version_info(new_versions)
            assert non_semver_versions, "Version data include non-semver version {}".format(non_semver_versions)

        with allure.step("Show package versions {} --plain ".format(app_name)):
            output_version = cli_objects.dut.app_ext.show_app_version(app_name, "plain")
            is_plain_output, new_versions = extract_version_info(output_version)
            assert is_plain_output, "Version data include dot •, raw version is {}".format(output_version)
            non_semver_versions = get_non_semver_version_info(new_versions)
            assert not non_semver_versions, "Version data include non-semver version:{}".format(non_semver_versions)

    except Exception as err:
        raise AssertionError(err)


@pytest.mark.app_ext
@allure.title('test show package manifest')
def test_show_package_manifest(add_app_into_repo, cli_objects):
    """
    This test is to show package's manifest and check it must include follow info: version, package, service
    Example:
        {
            "version": "1.0.0",
            "package": {
                "version": "{{ version }}",
                "name": "cpu-report",
                ...
            },
            "service": {
                "name": "{{ container_name }}"
            },
            ...
        }
    """
    dut_engine, app_name, version = add_app_into_repo
    try:
        with allure.step("Show app manifest {}={} ".format(app_name, version)):
            output = cli_objects.dut.app_ext.show_app_manifest(app_name, version)
            manifest_json = json.loads(output)
            check_manifest_key_list = ["version", "package", "service"]
            for key in check_manifest_key_list:
                assert key in manifest_json, "Mandatory key:{} is not found in manifest :{}".format(key, manifest_json)
    except Exception as err:
        raise AssertionError(err)


@pytest.mark.app_ext
@allure.title('test show package changelog')
def test_show_package_changelog(add_app_into_repo, cli_objects):
    """
    This test is to test show package changelog, and changelog should match that in manifest
    Example:
        manifest:
                {
                 ...
                "package": {
                    ...
                    "changelog": {
                        "1.0.0": {
                            "changes": [
                                "Initial release"
                            ],
                            "author": "Stepan Blyshchak",
                            "email": "stepanb@nvidia.com",
                            "date": "Mon, 25 May 2020 12:24:30 +0300"
                        },
                        "1.1.0": {
                            "changes": [
                                "Added functionality",
                                "Bug fixes"
                            ],
                            "author": "Stepan Blyshchak",
                            "email": "stepanb@nvidia.com",
                            "date": "Fri, 23 Oct 2020 12:26:08 +0300"
                        }
                    },
                    ...
                },
                ...
            }

        Changelog:
            1.0.0:

            • Initial release

                Stepan Blyshchak (stepanb@nvidia.com) Mon, 25 May 2020 12:24:30 +0300

            1.1.0:

            • Added functionality
            • Bug fixes

                Stepan Blyshchak (stepanb@nvidia.com) Fri, 23 Oct 2020 12:26:08 +0300

    """
    dut_engine, app_name, version = add_app_into_repo
    try:
        with allure.step("Show package changelog {}={} ".format(app_name, version)):
            output_changelog = cli_objects.dut.app_ext.show_app_changelog(app_name, version)
            output_manifest = cli_objects.dut.app_ext.show_app_manifest(app_name, version)
            manifest_json = json.loads(output_manifest)
            verify_changelog_same_to_manifest(output_changelog, manifest_json)

    except Exception as err:
        raise AssertionError(err)


@pytest.mark.app_ext
@allure.title('test app techsupport integration ')
def test_app_techsupport_integration(add_app_into_repo, cli_objects):
    """
    This test is to test techsupport integration in app extension
    1. The installed app's manifest should include the debug-dump info as follows:
        {
            "package": {
                "debug-dump": "echo DUMP"
            }
        }
    2. After generating techsupport, check that in the generated dump there is a directory:dump/<PACKAGE_NAME>.gz
    """
    dut_engine, app_name, _ = add_app_into_repo
    verison = APP_INFO["debug-dump"]["version"]
    try:
        with allure.step("Install app with debug-dump in manifest"):
            cli_objects.dut.app_ext.install_app(app_name, verison)
            cli_objects.dut.app_ext.enable_app(app_name)
        with allure.step("Check app version and status"):
            verify_app_container_up_and_repo_status_installed(cli_objects.dut, app_name, verison)
        with allure.step("Show tech support and verify there is a dump/{}.gz".format(app_name)):
            dump_file = cli_objects.dut.general.generate_techsupport()
            res = dut_engine.run_cmd("sudo tar -tf {} | grep {}.gz".format(dump_file, app_name))
            assert res, "Not found dump/{}.gz ".format(app_name)
    except Exception as err:
        raise AssertionError(err)

import re
import allure
import logging
import pytest

from ngts.tests.nightly.app_extension.app_extension_helper import \
    verify_app_container_up_and_repo_status_installed, uninstall_app_with_force_and_remove_app_from_repo, \
    verify_app_container_status_none, gen_app_tarball, APP_INFO, get_app_repository

logger = logging.getLogger()


@pytest.mark.app_ext
@pytest.mark.parametrize(
    "install_cmd_postfix, version, is_force_uninstalled",
    [
        (APP_INFO["name"], None, True),
        ("{}=={}".format(APP_INFO["name"], APP_INFO["normal2"]["version"]), APP_INFO["normal2"]["version"], False),
        ("{}@{}".format(APP_INFO["name"], APP_INFO["normal1"]["digest"]), APP_INFO["normal1"]["version"], False),
        ("{}=={} --force".format(APP_INFO["name"], APP_INFO["normal2"]["version"]), APP_INFO["normal2"]["version"], True),
    ],
)
@allure.title('App package install and uninstall')
def test_app_install_uninstall(engines, cli_objects, add_app_into_repo, install_cmd_postfix, version,
                               is_force_uninstalled):
    """
    This test case is test app install and uninstall, it include following test cases:
    1. install with default version, and uninstall with force
    2. install with specified version, and uninstall without force
    3. install with digest, and uninstall with option force
    4. install with specified version with force option
    After install, need check version, install status by spm list, and container status by docker ps
    After uninstall, need check container is removed and package is removed

    """

    logger.info("Install app with {}, version={}".format(install_cmd_postfix, version))
    dut_engine = engines.dut
    app_name = APP_INFO["name"]

    try:
        with allure.step("Install app with {}, version={}".format(install_cmd_postfix, version)):
            dut_engine.run_cmd("sudo sonic-package-manager install -y {}".format(install_cmd_postfix), validate=True)
            verify_app_container_status_none(cli_objects.dut, app_name)
            logger.info("Enable feature of {}".format(app_name))
            cli_objects.dut.app_ext.enable_app(app_name)
            verify_app_container_up_and_repo_status_installed(cli_objects.dut, app_name, version)

        with allure.step("Uninstall app"):
            logger.info("Uninstall app with force  is {} ".format(is_force_uninstalled))
            uninstall_app_with_force_and_remove_app_from_repo(cli_objects.dut, app_name, is_force_uninstalled)

    except Exception as err:
        raise AssertionError(err)


@pytest.mark.app_ext
@pytest.mark.parametrize(
    "app_name, version, abnormal_type",
    [
        (APP_INFO["name"], APP_INFO["invalid_manifest"]["version"], "invalid_manifest"),
        (APP_INFO["name"], APP_INFO["missing_dependency"]["version"], "missing_dependency"),
        (APP_INFO["name"], APP_INFO["package_conflict"]["version"], "package_conflict"),
    ],
)
@allure.title('Install app with abnormal package')
def test_app_install_with_abnormal_package(engines, add_app_into_repo, app_name, version, abnormal_type):
    """
    This test case is to install some abnormal package.
    It include 3 sub test cases
    1. install app with invalid manifest
    2. install app with missing dependency
    3. install app with package conflict
    And check corresponding Failed message

    """
    expected_error_msgs = {
        "invalid_manifest": "Failed to install {}=={}: \"name\" is a required field but it is missing".format(
            APP_INFO["name"], APP_INFO["invalid_manifest"]["version"]),
        "missing_dependency": "Failed to install {}.*{}.*missing-dependency.*it is not installed".format(
            APP_INFO["name"], APP_INFO["missing_dependency"]["version"], APP_INFO["name"]),
        "package_conflict": "Failed to install {}=={}: Package {} conflicts with syncd>0.0.0 but version".format(
            APP_INFO["name"], APP_INFO["package_conflict"]["version"], APP_INFO["name"])
    }
    dut_engine = engines.dut
    logger.info("Invalid manifest: install {} with version {}".format(app_name, version))
    try:
        with allure.step("Install app {} with abnormal package, version={}".format(app_name, version)):
            output = dut_engine.run_cmd("sudo sonic-package-manager install -y {}=={}".format(app_name, version))
            expected_error_msg = expected_error_msgs[abnormal_type]
            logger.info("Excepted message is {}, actual message is {}".format(expected_error_msg, output))
            msg_pattern = re.compile(expected_error_msg)
            assert msg_pattern.match(output), "install app with abnormal package fail"

    except Exception as err:
        raise AssertionError(err)


@pytest.mark.app_ext
@allure.title('Force installing app and skip dependency check')
def test_app_install_with_force_skip_dependency_check(engines, cli_objects, add_app_into_repo):
    """
    This test case is to test force install package with missing dependency
    1. check corresponding Failed message
    2. check container status by docker ps and package install status by spm list

    """
    dut_engine = engines.dut
    app_name = APP_INFO["name"]
    version = APP_INFO["missing_dependency"]["version"]

    try:
        with allure.step("Install app with {}, version={}".format(app_name, version)):
            output = dut_engine.run_cmd("sudo sonic-package-manager install -y {}={} --force".format(app_name, version))
            expected_msg = ".*ignoring error Package {} requires missing-dependency.*but it is not installed.*".format(app_name)
            msg_pattern = re.compile(expected_msg)
            assert msg_pattern.match(output), "Force install app failed"
            verify_app_container_status_none(cli_objects.dut, app_name)
            logger.info("Enable feature of {}".format(app_name))
            cli_objects.dut.app_ext.enable_app(app_name)
            verify_app_container_up_and_repo_status_installed(cli_objects.dut, app_name, version)

        with allure.step("Force uninstall app"):
            uninstall_app_with_force_and_remove_app_from_repo(cli_objects.dut, app_name, False)

    except Exception as err:
        raise AssertionError(err)


@pytest.mark.app_ext
@allure.title('Install app from tarball')
def test_app_install_from_tarball(engines, cli_objects, add_app_into_repo, is_air):
    """
    This test is to install app from tarball
    Firstly prepare a app tarball by docker pull and docker save -o
    Secondly install app from tarball
    And check the repo install status by spm list and container status by docker ps
    """
    dut_engine = engines.dut
    app_name = APP_INFO["name"]
    version = APP_INFO["normal1"]["version"]
    app_repo = get_app_repository(is_air)

    try:
        with allure.step("Install app {}:{} from tarball".format(app_name, version)):
            tarball_name = gen_app_tarball(dut_engine, app_repo, app_name, version)
            cli_objects.dut.app_ext.install_app_from_tarball(tarball_name)
            verify_app_container_status_none(cli_objects.dut, app_name)
            logger.info("Enable feature of {}".format(app_name))
            cli_objects.dut.app_ext.enable_app(app_name)
            verify_app_container_up_and_repo_status_installed(cli_objects.dut, app_name, version)

        with allure.step("Uninstall app"):
            uninstall_app_with_force_and_remove_app_from_repo(cli_objects.dut, app_name, False)

    except Exception as err:
        raise AssertionError(err)

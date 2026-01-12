import re
import logging
import allure
import semantic_version

from ngts.cli_util.verify_cli_show_cmd import verify_show_cmd
from dateutil.parser import parse as time_parse
from ngts.constants.constants import AppExtensionInstallationConstants, MarsConstants
from retry.api import retry_call


logger = logging.getLogger()
APP_INFO = {
    "name": "cpu-report",
    # Repository path without registry prefix; use get_app_repository() to get the
    # full repository including the relevant registry (lab vs AIR).
    "repository": "sonic/cpu-report",
    "normal1": {"digest": "sha256:59801bed4ebe5701f6cbac232281d0d7e990c2274a70e0b1d8818a4710cbf1bf ",
                "version": "1.0.0"},
    "normal2": {"digest": "sha256:96a87a62ca962fbf92a33c25e6bb2768aa6f113203845da64603d13872eb642f",
                "version": "2.0.0"},
    "invalid_manifest": {"digest": "sha256:f26bb0557ee72b5f947fbb5d74c2256fffde12b01ee39f213604f8e3d9109591",
                         "version": "3.0.0"},
    "missing_dependency": {"digest": "sha256:c72fb9c800bb80479873de27f17416a8a419dbc34f4130f24fa10c524f07b4ae",
                           "version": "4.0.0"},
    "package_conflict": {"digest": "sha256:c72fb9c800bb80479873de27f17416a8a419dbc34f4130f24fa10c524f07b4ae",
                         "version": "5.0.0"},
    "debug-dump": {"digest": " sha256:5ce08cd9f4d9158882d9f471042a28ff62037a41e2a0a5510e8d773557fee042",
                   "version": "6.0.0"},
    "delay_true": {"digest": " sha256:5ce08cd9f4d9158882d9f471042a28ff62037a41e2a0a5510e8d773557fee042",
                   "version": "7.0.0"},
    "shut_down": {"digest": " sha256:912eefe5b0b3566051115e141efe007dc68dbdb76a9772e0fe7768e1cc38ae3a",
                  "version": "10.0.0"},
}


def get_app_repository(is_air):
    """
    Return full repository (including registry) for APP_INFO["name"].

    :param is_air: True for Nvidia AIR setups, False for lab/regular setups.
    """
    registry = MarsConstants.AIR_DOCKER_REGISTRY if is_air else MarsConstants.DOCKER_REGISTRY
    return "{}/{}".format(registry, APP_INFO["repository"])


def verify_app_repository_list_format(output_cmd):
    """
    Verify format from "sonic-package-manager list" output
    :param output_cmd: output from cmd
    :return: None if output is like follow format, raise error in case of unexpected result:
        Name            Repository                                Description                   Version    Status
        --------------  ----------------------------------------  ----------------------------  ---------  ---------
        database        docker-database                           SONiC database package        1.0.0      Built-In
        dhcp-relay      docker-dhcp-relay                         N/A                           1.0.0      Installed

    """
    excepted_out_list = [[r"Name\s+Repository\s+Description\s+Version\s+Status", True],
                         [r"--+\s{2,}--+\s{2,}--+\s{2,}--+\s{2,}--+", True]]
    verify_show_cmd(output_cmd, excepted_out_list)


def verify_add_app_to_repo(cli_obj, app_name, repo_name, desc="N/A", version="N/A", status="Not Installed"):
    """
    Verify if app is added into repo From "sonic-package-manager list" output
    :param cli_obj: cli_obj object
    :param app_name: app package name
    :param repo_name: app package repository
    :param desc: app package description
    :param version: app package version
    :param status: indicate if the app package is installed or not
    :Return None, or raise exception  if app info not match all

    """
    app_package_repo_dict = cli_obj.app_ext.parse_app_package_list_dict()
    if app_name in app_package_repo_dict:
        app_info = app_package_repo_dict[app_name]
        assert all([repo_name == app_info["Repository"],
                    desc == app_info["Description"],
                    version == app_info["Version"],
                    status == app_info["Status"]]), \
            "{} install fail..., app info is {}".format(app_name, app_info)
    else:
        assert False, "{} is not in the package list:{}".format(app_name, app_package_repo_dict)


def retry_verify_app_container_up(cli_obj, app_name):
    """
    Verify with retries that docker is up
    :param cli_obj: cli_obj object
    :param app_name: app package name
    :Return None, or raise exception  if app info not match all
    """
    def verify_app_container_up(cli_obj, app_name):
        status = cli_obj.general.get_container_status(app_name)
        assert status, "{} container is not up, container status is None".format(app_name)
        assert "Up" in status, "expected status is Up, actual is {}".format(status)
    retry_call(verify_app_container_up, fargs=[cli_obj, app_name],
               tries=36, delay=10, logger=logger)


def verify_app_container_up_and_repo_status_installed(cli_obj, app_name, version):
    """
    Verify app container is up and status in repo is installed
    :param cli_obj: cli_obj object
    :param app_name: app package name
    :param version: app package version
    :Return None, or raise exception  if app info not match all

    """
    app_package_repo_dict = cli_obj.app_ext.parse_app_package_list_dict()
    if app_name in app_package_repo_dict:
        app_info = app_package_repo_dict[app_name]
        if version:
            assert version == app_info["Version"], "Expected Version is {}, Actual Version is {}".format(version, app_info["Version"])
        assert app_info["Status"] == "Installed", "Expected status is Installed, Actual status is {}".format(
            app_info["Status"])
        retry_verify_app_container_up(cli_obj, app_name)
    else:
        assert False, "No app package info: {}".format(app_package_repo_dict)


def verify_app_container_down_and_repo_status_na(cli_obj, app_name):
    """
    Verify app container is up and status in repo is installed
    :param cli_obj: cli_obj object
    :param app_name: app package name
    :Return None, or raise exception  if app info not match all

    """
    status = cli_obj.general.get_container_status(app_name)
    assert not status, "Container still is not uninstalled,  Status is {}, ".format(status)
    app_package_repo_dict = cli_obj.app_ext.parse_app_package_list_dict()
    if app_name in app_package_repo_dict:
        assert False, "app package is not removed: {}".format(app_package_repo_dict)


def uninstall_app_with_force_and_remove_app_from_repo(cli_obj, app_name, is_force=False):
    """
    Uninstall app with force or normally, and remove app from repo
    :param cli_obj: cli_obj object
    :param app_name: app package name
    :param is_force：Bool, True uninstall with force, or without force
    """
    if is_force:
        cli_obj.app_ext.uninstall_app(app_name, True)
    else:
        cli_obj.app_ext.disable_app(app_name)
        cli_obj.app_ext.uninstall_app(app_name)
    cli_obj.app_ext.remove_repository(app_name)
    verify_app_container_down_and_repo_status_na(cli_obj, app_name)


def gen_app_tarball(dut_engine, repo_name, app_name, version):
    """
    generate app tarball
    :param dut_engine: ssh engine object
    :param repo_name: repo package name
    :param app_name: app package name
    :param version: app version
    :Return tarball name or raise exception
    """
    logger.info("gen {}.tar from {}:{}".format(app_name, repo_name, version))
    tarball_name = "{}.tar".format(app_name)

    with allure.step("gen app tarball".format(app_name, version)):
        dut_engine.run_cmd("sudo docker pull {}:{}".format(repo_name, version), validate=True)
        dut_engine.run_cmd("sudo docker save {}:{} -o {} ".format(repo_name, version, tarball_name), validate=True)
        dut_engine.run_cmd("sudo docker rmi {}:{}".format(repo_name, version), validate=True)

    return tarball_name


def verify_app_container_status_none(cli_obj, app_name):
    """
    Verify app container is None
    :param cli_obj: cli_obj object
    :param app_name: app package name
    :Return None, or raise exception  if app info not match all

    """
    status = cli_obj.general.get_container_status(app_name)
    assert not status, "Excepted container status is None, actual container status is {}".format(status)


def extract_version_info(raw_version_data: str) -> (bool, list):
    """
    Extract version info, and transform them to version list
    :param raw_version_data: String, raw version data
    Example:
    Raw data: • 1.0.0
              • 2.0.0
              or
              1.0.0
              2.0.0
    New data:  [1.0.0, 2.0.0]
    Return output data is plain or not, and version list without dot

    """
    versions = raw_version_data.strip().split("\n")
    dot_reg = re.compile(r".*•\s*(?P<version>.*)")
    new_versions = []
    version_dots = []

    for version in versions:
        match_res = dot_reg.match(version)
        if match_res:
            new_versions.append(match_res.group("version").strip())
            version_dots.append(True)
        else:
            new_versions.append(version.strip())
    if len(new_versions) == len(version_dots) and len(new_versions) > 0:
        is_plain_output = False
    else:
        is_plain_output = True
    return is_plain_output, new_versions


def get_non_semver_version_info(versions: list) -> list:
    """
    Calculate SemVer(Semantic Versioning) version number and Non-SemVer version number
    :param versions: version data list
    Return non_semver_version_list
    """
    semver_version_num = 0
    non_semver_version_num = 0
    non_semver_version_list = []

    for ver in versions:
        if semantic_version.validate(ver):
            semver_version_num += 1
            logger.info("Semver version :{}, total number of semver version :{}".format(ver, semver_version_num))
        else:
            non_semver_version_num += 1
            non_semver_version_list.append(ver)
            logger.info(
                "Non-semver version :{}, total number of non-semver version :{}".format(ver, non_semver_version_num))

    return non_semver_version_list


def get_changelog_from_manifest(manifest: str) -> str:
    """
    Get_changelog_from_manifest
    :param manifest: app manifest
    :Return changelog string
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
    changelog = manifest["package"]["changelog"]
    changelog_str = ""
    first_entity = True
    for key, var in changelog.items():
        if not first_entity:
            changelog_str += "\n"
        first_entity = False
        changelog_str += key + ":\n\n"
        changelog_entity = changelog[key]
        if "changes" in changelog_entity:
            for v in changelog_entity["changes"]:
                changelog_str += "    • {}\n".format(v)
        changelog_entity.pop("changes")
        changelog_str += "\n"
        author_email_data_str = ''
        first_key = True
        for k, v in changelog_entity.items():
            if not first_key:
                space = " "
            else:
                space = ""

            if k == "email":
                author_email_data_str += "{}({})".format(space, v)
            else:
                author_email_data_str += "{}{}".format(space, v)
            first_key = False
        changelog_str += "        {}\n".format(author_email_data_str)
    logger.info("Changelog extracted from manifest : {}".format(changelog_str))
    return changelog_str


def verify_changelog_same_to_manifest(changelog_str: str, manifest_json: str) -> None:
    """
    Verify changelog content same to that in manifest
    :param changelog_str: changelog string
    :param manifest_json:  manifest
    """
    changelog_str_from_manifest = get_changelog_from_manifest(manifest_json)
    changelog_str_list = changelog_str.strip().split("\n")
    changelog_str_from_manifest_list = changelog_str_from_manifest.split("\n")
    assert len(changelog_str_list) != len(changelog_str_from_manifest_list), \
        "Changelog :{} not match that in manifest:{}".format(changelog_str_list, changelog_str_from_manifest_list)
    for i in range(0, len(changelog_str_list)):
        assert changelog_str_from_manifest_list[i] in changelog_str_list[i], \
            "Changelog line of {} is not matched that of manifest".format(i)


def verify_app_container_start_delay(dut_engine, app_name, delay_time):
    """
    Verify app container delay delay_time (currently default is 180s) to start

    """
    get_app_uptime_cmd = f'date ' \
        f'--date=`docker inspect --format="{{{{.State.StartedAt}}}}" {app_name}` +"%Y-%m-%d %H:%M:%S"'
    up_time_kernel = time_parse(dut_engine.run_cmd('uptime -s'))
    up_time_app = time_parse(dut_engine.run_cmd(get_app_uptime_cmd))

    if up_time_app > up_time_kernel:
        time_diff = (up_time_app - up_time_kernel).seconds
    else:
        time_diff = 0

    assert time_diff > delay_time, "Expect app delay {} seconds to start, actually delay {} to start ".format(
        delay_time, time_diff)


def app_cleanup(dut_engine, cli_obj, app_name):
    """
    Uninstall app and remove from repo
    :param dut_engine: ssh engines
    :param cli_obj: cli_obj object
    :param app_name: app extension name

    """
    # uninstall app with force
    if dut_engine.run_cmd("docker image list | grep {}".format(app_name)):
        cli_obj.app_ext.disable_app(app_name)
        cli_obj.app_ext.uninstall_app(app_name)
    # remove app from repo
    if app_name in cli_obj.app_ext.parse_app_package_list_dict():
        cli_obj.app_ext.remove_repository(app_name)


def get_installed_mellanox_extensions(cli_obj):
    """
    Returns list of mellanox application extensions, installed to image
    :param cli_obj: cli_obj object
    :return: list of app extension names
    """
    app_package_repo_dict = cli_obj.app_ext.parse_app_package_list_dict()
    return [app_name for app_name in app_package_repo_dict
            if app_name in AppExtensionInstallationConstants.APPLICATION_LIST]

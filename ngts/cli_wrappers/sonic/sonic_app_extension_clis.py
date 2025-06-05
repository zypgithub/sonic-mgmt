import logging

from ngts.cli_util.cli_parsers import generic_sonic_output_parser
from infra.tools.redmine.redmine_api import is_redmine_issue_active
import time


logger = logging.getLogger()


class SonicAppExtensionCli:
    """
    This class hosts SONiC APP Extension cli methods
    """

    def __init__(self, engine):
        self.engine = engine

    def add_repository(self, app_name, repository_name, version=None):
        if version:
            self.engine.run_cmd('sudo sonic-package-manager repository add {} {} --default-reference={}'.format(app_name, repository_name, version), validate=True)
        else:
            self.engine.run_cmd('sudo sonic-package-manager repository add {} {}'.format(app_name, repository_name), validate=True)

    def remove_repository(self, app_name):
        self.engine.run_cmd('sudo sonic-package-manager repository remove {}'.format(app_name), validate=True)

    def install_app(self, app_name, version="", from_repository=''):
        if version:
            self.engine.run_cmd('sudo sonic-package-manager install {}=={} -y'.format(app_name, version), validate=True)
        elif from_repository:
            self.engine.run_cmd('sudo sonic-package-manager install --from-repository {} -y'.format(from_repository), validate=True)
        else:
            self.engine.run_cmd('sudo sonic-package-manager install {} -y'.format(app_name), validate=True)

    def uninstall_app(self, app_name, is_force=True):
        if is_force:
            self.engine.run_cmd('sudo sonic-package-manager uninstall {} -y --force'.format(app_name), validate=True)
        else:
            self.engine.run_cmd('sudo sonic-package-manager uninstall {} -y'.format(app_name), validate=True)

    def show_app_list(self):
        return self.engine.run_cmd('sudo sonic-package-manager list')

    def parse_app_package_list_dict(self):
        """
        Parse app package data into dict by "sonic-package-manager list" output
        :Return app package dict, or raise exception
        """
        app_package_repo_list = self.show_app_list()
        # TODO: This is a workaround, need to remove the following code after the issue is fixed
        # TODO:  and the fix merged to other branches based on master, like DPU.
        # TODO: [SONIC - Design] Bug SW #3322943:[Non-Functional ] [app|spm] |
        # TODO: The return of sonic-package-manager list includes some redundant strings
        # -----------------------------workaround-------------------------------
        unexpected_line = 'libyang[1]:'
        if unexpected_line in app_package_repo_list:
            name_offset = 0
            for line in app_package_repo_list.split("\n"):
                if "Name" in line and "Repository" in line:
                    break
                name_offset += 1

            app_package_repo_dict = generic_sonic_output_parser(app_package_repo_list,
                                                                headers_ofset=name_offset,
                                                                len_ofset=1 + name_offset,
                                                                data_ofset_from_start=2 + name_offset,
                                                                data_ofset_from_end=None,
                                                                column_ofset=2,
                                                                output_key='Name')
            return app_package_repo_dict
        # -----------------------------workaround-------------------------------
        app_package_repo_dict = generic_sonic_output_parser(app_package_repo_list,
                                                            headers_ofset=0,
                                                            len_ofset=1,
                                                            data_ofset_from_start=2,
                                                            data_ofset_from_end=None,
                                                            column_ofset=2,
                                                            output_key='Name')
        return app_package_repo_dict

    def enable_app(self, app_name):
        self.engine.run_cmd('sudo config feature state {} enabled'.format(app_name), validate=True)

    def disable_app(self, app_name, validate=True):
        self.engine.run_cmd('sudo config feature state {} disabled'.format(app_name), validate=validate)
        # TODO: WA for issue RM#3943532, remove after it's fixed
        if is_redmine_issue_active([3943532])[0]:
            time.sleep(15)

    def install_app_from_tarball(self, tarball_name):
        self.engine.run_cmd("sudo spm install -y --from-tarball {}".format(tarball_name), validate=True)

    def upgrade_app(self, app_name: str, version: str, is_force_upgrade: bool = False, validate: bool = True,
                    allow_downgrade: bool = False) -> str:
        """
        Upgrade app with specified version from repo:
        :param app_name: app name
        :param version:  app package version
        :param allow_downgrade: allow downgrade, True is allow downgrade, False is not allow
        Return output from command
        """
        allow_downgrade_option = "--allow-downgrade" if allow_downgrade else ""
        if is_force_upgrade:
            output = self.engine.run_cmd("sudo sudo spm install -y -f {}={} {}".format(app_name, version,
                                                                                       allow_downgrade_option),
                                         validate=validate)
        else:
            output = self.engine.run_cmd("sudo sudo spm install -y {}={} {}".format(app_name, version,
                                                                                    allow_downgrade_option),
                                         validate=validate)

        return output

    def upgrade_app_from_tarbll(self, tarball_name: str) -> None:
        """
        Upgrade app with specified version from tarball:
        :param tarball_name: app name
        :param validate: bool
        """
        self.engine.run_cmd("sudo spm upgrade -y --from-tarball {}".format(tarball_name))

    def show_app_version(self, app_name: str, option: str = "") -> str:
        """
        Show app version:
        :param app_name: app name
        :param option: "", plain, all
        :Return app version info
        """
        if option:
            option = "--{}".format(option)
        return self.engine.run_cmd("sudo spm show package versions {} {}".format(app_name, option), validate=True)

    def show_app_manifest(self, app_name: str, version: str = "") -> str:
        """
        Show app manifest:
        :param app_name: app name
        :param version: app version
        :Return specified version app manifest
        """
        return self.engine.run_cmd("sudo spm show package manifest {}={} ".format(app_name, version), validate=True)

    def show_app_changelog(self, app_name: str, version: str = "") -> str:
        """
        Show app version:
        :param app_name: app name
        :param version: app version
        :Return specified version app changelog
        """
        return self.engine.run_cmd("sudo spm show package changelog {}={} ".format(app_name, version), validate=True)

    def verify_version_support_app_ext(self):
        """
        Verify if the version support app ext feature by finding the cmd of sonic-package-manager or not
        :return True if support app ext, else False
        """
        app_ext_cmd_prefix = 'sonic-package-manager'
        output = self.engine.run_cmd('which {}'.format(app_ext_cmd_prefix))
        if app_ext_cmd_prefix in output:
            return True
        return False

    def get_installed_app_version(self, app_name):
        """
        get the installed app version
        :param app_name: app name
        :return: the installed app version
        """
        apps_dict = self.parse_app_package_list_dict()
        app_dict = apps_dict[app_name]
        return app_dict['Version']

    def remove_selected_app_extension(self, app_name):
        logger.info(f'Uninstalling app extension {app_name}')
        self.disable_app(app_name)
        self.uninstall_app(app_name)
        self.remove_repository(app_name)
        logger.info(f'{app_name} uninstalled successfully')

"""

conftest.py

Defines the methods and fixtures which will be used by pytest

"""

import pytest
import logging
import re
import os

from ngts.constants.constants import MarsConstants

logger = logging.getLogger()


def pytest_addoption(parser):
    """
    Parse pytest options
    :param parser: pytest builtin
    """
    logger.info('Parsing deploy type')
    parser.addoption('--deploy_type', action='store', choices=['onie', 'sonic', 'bfb', 'pxe'], required=False, default='onie',
                     help='Deploy type')
    logger.info('Parsing apply_base_config')
    parser.addoption('--apply_base_config', action='store', required=False, default=None,
                     help='Apply base config or not, for canonical True, for community False')
    logger.info('Parsing reboot after install')
    parser.addoption('--reboot_after_install', action='store', required=False, default=None,
                     help='Reboot after installation or not to overcome swss issue')
    logger.info('Parsing is shutdown bgp ')
    parser.addoption('--is_shutdown_bgp', action='store_true', required=False, default=False,
                     help='For sonic install, need shutdown bgp, or it can not access the external IP')
    logger.info('Parsing fw_pkg')
    parser.addoption('--fw_pkg_path', action='store', required=False, default=None,
                     help='firmware package file path')
    logger.info('Parsing base-version')
    parser.addoption("--base-version", action="store", default="",
                     help="URL or path to the SONiC image. Firstly upgrade switch to this version.")
    logger.info('Parsing base-version-dpu')
    parser.addoption("--base-version-dpu", action="store", default="",
                     help="URL or path to the SONiC image for dpu.")
    logger.info('Parsing target-version')
    parser.addoption("--target-version", action="store",
                     help="URL or path to the SONiC image. If this argument is specified, upgrade switch to this \
                              version after upgraded to the base_version. Default: ''")
    logger.info('Parsing serve_files')
    parser.addoption("--serve_files", action="store",
                     help="Specify whether to run http server on the running machine and serve the installer files"
                          "Note: this option is not supported when running from a docker without ip")
    logger.info('Parsing upgrade-only')
    parser.addoption("--upgrade-only", action="store", default="no", choices=["yes", "no"],
                     help="Specify whether to skip topology change and only do upgrade. Default: 'no'")
    logger.info('Parsing deploy_only_target')
    parser.addoption("--deploy_only_target", action="store", default='no', choices=["yes", "no"],
                     dest="deploy_only_target", help="If yes - then the installation of the base version will be "
                                                     "skipped and the target version will be installed instead of "
                                                     "the base.")
    logger.info('Parsing deploy_fanout')
    parser.addoption("--deploy_fanout", help="Specify whether to do fanout deployment. Default is 'no'",
                     choices=["no", "yes"], action="store", default="no")
    logger.info('Parsing onyx_image_url')
    parser.addoption("--onyx_image_url", help="Specify Onyx image url for the fanout switch deployment"
                                              " Example: http://nbu-mtr-nfs.nvidia.com/mswg/release/sx_mlnx_os/lastrc_3_9_3000/X86_64/image-X86_64-3.9.3004-002.img",
                     action="store", default=None)
    logger.info('Parsing port-number')
    parser.addoption("--port-number", action="store", default="",
                     help="Specify the test setup's number of ports. Default: ''")
    logger.info('Parsing recover_by_reboot')
    parser.addoption("--recover_by_reboot", help="If post validation install validation has failed, "
                                                 "reboot the dut and run post validation again."
                                                 "This flag might be useful when the first boot has failed due to fw upgrade timeout",
                     default=True, action='store_true')
    logger.info('Parsing reboot')
    parser.addoption("--reboot", action="store", default="no",
                     choices=["no", "random"] + list(MarsConstants.REBOOT_TYPES.keys()),
                     help="Specify whether reboot the switch after deploy. Default: 'no'")
    logger.info('Parsing additional-apps')
    parser.addoption("--additional-apps", help="Specify url to WJH debian package or JSON data of app extensions",
                     default="", action="store")
    parser.addoption("--wjh-deb-url", help="Specify url to WJH debian package", default="", action="store")

    logger.info('Parsing workspace-path')
    parser.addoption("--workspace-path", help="Specify workspace path",
                     default="/root/mars/workspace/", action="store")
    logger.info('Parsing post_validation')
    parser.addoption("--post_validation", help="Specify whether do post installation validation",
                     default=False, action="store")
    logger.info('Parsing deploy_dpu')
    parser.addoption("--deploy_dpu", help="Specify whether to deploy dpu for smart switch setup.",
                     action="store", default="no")

    logger.info('Parsing destination hwsku')
    parser.addoption("--dest_hwsku", help="The destination hwsku", default="", action="store")


@pytest.fixture(scope="module")
def workspace_path(request):
    """
    Method for getting workspace path from pytest arguments
    :param request: pytest builtin
    :return: workspace path
    """
    return request.config.getoption('--workspace-path')


@pytest.fixture(scope="module")
def deploy_type(request):
    """
    Method for getting deploy type from pytest arguments
    :param request: pytest builtin
    :return: deploy type
    """
    return request.config.getoption('--deploy_type')


@pytest.fixture(scope="module")
def base_version(request):
    """
    Method for getting base version from pytest arguments
    :param request: pytest builtin
    :return: base version
    """
    return request.config.getoption('--base-version')


@pytest.fixture(scope="session")
def base_version_dpu(request):
    """
    Method for getting base version for dpu from pytest arguments
    :param request: pytest builtin
    :return: base version
    """
    return request.config.getoption('--base-version-dpu')


@pytest.fixture(scope="module")
def target_version(request):
    """
    Method for getting target version from pytest arguments
    :param request: pytest builtin
    :return: target version
    """
    return request.config.getoption('--target-version')


@pytest.fixture(scope="module")
def serve_files(request):
    """
    Method for getting serve files from pytest arguments
    :param request: pytest builtin
    :return: serve files
    """
    return request.config.getoption('--serve_files')


@pytest.fixture(scope="module")
def upgrade_only(request):
    """
    Method for getting upgrade-only from pytest arguments
    :param request: pytest builtin
    :return: True if upgrade-only == yes, False - otherwise
    """
    upgrade_only_arg = request.config.getoption('--upgrade-only')
    if upgrade_only_arg and re.match(r"^(no|false)$", upgrade_only_arg, re.I):
        return True
    return False


@pytest.fixture(scope="module")
def post_installation_validation(request):
    """
    Method for getting post-validation from pytest arguments
    :param request: pytest builtin
    :return: post_validation (True or False)
    """
    return request.config.getoption('--post_validation')


@pytest.fixture(scope="module")
def destination_hwsku(request):
    """
    Method for getting post-validation from pytest arguments
    :param request: pytest builtin
    :return: destination hwsku
    """
    return request.config.getoption('--dest_hwsku')


@pytest.fixture(scope="module")
def deploy_only_target(request):
    """
    Method for getting deploy only target from pytest arguments
    :param request: pytest builtin
    :return: True/False
    """
    deploy_only_target_arg = request.config.getoption('--deploy_only_target')
    return deploy_only_target_arg == "yes"


@pytest.fixture(scope="module")
def apply_base_config(request):
    """
    Method for getting base version from pytest arguments
    :param request: pytest builtin
    :return: apply base config flag
    """
    return request.config.getoption('--apply_base_config')


@pytest.fixture(scope="module")
def deploy_fanout(request):
    """
    Method for getting deploy only target from pytest arguments
    :param request: pytest builtin
    :return: True/False
    """
    deploy_fanout_arg = request.config.getoption('--deploy_fanout')
    return deploy_fanout_arg == "yes"


@pytest.fixture(scope="module")
def reboot_after_install(request):
    """
    Method for getting reboot after install flag pytest arguments
    :param request: pytest builtin
    :return: whether to do reboot after installation to overcome swss docker in exited state
    """
    return request.config.getoption('--reboot_after_install')


@pytest.fixture(scope="module")
def is_shutdown_bgp(request):
    """
    Method for getting shutdown bgp flag from pytest arguments
    :param request: pytest builtin
    :return: True or False
    """
    return request.config.getoption('--is_shutdown_bgp')


@pytest.fixture(scope="module")
def onyx_image_url(request):
    """
    Method for getting onyx_image_url from pytest arguments
    :param request: pytest builtin
    :return: onyx_image_url
    """
    return request.config.getoption('--onyx_image_url')


@pytest.fixture(scope="module")
def port_number(request):
    """
    Method for getting port-number from pytest arguments
    :param request: pytest builtin
    :return: port-number
    """
    return request.config.getoption('--port-number')


@pytest.fixture(scope="module")
def recover_by_reboot(request):
    """
    Method for getting recover_by_reboot from pytest arguments
    :param request: pytest builtin
    :return: recover_by_reboot
    """
    return request.config.getoption('--recover_by_reboot')


@pytest.fixture(scope="module")
def fw_pkg_path(request):
    """
    Method for getting firmware package file path from pytest arguments
    :param request: pytest builtin
    :return: path to firmware package
    """
    fw_pkg_path = request.config.getoption('--fw_pkg_path')
    if fw_pkg_path and not os.path.exists(fw_pkg_path):
        # if the fw_pkg_path give does not exist, then use the default one
        sonic_mgmt_path = os.path.dirname(os.path.abspath(__file__)).split('ngts')[0]
        fw_pkg_path = os.path.join(sonic_mgmt_path, MarsConstants.UPDATED_FW_TAR_PATH)
    return fw_pkg_path


@pytest.fixture(scope='session')
def reboot(request):
    """
    Method for getting the reboot from pytest arguments
    :param request: pytest builtin
    :return: reboot
    """
    return request.config.getoption('--reboot')


@pytest.fixture(scope='session')
def wjh_deb_url(request):
    """
    Method for getting the WJH from pytest arguments
    :param request: pytest builtin
    :return: wjh-deb-url
    """
    return request.config.getoption('--wjh-deb-url')


@pytest.fixture(scope='session')
def additional_apps(request):
    """
    Method for getting the additional-apps from pytest arguments
    :param request: pytest builtin
    :return: additional-apps
    """
    return request.config.getoption('--additional-apps')


@pytest.fixture(scope="session")
def deploy_dpu(request):
    """
    Method for getting deploy_dpu from pytest arguments
    :param request: pytest builtin
    :return: deploy_dpu
    """
    deploy_dpu = request.config.getoption('--deploy_dpu')
    return deploy_dpu == "yes"

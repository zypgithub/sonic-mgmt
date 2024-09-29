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

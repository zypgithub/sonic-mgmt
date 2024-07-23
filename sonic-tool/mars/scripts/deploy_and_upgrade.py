#!/usr/bin/env python
"""
Prepare the SONiC testing topology.

This script is executed on the STM node. It establishes SSH connection to the sonic-mgmt docker container (Player) and
run commands on it. Purpose is to prepare the SONiC testing topology using the testbed-cli.sh tool.
"""

# Builtin libs
import argparse
import os
import random
import re
import socket
import sys
import contextlib
import subprocess
import traceback
import logging
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
import shutil
import json
import time
from multiprocessing.pool import ThreadPool
from retry.api import retry_call

# Third-party libs
from fabric import Config
from fabric import Connection

# Home-brew libs
from lib import constants
from lib.utils import parse_topology, get_logger

logger = get_logger("DeployUpgrade")


def _parse_args():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--topo", dest="topo", help="Path to the MARS topology configuration file")
    parser.add_argument("--dut-name", required=True, dest="dut_name", help="The DUT name")
    parser.add_argument("--sonic-topo", required=True, dest="sonic_topo",
                        help="The topo for SONiC testing, for example: t0, t1, t1-lag, ptf32, ...")
    parser.add_argument("--base-version", required=True, dest="base_version",
                        help="URL or path to the SONiC image. Firstly upgrade switch to this version.")
    parser.add_argument("--upgrade_type", nargs="?", default="sonic", dest="upgrade_type")
    parser.add_argument("--target-version", nargs="?", default="", dest="target_version",
                        help="URL or path to the SONiC image. If this argument is specified, upgrade switch to this \
                              version after upgraded to the base_version. Default: ''")
    parser.add_argument('--log_level', dest='log_level', default=logging.INFO, help='log verbosity')
    parser.add_argument("--upgrade-only", nargs="?", default="no", dest="upgrade_only",
                        help="Specify whether to skip topology change and only do upgrade. Default: 'no'")
    parser.add_argument("--reboot", nargs="?", default="no", choices=["no", "random"] + list(constants.REBOOT_TYPES.keys()),
                        dest="reboot", help="Specify whether reboot the switch after deploy. Default: 'no'")
    parser.add_argument("--repo-name", dest="repo_name", help="Specify the sonic-mgmt repository name")
    parser.add_argument("--workspace-path", dest="workspace_path",
                        help="Specify the location of sonic-mgmt repo on sonic-mgmt docker container.")
    parser.add_argument("--port-number", nargs="?", default="", dest="port_number",
                        help="Specify the test setup's number of ports. Default: ''")
    parser.add_argument("--setup-name", default="", dest="setup_name",
                        help="Specify the test setup name. Default: ''")
    parser.add_argument("--recover_by_reboot", help="If post validation install validation has failed, "
                                                    "reboot the dut and run post validation again."
                                                    "This flag might be useful when the first boot has failed due to fw upgrade timeout",
                        dest="recover_by_reboot", default=True, action='store_true')
    parser.add_argument("--serve_files", help="Specify whether to run http server on the runnning machine and serve the installer files"
                                              "Note: this option is not supported when running from a docker without ip",
                        dest="serve_files", default=False, action='store_true')
    parser.add_argument("--deploy_only_target", nargs="?", default='no', choices=["yes", "no"],
                        dest="deploy_only_target", help="If yes - then the installation of the base version will be "
                                                        "skipped and the target version will be installed instead of "
                                                        "the base.")
    parser.add_argument("--deploy_fanout", help="Specify whether to do fanout deployment. Default is 'no'",
                        choices=["no", "yes"], dest="deploy_fanout", default="no")
    parser.add_argument("--onyx_image_url", help="Specify Onyx image url for the fanout switch deployment"
                                                 " Example: http://nbu-mtr-nfs.nvidia.com/mswg/release/sx_mlnx_os/lastrc_3_9_3000/X86_64/image-X86_64-3.9.3004-002.img",
                        dest="onyx_image_url", default=None)
    parser.add_argument("--wjh-deb-url", help="Specify url to WJH debian package",
                        dest="wjh_deb_url", default="")
    parser.add_argument("--app_extension_dict_path",
                       help="Specify path with json data of app extensions"
                            " Content of file: '{\"lc-manager\":\"harbor.mellanox.com/sonic-lc-manager/lc-manager:0.0.6\","
                            "\"p4-sampling\":\"harbor.mellanox.com/sonic-p4/p4-sampling:0.2.0-004\"}' ",
                       dest="app_extension_dict_path", default="")
    parser.add_argument("--additional-apps", help="Specify url to WJH debian package or JSON data of app extensions",
                        dest="additional_apps", default="")

    return parser.parse_args()


class ImageHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    @summary: HTTP request handler class, for serving SONiC image files over HTTP.
    """
    served_files = {}

    def do_GET(self):
        """
        @summary: Handling HTTP GET requests.
        """
        if self.path == "/favicon.ico":
            self.send_error(404, "No /favicon.ico")
            return None

        if self.path not in self.served_files.keys():
            self.send_error(404, "Requested URL is not found")
            return None

        f = self.send_head(self.path)
        if f:
            shutil.copyfileobj(f, self.wfile)
            f.close()

    def send_head(self, request_path):
        """
        @summary: Send HTTP header
        @param request_path: Path of the HTTP Request
        """
        served_file = self.served_files[request_path]
        if not os.path.isfile(served_file):
            self.send_error(404, "File %s not found for /%s" % (served_file, request_path))
            return None

        try:
            f = open(served_file, "rb")
        except IOError:
            self.send_error(404, "Read file %s failed" % served_file)
            return None
        self.send_response(200)
        self.send_header("Content-type", "application/octet-stream")
        fs = os.fstat(f.fileno())
        self.send_header("Content-Length", str(fs[6]))
        self.end_headers()
        return f


def separate_logger(func):
    """
    Decorator which run method in silent mode(redirect stdout and stderr to file) without print output,
    output will be printed only in case of failure or in case of using logger
    """
    @contextlib.contextmanager
    def redirect_stdout_stderr(std_data_file_name):
        original_out = sys.stdout
        original_err = sys.stderr
        try:
            with open(std_data_file_name, 'w') as logdata:
                sys.stdout = logdata
                sys.stderr = logdata
                yield
        finally:
            sys.stdout = original_out
            sys.stderr = original_err

    def get_std_data(std_data_filename):
        with open(std_data_filename) as data:
            return data.read()

    def get_allure_url(std_data_filename):
        allure_urls = []
        allure_url_regex = 'Allure report URL: (http:.*html)'
        with open(std_data_filename) as data:
            for line in data.readlines():
                if re.search(allure_url_regex, line):
                    allure_urls.append(re.search(allure_url_regex, line).group(1))
        return allure_urls

    def log_allure_urls(allure_urls, method_name):
        for report in allure_urls:
            logger.info('Allure report URL for {}: {}'.format(method_name, report))


    def wrapper(*args, **kwargs):
        method_name = func.__name__
        dut_name = kwargs.get('dut_name')
        std_data_filename = "/tmp/{}_{}.log".format(method_name, dut_name)

        logger.info('#' * 100)
        logger.info('Running method: {}'.format(method_name))
        logger.info('#' * 100)

        try:
            with redirect_stdout_stderr(std_data_filename):
                func(*args, **kwargs)
            logger.debug(get_std_data(std_data_filename))
        except Exception as err:
            logger.error(get_std_data(std_data_filename))
            raise Exception(err)
        finally:
            logger.info('#' * 100)
            log_allure_urls(get_allure_url(std_data_filename), method_name)
            logger.info('Finished run for method: {}'.format(method_name))
            logger.info('#' * 100)

    return wrapper


def start_http_server(served_files):
    """
    @summary: Use ThreadPool to start a HTTP server
    @param served_files: Dictionary of the files to be served. Dictionary format:
        {"/base_version": "/.autodirect/sw_system_release/sonic/201811-latest-sonic-mellanox.bin",
         "/target_version": "/.autodirect/sw_system_release/sonic/master-latest-sonic-mellanox.bin"}
    """
    logger.info("Try to serve files over HTTP:\n%s" % json.dumps(served_files, indent=4))
    ImageHTTPRequestHandler.served_files = served_files
    httpd = HTTPServer(("", 0), ImageHTTPRequestHandler)

    def run_httpd():
        httpd.serve_forever()

    pool = ThreadPool()
    pool.apply_async(run_httpd)
    time.sleep(5)  # The http server needs couple of seconds to startup
    logger.info("Started HTTP server on STM to serve files %s over http://%s:%s" %
                (str(served_files), httpd.server_name, httpd.server_port))
    return httpd


def prepare_images(base_version, target_version, serve_file):
    """
    Method which starts HTTP server if need and share image via HTTP
    """
    image_urls = {"base_version": "", "target_version": ""}

    if serve_file:
        serve_files_over_http(base_version, target_version, image_urls)
    else:
        set_image_path(base_version, "base_version", image_urls)
        if target_version:
            set_image_path(target_version, "target_version", image_urls)

    for image_role in image_urls:
        logger.info('Image {image_role} URL is:{image}'.format(image_role=image_role, image=image_urls[image_role]))
    return image_urls


def serve_files_over_http(base_version, target_version, image_urls):
    served_files = {}
    verify_file_exists(base_version)
    served_files["/base_version"] = base_version
    if target_version:
        verify_file_exists(target_version)
        served_files["/target_version"] = target_version

    httpd = start_http_server(served_files)
    http_base_url = "http://{}:{}".format(httpd.server_name, httpd.server_port)
    for served_file_path in served_files:
        image_urls[served_file_path.lstrip("/")] = http_base_url + served_file_path


def set_image_path(image_path, image_key, image_dict):
    if is_url(image_path):
        path = image_path
    else:
        verify_file_exists(image_path)
        logger.info("Image {} path is:{}".format(image_key, os.path.realpath(image_path)))
        path = get_installer_url_from_nfs_path(image_path)
    image_dict[image_key] = path


def is_url(image_path):
    return re.match('https?://', image_path)


def get_installer_url_from_nfs_path(image_path):
    verify_image_stored_in_nfs(image_path)
    image_path = get_image_path_in_new_nfs_dir(image_path)
    return "{http_base}{image_path}".format(http_base=constants.HTTP_SERVER_NBU_NFS, image_path=image_path)


def verify_file_exists(image_path):
    is_file = os.path.isfile(image_path)
    assert is_file, "Cannot access Image {}: no such file.".format(image_path)


def verify_image_stored_in_nfs(image_path):
    nfs_base_path = '\/auto\/|\/\.autodirect\/'
    is_located_in_nfs = re.match(r"^({nfs_base_path}).+".format(nfs_base_path=nfs_base_path), image_path)
    assert is_located_in_nfs, "The Image must be located under {nfs_base_path}".\
        format(nfs_base_path=nfs_base_path)


def get_image_path_in_new_nfs_dir(image_path):
    return re.sub(r"^\/\.autodirect\/", "/auto/", image_path)

@separate_logger
def generate_minigraph(ansible_path, mgmt_docker_engine, dut_name, sonic_topo, port_number):
    """
    Method which doing minigraph generation
    """
    with mgmt_docker_engine.cd(ansible_path):
        logger.info("Generating minigraph")
        cmd = "./testbed-cli.sh gen-mg {SWITCH}-{TOPO} lab vault".format(SWITCH=dut_name, TOPO=sonic_topo)
        if port_number:
            cmd += " -e port_number={}".format(port_number)
        logger.info("Running CMD: {}".format(cmd))
        retries = initial_count = 3
        SLEEP_TIME = 30
        while retries:
            try:
                mgmt_docker_engine.run(cmd)
                break
            except Exception:
                logger.warning("Failed in Generating minigraph. Trying again. Try number {} ".
                               format(initial_count - retries + 1))
                logger.warning(traceback.print_exc())
                logger.error('Sleep {} seconds after attempt'.format(SLEEP_TIME))
                time.sleep(SLEEP_TIME)
                retries = retries - 1


def _get_hostname_from_ip(ip):
    host_name_index = 0
    hostname_str = socket.gethostbyaddr(ip)[host_name_index]
    return _remove_mlnx_lab_suffix(hostname_str)


def _remove_mlnx_lab_suffix(hostname_string):
    """
    Returns switch hostname without mlnx lab prefix
    :param hostname_string: 'arc-switch1030.mtr.labs.mlnx'
    :return: arc-switch1030
    """
    host_name_index = 0
    return hostname_string.split('.')[host_name_index]


@separate_logger
def deploy_fanout(ansible_path, mgmt_docker_engine, topo, setup_name, onyx_image_url, dut_name):
    """
    Method which deploy fanout switch config
    """
    logger.info("Performing reset_factory on fanout switch")
    onyx_image_argument = " --onyx_image_url={} ".format(onyx_image_url) if onyx_image_url else ''
    cmd = "PYTHONPATH=/devts:{sonic_mgmt_dir} {ngts_pytest} --setup_name={setup_name} --rootdir={sonic_mgmt_dir}/ngts" \
          " -c {sonic_mgmt_dir}/ngts/pytest.ini --log-level=INFO --clean-alluredir --alluredir=/tmp/allure-results" \
          " --disable_loganalyzer {onyx_image_argument}" \
          " {sonic_mgmt_dir}ngts/scripts/reset_fanout/fanout_reset_factory_test.py".\
        format(ngts_pytest=constants.NGTS_PATH_PYTEST, sonic_mgmt_dir=constants.SONIC_MGMT_DIR, setup_name=setup_name,
               onyx_image_argument=onyx_image_argument)
    with mgmt_docker_engine.cd(ansible_path):
        logger.info("Running CMD: {}".format(cmd))
        mgmt_docker_engine.run(cmd)
    logger.info("Performing deploy fanout")
    fanout_device_ip = topo.get_device_by_topology_id(constants.FANOUT_DEVICE_ID).BASE_IP
    host_name = _get_hostname_from_ip(fanout_device_ip)
    pfcwd_dockers_url = '{}/auto/sw_system_project/sonic/docker/'.format(constants.HTTP_SERVER_NBU_NFS)
    with mgmt_docker_engine.cd(ansible_path):
        cmd = "ansible-playbook -i lab fanout.yml -l {host_name} -e pfcwd_dockers_url={pfcwd_dockers_url} -vvv".format(
            host_name=host_name, pfcwd_dockers_url=pfcwd_dockers_url)
        logger.info("Running CMD: {}".format(cmd))
        return mgmt_docker_engine.run(cmd)


@separate_logger
def recover_topology(ansible_path, mgmt_docker_engine, dut_name, sonic_topo, ptf_tag):
    """
    Method which add cEOS dockers and topo in case of community setup
    """
    logger.info("Preparing topology for SONiC testing")
    with mgmt_docker_engine.cd(ansible_path):
        logger.info("Remove all topologies. This may increase a chance to deploy a new one successful")
        for topology in constants.TOPO_ARRAY:
            logger.info("Remove topo {}".format(topology))
            cmd = "./testbed-cli.sh -k ceos remove-topo {SWITCH}-{TOPO} vault".format(SWITCH=dut_name, TOPO=topology)
            logger.info("Running CMD: {}".format(cmd))
            mgmt_docker_engine.run(cmd, warn=True)

        logger.info("Add topology")
        cmd = "./testbed-cli.sh -k ceos add-topo {SWITCH}-{TOPO} vault -e ptf_imagetag={PTF_TAG}".format(SWITCH=dut_name,
                                                                                                         TOPO=sonic_topo,
                                                                                                         PTF_TAG=ptf_tag)
        logger.info("Running CMD: {}".format(cmd))
        mgmt_docker_engine.run(cmd)


def get_sonic_branch(image_path):
    """
    Get image branch from path: /auto/sw_system_release/sonic/master.234-27a6641fb_Internal/Mellanox/sonic-mellanox.bin
    :param image_path: example: /auto/sw_system_release/sonic/master.234-27a6641fb_Internal/Mellanox/sonic-mellanox.bin
    :return: branch, example: master
    """
    branch_part_index = 1
    real_path = os.path.realpath(image_path)
    branch = real_path.split('/auto/sw_system_release/sonic/')[branch_part_index][:6]
    return branch


def get_ptf_docker_tag(image_path):
    """
    Get PTF docker tag from SONiC image path
    :param image_path: example: /auto/sw_system_release/sonic/master.234-27a6641fb_Internal/Mellanox/sonic-mellanox.bin
    :return: ptf docker tag, example: '42007'
    """
    ptf_tag = '558858'
    try:
        if is_url(image_path):
            file_path_index = 3
            image_path = '/' + '/'.join(image_path.split('/')[file_path_index:])
        branch = get_sonic_branch(image_path)
        logger.info('SONiC branch is: {}'.format(branch))
        ptf_tag = constants.BRANCH_PTF_MAPPING.get(branch, '558858')
    except Exception as err:
        logger.error('Can not get SONiC branch and PTF tag from path: {}, using "latest". Error: {}'.format(image_path,
                                                                                                            err))

    return ptf_tag


@separate_logger
def install_image(ansible_path, mgmt_docker_engine, sonic_topo, image_url, setup_name, dut_name, upgrade_type='onie'):
    """
    Method which doing installation of image on DUT via ONIE or via SONiC cli
    """
    logger.info("Upgrade switch using SONiC upgrade playbook using upgrade type: {}".format(upgrade_type))
    if sonic_topo == 'ptf-any':
        apply_base_config = '--apply_base_config=True '
    else:
        apply_base_config = ''

    cmd = "PYTHONPATH=/devts:{sonic_mgmt_dir} {ngts_pytest} --setup_name={setup_name} --rootdir={sonic_mgmt_dir}/ngts" \
          " -c {sonic_mgmt_dir}/ngts/pytest.ini --log-level=INFO --clean-alluredir --alluredir=/tmp/allure-results" \
          " --base_version={base_version} --deploy_type={deploy_type} --disable_loganalyzer {apply_base_config} " \
          " --fw_pkg_path={sonic_mgmt_dir}/{updated_fw_tar_path}" \
          " {sonic_mgmt_dir}/ngts/scripts/sonic_deploy/test_sonic_deploy_image.py".\
        format(ngts_pytest=constants.NGTS_PATH_PYTEST, sonic_mgmt_dir=constants.SONIC_MGMT_DIR, setup_name=setup_name,
               base_version=image_url, deploy_type=upgrade_type, apply_base_config=apply_base_config,
               updated_fw_tar_path=constants.UPDATED_FW_TAR_PATH)
    with mgmt_docker_engine.cd(ansible_path):
        logger.info("Running CMD: {}".format(cmd))
        mgmt_docker_engine.run(cmd)

@separate_logger
def deploy_minigprah(ansible_path, mgmt_docker_engine, dut_name, sonic_topo, recover_by_reboot):
    """
    Method which doing minigraph deploy on DUT
    """
    with mgmt_docker_engine.cd(ansible_path):
        cmd = "ansible-playbook -i inventory --limit {SWITCH}-{TOPO} deploy_minigraph.yml " \
              "-e dut_minigraph={SWITCH}.{TOPO}.xml -b -vvv".format(SWITCH=dut_name, TOPO=sonic_topo)
        logger.info("Running CMD: {}".format(cmd))
        if recover_by_reboot:
            try:
                logger.info("Deploying minigraph")
                return mgmt_docker_engine.run(cmd)
            except Exception:
                logger.warning("Failed in Deploying minigraph")
                logger.warning("Performing a reboot and retrying")
                reboot_validation(ansible_path, mgmt_docker_engine, "reboot", dut_name, sonic_topo)
        logger.info("Deploying minigraph")
        return mgmt_docker_engine.run(cmd)


@separate_logger
def post_install_check(ansible_path, mgmt_docker_engine, dut_name, sonic_topo):
    """
    Method which doing post install checks: check ports status, check dockers status, etc.
    """
    with mgmt_docker_engine.cd(ansible_path):
        post_install_validation = "ansible-playbook -i inventory --limit {SWITCH}-{TOPO} post_upgrade_check.yml -e topo={TOPO} " \
              "-b -vvv".format(SWITCH=dut_name, TOPO=sonic_topo)
        logger.info("Performing post-install validation by running: {}".format(post_install_validation))
        return mgmt_docker_engine.run(post_install_validation)


@separate_logger
def reboot_validation(ansible_path, mgmt_docker_engine, reboot, dut_name, sonic_topo):
    """
    Method which doing reboot validation
    """
    if reboot == "random":
        reboot_type = random.choice(list(constants.REBOOT_TYPES.values()))
    else:
        reboot_type = constants.REBOOT_TYPES[reboot]

    with mgmt_docker_engine.cd(ansible_path):
        logger.info("Running reboot type: {}".format(reboot_type))
        reboot_res = mgmt_docker_engine.run("ansible-playbook test_sonic.yml -i inventory --limit {SWITCH}-{TOPO} \
                                     -e testbed_name={SWITCH}-{TOPO} -e testbed_type={TOPO} \
                                     -e testcase_name=reboot -e reboot_type={REBOOT_TYPE} -vvv".format(SWITCH=dut_name,
                                                                                                       TOPO=sonic_topo,
                                                                                                       REBOOT_TYPE=reboot_type),
                                            warn=True)
        logger.warning("reboot type: {} failed".format(reboot_type))
        logger.debug("reboot type {} failure results: {}".format(reboot_type, reboot_res))
        logger.info("Running reboot type: {} after {} failed".format(constants.REBOOT_TYPES["reboot"], reboot_type))
        if reboot_res.failed and reboot != constants.REBOOT_TYPES["reboot"]:
           reboot_res = mgmt_docker_engine.run("ansible-playbook test_sonic.yml -i inventory --limit {SWITCH}-{TOPO} \
                            -e testbed_name={SWITCH}-{TOPO} -e testbed_type={TOPO} -e testcase_name=reboot \
                            -e reboot_type={REBOOT_TYPE} -vvv".format(SWITCH=dut_name, TOPO=sonic_topo,
                                                                      REBOOT_TYPE=constants.REBOOT_TYPES["reboot"]),
                                   warn=True)
           logger.info("reboot type: {} result is {}"
                       .format(constants.REBOOT_TYPES["reboot"], reboot_res))


@separate_logger
def install_wjh(ansible_path, mgmt_docker_engine, dut_name, sonic_topo, wjh_deb_url):
    """
    Method which doing WJH installation on DUT
    """
    logger.info("Starting installation of SONiC what-just-happened")
    with mgmt_docker_engine.cd(ansible_path):
        mgmt_docker_engine.run("ansible-playbook install_wjh.yml -i inventory --limit {SWITCH}-{TOPO} \
                        -e testbed_name={SWITCH}-{TOPO} -e testbed_type={TOPO} \
                        -e wjh_deb_url={PATH} -vvv".format(SWITCH=dut_name, TOPO=sonic_topo,
                                                           PATH=wjh_deb_url))

@separate_logger
def install_supported_app_extensions(ansible_path, mgmt_docker_engine, setup_name, dut_name, app_extension_dict_path):
    app_extension_path_str = ''
    if app_extension_dict_path:
        app_extension_path_str = '--app_extension_dict_path={}'.format(app_extension_dict_path)
    cmd = "PYTHONPATH=/devts:{sonic_mgmt_dir} {ngts_pytest} --setup_name={setup_name} --rootdir={sonic_mgmt_dir}/ngts" \
          " -c {sonic_mgmt_dir}/ngts/pytest.ini --log-level=INFO --clean-alluredir --alluredir=/tmp/allure-results " \
          " --disable_loganalyzer {app_extension_path_str} " \
          " {sonic_mgmt_dir}/ngts/scripts/install_app_extension/install_app_extensions.py". \
        format(ngts_pytest=constants.NGTS_PATH_PYTEST, sonic_mgmt_dir=constants.SONIC_MGMT_DIR, setup_name=setup_name,
               app_extension_path_str=app_extension_path_str)
    with mgmt_docker_engine.cd(ansible_path):
        logger.info("Running CMD: {}".format(cmd))
        mgmt_docker_engine.run(cmd)


def validate_args(args):
    if args.deploy_only_target == 'yes' and not args.target_version:
        raise Exception('Argument "target_version" must be provided when "deploy_only_target" flag is set to "yes".'
                        ' Please provide a target version.')
    if args.wjh_deb_url and args.app_extension_dict_path:
        raise Exception('Argument wjh_deb_url or app_extension_dict_path should be provided, you provided both')
    if (args.additional_apps and args.wjh_deb_url) or (args.additional_apps and args.app_extension_dict_path):
        raise Exception('Argument additional_apps can not be used with wjh_deb_url or app_extension_dict_path')


def is_additional_apps_argument_is_deb_package(additional_apps_argument):
    is_deb_package = False
    path = additional_apps_argument
    try:
        if os.path.islink(additional_apps_argument):
            path = os.readlink(additional_apps_argument)
        if path.endswith('.deb'):
            is_deb_package = True
    except OSError:
        pass
    return is_deb_package


def is_additional_apps_argument_is_app_ext_dict(additional_apps_argument):
    is_app_ext_dict = False
    try:
        requests.get('{}/{}'.format(constants.HTTP_SERVER_NBU_NFS, additional_apps_argument)).json()
        is_app_ext_dict = True
    except json.decoder.JSONDecodeError:
        pass
    return is_app_ext_dict


def main():

    logger.info("Deploy SONiC testing topology and upgrade switch")

    args = _parse_args()
    validate_args(args)
    workspace_path = args.workspace_path
    repo_name = args.repo_name
    repo_path = os.path.join(workspace_path, repo_name)
    ansible_path = os.path.join(repo_path, "ansible")
    logger.setLevel(args.log_level)

    topo = parse_topology(args.topo)
    sonic_mgmt_device = topo.get_device_by_topology_id(constants.SONIC_MGMT_DEVICE_ID)
    hypervisor_device = topo.get_device_by_topology_id(constants.TEST_SERVER_DEVICE_ID)

    sonic_mgmt_device_username, sonic_mgmt_device_password = topo.get_user_access(sonic_mgmt_device.USERS[0])
    hypervisor_device_username, hypervisor_device_password = topo.get_user_access(hypervisor_device.USERS[0])

    mgmt_docker_engine = Connection(sonic_mgmt_device.BASE_IP, user=sonic_mgmt_device_username,
                                    config=Config(overrides={"run": {"echo": True}}),
                                    connect_kwargs={"password": sonic_mgmt_device_password})

    hypervisor_engine = Connection(hypervisor_device.BASE_IP, user=hypervisor_device_username,
                                   config=Config(overrides={"run": {"echo": True}}),
                                   connect_kwargs={"password": hypervisor_device_password})

    image_urls = prepare_images(args.base_version, args.target_version, args.serve_files)

    ptf_tag = get_ptf_docker_tag(args.base_version)
    if args.target_version:
        ptf_tag = get_ptf_docker_tag(args.target_version)

    if args.upgrade_only and re.match(r"^(no|false)$", args.upgrade_only, re.I):
        recover_topology(ansible_path=ansible_path, mgmt_docker_engine=mgmt_docker_engine,
                         dut_name=args.dut_name, sonic_topo=args.sonic_topo, ptf_tag=ptf_tag)

    base_version_url = image_urls["base_version"]
    if args.deploy_only_target == 'yes':
        if image_urls["target_version"]:
            base_version_url = image_urls["target_version"]
        else:
            raise Exception('Argument "target_version" must be provided when "deploy_only_target" flag is set to "yes".'
                            ' Please provide a target version.')

    install_image(ansible_path=ansible_path, mgmt_docker_engine=mgmt_docker_engine,
                  sonic_topo=args.sonic_topo, setup_name=args.setup_name,
                  image_url=base_version_url, upgrade_type=args.upgrade_type, dut_name=args.dut_name)

    # Community only steps
    if args.sonic_topo != 'ptf-any':
        if args.deploy_fanout == 'yes':
            deploy_fanout(ansible_path=ansible_path, mgmt_docker_engine=mgmt_docker_engine,
                          topo=topo, setup_name=args.setup_name, onyx_image_url=args.onyx_image_url,
                          dut_name=args.dut_name)
        generate_minigraph(ansible_path=ansible_path, mgmt_docker_engine=mgmt_docker_engine, dut_name=args.dut_name,
                           sonic_topo=args.sonic_topo, port_number=args.port_number)
        retry_call(deploy_minigprah, fargs=[ansible_path, mgmt_docker_engine, args.dut_name, args.sonic_topo,
                                            args.recover_by_reboot], tries=3, delay=30, logger=logger)

    if 'sonic_bluefield' not in args.setup_name:
        post_install_check(ansible_path=ansible_path, mgmt_docker_engine=mgmt_docker_engine, dut_name=args.dut_name,
                           sonic_topo=args.sonic_topo)

    if image_urls["target_version"] and args.deploy_only_target == 'no':
        logger.info("Target version is defined, upgrade switch again to the target version.")

        install_image(ansible_path=ansible_path, mgmt_docker_engine=mgmt_docker_engine,
                      sonic_topo=args.sonic_topo, setup_name=args.setup_name,
                      image_url=image_urls["target_version"], upgrade_type='sonic', dut_name=args.dut_name)

        post_install_check(ansible_path=ansible_path, mgmt_docker_engine=mgmt_docker_engine, dut_name=args.dut_name,
                           sonic_topo=args.sonic_topo)

    if args.reboot and args.reboot != "no":
        reboot_validation(ansible_path=ansible_path, mgmt_docker_engine=mgmt_docker_engine, reboot=args.reboot,
                          dut_name=args.dut_name, sonic_topo=args.sonic_topo)

    if args.additional_apps:
        if is_additional_apps_argument_is_deb_package(args.additional_apps):
            args.wjh_deb_url = '{}{}'.format(constants.HTTP_SERVER_NBU_NFS, args.additional_apps)
        elif is_additional_apps_argument_is_app_ext_dict(args.additional_apps):
            args.app_extension_dict_path = args.additional_apps

    if args.wjh_deb_url:
        install_wjh(ansible_path=ansible_path, mgmt_docker_engine=mgmt_docker_engine, dut_name=args.dut_name,
                    sonic_topo=args.sonic_topo, wjh_deb_url=args.wjh_deb_url)

    if args.app_extension_dict_path:
        install_supported_app_extensions(ansible_path=ansible_path, mgmt_docker_engine=mgmt_docker_engine,
                                         setup_name=args.setup_name,
                                         app_extension_dict_path=args.app_extension_dict_path,
                                         dut_name=args.dut_name)


if __name__ == "__main__":
    main()

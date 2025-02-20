"""
Utilities functions
"""
import logging
import sys
import time
import re

from lib import setup_env

# Required for importing the topology package in ver_sdk
setup_env.extend_sys_path()


def get_logger(name, level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s:%(lineno)d %(message)s"):
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(sys.stdout)
    logger.setLevel(level)
    formatter = logging.Formatter(format)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = get_logger("Utils")

try:
    from topology.TopologyAPI import TopologyAPI
except ImportError as e:
    err_msg="""
    Failed to import module from ver_sdk package. Possible reasons:
    * ver_sdk is not installed
    * ver_sdk path is not in sys.path:
    * topology package is excluded in ver_sdk installation
    Reference:
        "https://wikinox.mellanox.com/display/SW/Install+Ver-SDK+tools+In+User+Space"
    Example command to install ver_sdk:
        /mswg/projects/ver_tools/sdk_exe_folder/install_ver_tools.py --install_pointer VER_SDK-14032-20190819-1030.tar
            --ignore_packages kvl,setuptools
    """
    logger.error(str(e))
    logger.error(err_msg)
    sys.exit(1)


def parse_topology(topo_file_path):
    return TopologyAPI(topo_file_path)


def wait_until(timeout, interval, condition, *args, **kwargs):
    """
    @summary: Wait until the specified condition is True or timeout.
    @param timeout: Maximum time to wait
    @param interval: Poll interval
    @param condition: A function that returns False or True
    @param *args: Extra args required by the 'condition' function.
    @param **kwargs: Extra args required by the 'condition' function.
    @return: If the condition function returns True before timeout, return True. If the condition function raises an
        exception, log the error and keep waiting and polling.
    """
    logger.debug("Wait until %s is True, timeout is %s seconds, checking interval is %s" % \
        (condition.__name__, timeout, interval))
    start_time = time.time()
    elapsed_time = 0
    while elapsed_time < timeout:
        logger.debug("elapsed=%d, timeout=%d" % (elapsed_time, timeout))

        try:
            check_result = condition(*args, **kwargs)
        except Exception as e:
            logger.debug("Exception caught while checking %s: %s" % (condition.__name__, repr(e)))
            check_result = False

        if check_result:
            logger.debug("%s is True, exit early with True" % condition.__name__)
            return True
        else:
            logger.debug("%s is False, wait %d seconds and check again" % (condition.__name__, interval))
            time.sleep(interval)
            elapsed_time = time.time() - start_time

    if elapsed_time >= timeout:
        logger.debug("%s is still False after %d seconds, exit with False" % (condition.__name__, timeout))
        return False


def get_allure_project_id(setup_name, test_script_full_path, get_dut_name_only=False, allure_project_id_suffix=None):
    max_length = 70
    non_alphabetic_chars = "[^0-9a-zA-Z]+"
    if get_dut_name_only:
        allure_proj = setup_name
    else:
        sonic_mgmt_folder_index = test_script_full_path.find('mgmt')
        if sonic_mgmt_folder_index != -1:
            test_script_full_path = test_script_full_path[sonic_mgmt_folder_index:]
        allure_proj = "{}-{}".format(setup_name, test_script_full_path)
    allure_proj = allure_proj[:max_length]
    if allure_project_id_suffix:
        allure_project_id_suffix_str = "-{}".format(allure_project_id_suffix)
        allure_proj = allure_proj[:(max_length-len(allure_project_id_suffix))]
        allure_proj += allure_project_id_suffix_str
    else:
        allure_proj = allure_proj[:max_length]
    allure_proj = re.sub(non_alphabetic_chars, "-", allure_proj)
    allure_proj = allure_proj.strip('-')
    allure_proj = allure_proj.lower()
    return allure_proj

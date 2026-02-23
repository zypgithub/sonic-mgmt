import pytest
import time
import logging

from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_constants.constants_nvos import IbConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tools.test_utils import allure_utils as allure
from retry import retry

logger = logging.getLogger()

OPEN_SM_PATH = "/opt/ufm/opensm/sbin/opensm"  # UFM opensm (used for multiplanar)
DOCA_OPEN_SM_PATH = "opensm"  # Doca opensm - executed directly via Doca, not through UFM
SM_MASTER_OPEN_SM_PATH = "/labhome/juliav/workspace/sm_regression/sources/SM_MASTER/usr/sbin/opensm"  # SM Master path
OPEN_SM_CFG_PATH = "/auto/sw_system_project/NVOS_INFRA/verification/issu/opensm.cfg"
MISSING_HFNM_MESSAGE = "HA and HFNM can't be found in topology"
MISSING_HOST = "Host {} is missing from topology"
GET_OPENSM_CMD = "ps aux | grep opensm"


class OpenSmTool:
    # Class-level configuration for opensm path.
    # Set automatically by the configure_opensm_path fixture in conftest.py
    OPENSM_PATH = SM_MASTER_OPEN_SM_PATH

    @classmethod
    def set_opensm_path(cls, opensm_path):
        """
        Set opensm path for the test session.
        Called by the configure_opensm_path fixture in conftest.py.

        Args:
            opensm_path: The opensm path to use.
        """
        cls.OPENSM_PATH = opensm_path
        is_doca = opensm_path == DOCA_OPEN_SM_PATH
        logging.info(f"OpenSmTool configured: OPENSM_PATH={cls.OPENSM_PATH} (doca={is_doca})")

    @staticmethod
    def start_open_sm(engines=None, multiplanar=False):
        """Start OpenSM."""
        return OpenSmTool.start_open_sm_on_server(engines, multiplanar)

    @staticmethod
    def stop_open_sm(engines=None):
        return OpenSmTool.stop_open_sm_on_server(engines)

    @staticmethod
    def _get_opensm_process_lines(output):
        """Filter ps aux output to get only opensm process lines (excludes grep)."""
        return [line for line in output.split('\n') if 'grep' not in line and line.strip()]

    @staticmethod
    def start_open_sm_on_server(engines, multiplanar=False):
        """Start OpenSM if it's not running, or restart if wrong version is detected."""
        if not hasattr(engines, "hfnm"):
            logging.warning(MISSING_HFNM_MESSAGE)
            return ResultObj(False, MISSING_HFNM_MESSAGE)

        is_running, port_name = OpenSmTool.is_sm_running_on_server(engines)

        # Determine desired opensm path
        if OpenSmTool.OPENSM_PATH == DOCA_OPEN_SM_PATH:
            desired_path = DOCA_OPEN_SM_PATH
        elif multiplanar:
            desired_path = OPEN_SM_PATH
        else:
            desired_path = OpenSmTool.OPENSM_PATH

        if is_running:
            running_path = OpenSmTool.get_running_opensm_path(engines)
            if running_path is None or running_path == desired_path:
                logging.info(f"OpenSM already running (path: {running_path})")
                return ResultObj(True, "OpenSM is already running")
            # Wrong version - restart
            logging.warning(f"Wrong OpenSM version ({running_path}), restarting with {desired_path}")
            OpenSmTool.stop_open_sm_on_server(engines)
            time.sleep(2)
        else:
            OpenSmTool.stop_open_sm_on_server(engines)

        with allure.step("Get GUID to start OpenSM"):
            output = engines.hfnm.run_cmd("ibdev2netdev")
            if "No space left on device" in output:
                logger.info("Attempting to clean up opensm.log files to free space...")
                engines.hfnm.run_cmd("rm -f /var/log/opensm.log*")
                logger.info("Retrying ibdev2netdev...")
                output = engines.hfnm.run_cmd("ibdev2netdev")

                if "No space left on device" in output:
                    return ResultObj(False, "Failed to cleanup opensm logs")

            if multiplanar:
                # CX8 needs to see the planarized interface
                output = engines.hfnm.run_cmd("ibdev2netdev")
                if "smi2" not in output:
                    engines.hfnm.run_cmd(
                        f"/opt/mellanox/iproute2/sbin/rdma dev add smi2 type SMI parent {port_name}")

            logging.info(f"Using opensm path: {desired_path}")

            output = engines.hfnm.run_cmd("ibstat {}".format(port_name))
            guid = ''
            for line in output.splitlines():
                if "System image GUID" in line:
                    guid = line.split(":")[1]
                    logging.info("GUID: " + guid)
                    break
            if not guid:
                return ResultObj(False, "Failed to find GUID to start OpenSM")

        with allure.step("Start OpenSM"):
            engines.hfnm.run_cmd(f"{desired_path} -F {OPEN_SM_CFG_PATH} -g {guid} -B")
            time.sleep(5)

        with allure.step("Verify OpenSM is running"):
            return ResultObj(OpenSmTool.verify_open_sm_is_running_on_server(engines), "Failed to start OpenSM")

    @staticmethod
    def stop_open_sm_on_server(engines):
        try:
            if not hasattr(engines, "hfnm"):
                logging.warning(MISSING_HFNM_MESSAGE)
                return ResultObj(False, MISSING_HFNM_MESSAGE)

            OpenSmTool.stop_open_sm_process_on_engine(engines.hfnm)
            return ResultObj(True, "OpenSM stopped successfully")

        except BaseException as ex:
            logging.error(f"Failed to stop opensm: {ex}")
            return ResultObj(False, f"Failed to stop opensm: {ex}")

    @staticmethod
    def stop_open_sm_on_non_fnm_hosts(engines, hosts_nicknames):
        """
        go over each host nickname - aka ha, hb and so on and kill openSM if its active on it
        """
        try:
            for host_nickname in hosts_nicknames:
                if not hasattr(engines, host_nickname):
                    logging.warning(MISSING_HOST.format(host_nickname))
                    return ResultObj(False, MISSING_HOST.format(host_nickname))

                host_engine = getattr(engines, host_nickname)
                OpenSmTool.stop_open_sm_process_on_engine(host_engine)

        except BaseException as ex:
            logging.error(f"Failed to stop opensm with error: {ex}")
            return False, 0
        return ResultObj(True)

    @staticmethod
    def stop_open_sm_process_on_engine(engine):
        """Stop openSM process on given host engine if running."""
        with allure.step(f"Stop opensm on {engine.ip}"):
            output = engine.run_cmd(GET_OPENSM_CMD)
            lines = OpenSmTool._get_opensm_process_lines(output)
            if not lines:
                logging.info(f"No opensm processes on {engine.ip}")
                return

            pids = [line.split()[1] for line in lines if len(line.split()) >= 2]
            if pids:
                engine.run_cmd("sudo kill -9 " + " ".join(pids))
                logging.info(f"Killed SM processes {pids} on {engine.ip}")

    @staticmethod
    def is_sm_running_on_server(engines, host_nickname=None):
        """
        check on fnm host if it runs openSM
        @param host_nickname - allows to override fnm host with another, for example 'ha' nickname
        """
        host_nickname = IbConsts.HFNM if not host_nickname else host_nickname
        with allure.step("Check if OpenSM is running on a server"):
            # check if open sm process is currently running
            output = engines[host_nickname].run_cmd(GET_OPENSM_CMD)
            lines = OpenSmTool._get_opensm_process_lines(output)

            # check if port is up
            output = engines[host_nickname].run_cmd("ibdev2netdev")
            is_up = "(Up)" in output
            port_name = output.split()[0]

            # return OpenSM is running only if open sm process is running and port is up
            is_running = bool(lines) and is_up

            return is_running, port_name

    @staticmethod
    def get_running_opensm_path(engines, host_nickname=None):
        """Detect which OpenSM binary is currently running."""
        host_nickname = IbConsts.HFNM if not host_nickname else host_nickname
        if not hasattr(engines, host_nickname):
            return None

        output = engines[host_nickname].run_cmd(GET_OPENSM_CMD)
        lines = OpenSmTool._get_opensm_process_lines(output)
        if not lines:
            return None

        # Check for known paths, otherwise assume DOCA (no path prefix)
        for path in [SM_MASTER_OPEN_SM_PATH, OPEN_SM_PATH]:
            if path in output:
                return path
        return DOCA_OPEN_SM_PATH

    @staticmethod
    def verify_open_sm_is_running_on_server(engines, host_nickname=None):
        """
        @param host_nickname - allows to override fnm host with another, for example 'ha' nickname
        """
        is_running, port_name = OpenSmTool.is_sm_running_on_server(engines, host_nickname)
        return is_running

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

OPEN_SM_PATH = "opensm"
OPEN_SM_CFG_PATH = "/auto/sw_system_project/NVOS_INFRA/verification/issu/opensm.cfg"
MISSING_HFNM_MESSAGE = "HA and HFNM can't be found in topology"


class OpenSmTool:

    @staticmethod
    def start_open_sm(engines=None, multiplanar=False):
        return OpenSmTool.start_open_sm_on_server(engines, multiplanar)

    @staticmethod
    def stop_open_sm(engines=None):
        return OpenSmTool.stop_open_sm_on_server(engines)

    @staticmethod
    def start_open_sm_on_server(engines, multiplanar=False):
        """
        Start open sm if it's not running
        """
        if not hasattr(engines, "hfnm"):
            logging.warning(MISSING_HFNM_MESSAGE)
            return ResultObj(False, MISSING_HFNM_MESSAGE)

        is_running, port_name = OpenSmTool.is_sm_running_on_server(engines)

        if is_running:
            logging.info("Open SM is already running")
            return ResultObj(True, "Open SM is already running")
        else:
            OpenSmTool.stop_open_sm_on_server(engines)

        with allure.step("Get GUID to start OpenSM"):
            if multiplanar:
                # CX8 needs to see the planarized interface
                output = engines.hfnm.run_cmd("ibdev2netdev")
                if "smi2" not in output:
                    engines.hfnm.run_cmd(f"/opt/mellanox/iproute2/sbin/rdma dev add smi2 type SMI parent {port_name}")
                opensm_path = '/opt/ufm/opensm/sbin/opensm'
            else:
                opensm_path = '/labhome/juliav/workspace/sm_regression/sources/SM_MASTER/usr/sbin/opensm'
            output = engines.hfnm.run_cmd("ibstat {}".format(port_name))
            guid = ''
            for line in output.splitlines():
                if "System image GUID" in line:
                    guid = line.split(":")[1]
                    logging.info("GUID: " + guid)
                    break
            if not guid:
                return ResultObj(False, "Failed to find GUID to start OpenSM")

        with (allure.step("Start OpenSM")):
            # todo: remove when we get opensm 5.22 or later
            engines.hfnm.run_cmd(f"{opensm_path} -F {OPEN_SM_CFG_PATH} -g {guid} -B")
            time.sleep(5)

        with allure.step("Verify OpenSM is running"):
            return ResultObj(OpenSmTool.verify_open_sm_is_running_on_server(engines), "Failed to start OpenSM")

    @staticmethod
    def stop_open_sm_on_server(engines):
        try:
            if not hasattr(engines, "hfnm"):
                logging.warning(MISSING_HFNM_MESSAGE)
                return ResultObj(False, MISSING_HFNM_MESSAGE)

            with allure.step("Get opensm process ids to stop"):
                output = engines.hfnm.run_cmd(f"ps aux | grep opensm")
                lines = [line for line in output.split('\n') if 'grep' not in line]
                if not lines:
                    return ResultObj(True, "No opensm processes")

            with allure.step("Stop open sm process"):
                process_ids = [line.split()[1] for line in lines]
                cmd = "sudo kill -9"
                for process_id in process_ids:
                    cmd += f" {process_id}"
                output = engines.hfnm.run_cmd(cmd)
                return ResultObj(True, info=output)
        except BaseException as ex:
            logging.error("Failed to stop opensm")
            return False, 0

    @staticmethod
    def is_sm_running_on_server(engines):
        with allure.step("Check if OpenSM is running on a server"):
            # check if open sm process is currently running
            output = engines.hfnm.run_cmd(f"ps aux | grep opensm")
            lines = [line for line in output.split('\n') if 'grep' not in line]

            # check if port is up
            output = engines.hfnm.run_cmd("ibdev2netdev")
            is_up = "(Up)" in output
            port_name = output.split()[0]

            # return OpenSM is running only if open sm process is running and port is up
            is_running = bool(lines) and is_up

            return is_running, port_name

    @staticmethod
    def verify_open_sm_is_running_on_server(engines):
        is_running, port_name = OpenSmTool.is_sm_running_on_server(engines)
        return is_running

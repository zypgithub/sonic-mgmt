import pytest
import time
import logging
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_constants.constants_nvos import IbConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.ResultObj import ResultObj
from ngts.tools.test_utils import allure_utils as allure
from retry import retry

logger = logging.getLogger()

OPEN_SM_PATH = "opensm"


class OpenSmTool:

    @staticmethod
    def start_open_sm(engines=None):
        return OpenSmTool.start_open_sm_on_server(engines)

    @staticmethod
    def stop_open_sm(engines=None):
        return OpenSmTool.stop_open_sm_on_server(engines)

    @staticmethod
    def start_open_sm_on_server(engines):
        """
        Start open sm if it's not running
        """
        if not hasattr(engines, "ha"):
            logging.warning("HA can't be found in topology")
            return ResultObj(False, "HA can't be found in topology")

        is_running, port_name = OpenSmTool.is_sm_running_on_server(engines)

        if is_running:
            logging.info("Open SM is already running")
            return ResultObj(True, "Open SM is already running")
        else:
            OpenSmTool.stop_open_sm_on_server(engines)

        with allure.step("Get GUID to start OpenSM"):
            output = engines.ha.run_cmd("ibstat {}".format(port_name))
            guid = ''
            for line in output.splitlines():
                if "System image GUID" in line:
                    guid = line.split(":")[1]
                    logging.info("GUID: " + guid)
                    break
            if not guid:
                return ResultObj(False, "Failed to find GUID to start OpenSM")

        with allure.step("Start OpenSM"):
            engines.ha.run_cmd(f"{OPEN_SM_PATH} -g {guid} -B")
            time.sleep(5)

        with allure.step("Verify OpenSM is running"):
            return ResultObj(OpenSmTool.verify_open_sm_is_running_on_server(engines), "Failed to start OpenSM")

    @staticmethod
    def stop_open_sm_on_server(engines):
        try:
            if not hasattr(engines, "ha"):
                logging.warning("HA can't be found in topology")
                return ResultObj(False, "HA can't be found in topology")

            with allure.step("Get opensm process ids to stop"):
                output = engines.ha.run_cmd(f"ps aux | grep opensm")
                lines = [line for line in output.split('\n') if 'grep' not in line]
                if not lines:
                    return ResultObj(True, "No opensm processes")

            with allure.step("Stop open sm process"):
                process_ids = [line.split()[1] for line in lines]
                cmd = "sudo kill -9"
                for process_id in process_ids:
                    cmd += f" {process_id}"
                output = engines.ha.run_cmd(cmd)
                return ResultObj(True, info=output)
        except BaseException as ex:
            logging.error("Failed to stop opensm")
            return False, 0

    @staticmethod
    def is_sm_running_on_server(engines):
        with allure.step("Check if OpenSM is running on a server"):
            # check if open sm process is currently running
            output = engines.ha.run_cmd(f"ps aux | grep opensm")
            lines = [line for line in output.split('\n') if 'grep' not in line]

            # check if port is up
            output = engines.ha.run_cmd("ibdev2netdev")
            is_up = "(Up)" in output
            port_name = output.split()[0]

            # return OpenSM is running only if open sm process is running and port is up
            is_running = bool(lines) and is_up

            return is_running, port_name

    @staticmethod
    def verify_open_sm_is_running_on_server(engines):
        is_running, port_name = OpenSmTool.is_sm_running_on_server(engines)
        return is_running

import logging
from concurrent.futures import ThreadPoolExecutor
from infra.tools.validations.traffic_validations.ping.send import ping_till_alive
from ngts.tools.test_utils import allure_utils as allure
import shutil
import os


logger = logging.getLogger()


class DvsInstallationSteps:

    @staticmethod
    def pre_installation_steps(setup_info):
        pass

    @staticmethod
    def post_installation_steps(duts, sdk_version, deploy_sequential=False):
        """Install SDK and burn FW on each DUT."""
        def _sdk_fw_install_on_switch(dut):
            dut['cli_obj'].install_sdk_and_burn_fw_flow(sdk_version)

        if deploy_sequential:
            for dut in duts:
                logger.info(f"Installing SDK and FW on {dut['dut_name']}")
                _sdk_fw_install_on_switch(dut)
        else:
            names = ", ".join(d['dut_name'] for d in duts)
            logger.info(f"Installing SDK and FW in parallel on: {names}")
            with ThreadPoolExecutor(max_workers=len(duts)) as pool:
                list(pool.map(_sdk_fw_install_on_switch, duts))

import logging
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
    def post_installation_steps(duts, sdk_version):
        for dut in duts:
            # TODO: FW burn on prod switch isn't functional at the moment, need to find a WA
            cli_obj = dut['cli_obj']
            cli_obj.install_sdk_and_burn_fw_flow(sdk_version)

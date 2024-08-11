import logging
import re
from enum import Enum
from typing import Iterable, Dict

from ngts.tools.test_utils import allure_utils as allure
from .ResultObj import ResultObj, IssueType
from retry import retry

from ...nvos_constants.constants_nvos import NvosConst

logger = logging.getLogger()

PACKAGES_TO_STRESS_CPU_AND_MEMORY = ['stres-ng', 'bc']


class StressResourcesTool:

    @staticmethod
    def stress_cpu_and_memory(engines, core_number, cpu_load=95, vm=8, vm_bytes='75%', timeout='300s'):
        with allure.step("Checking if needed packages are installed"):
            packages_to_delete = []
            for package in PACKAGES_TO_STRESS_CPU_AND_MEMORY:
                output = engines.dut.run_cmd(f"dpkg-query -l {package}")
                if "no packages found" in output or output == "":
                    logger.info(f"Installing package {package}")
                    engines.dut.run_cmd(f"sudo apt-get install -y {package}")
                    packages_to_delete.append(package)
        with allure.step("Stress CPU and MEMORY utilization"):
            engines.dut.run_cmd(f"sudo stress-ng --cpu {core_number} --cpu-load {cpu_load} --vm {vm} --vm-bytes {vm_bytes} --timeout {timeout} --metrics-brief &")
        return packages_to_delete

    @staticmethod
    def delete_packages(engines, packages_to_delete):
        with allure.step("Delete packages that were installed during the test"):
            for package in packages_to_delete:
                output = engines.dut.run_cmd(f"sudo apt-get remove -y {package}")
                logger.info(output)

import logging
import os

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts


class NvuePerformanceCli:

    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        self.topology_obj = topology_obj
        self.engine = engine
        self.dut_alias = dut_alias
        self.cli_obj = cli_obj

    def apply_configuration_file(self, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR, dst_dir=PerfConsts.CL_HOME_DIR):
        src_file = self.get_configuration_file_path(scenario, template_suite)
        logging.info(f"Applying configuration file on {self.dut_alias}")
        self.engine.copy_file(source_file=src_file, file_system=dst_dir,
                              dest_file="tmp.yaml", overwrite_file=True, verify_file=False)
        logging.info(f"Configuration file was copied to {self.dut_alias}")
        full_path = os.path.join(dst_dir, "tmp.yaml")
        self.cli_obj.general.replace_config(self.engine, full_path, output_type="json")
        self.cli_obj.general.apply_config(self.engine, option="-y")
        logging.info(f"The configuration file on {self.dut_alias} was applied successfully")

    def get_configuration_file_path(self, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                 template_suite, scenario, "cumulus", f"{self.dut_alias}.yaml")
        logging.info("Full Path returned is {}".format(full_path))
        return full_path

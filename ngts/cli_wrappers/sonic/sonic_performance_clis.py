import logging
import os
import json
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure


class SonicPerformanceCli:
    """
    This class is for Performance cli commands for sonic only
    """

    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        self.topology_obj = topology_obj
        self.engine = engine
        self.dut_alias = dut_alias
        self.cli_obj = cli_obj

    def save_basic_configuration(self, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR, scenario='basic'):
        config_db_json = self.cli_obj.general.get_config_db()
        full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                 scenario, "sonic", f"{self.dut_alias}.json")
        with open(full_path, 'w') as f:
            json.dump(config_db_json, f)

    def apply_configuration_file(self, scenario, dst_dir="/tmp"):
        src_file = self.get_configuration_file_path(scenario)
        logging.info("Applying the configuration_file onto the dut after copying")
        self.engine.copy_file(source_file=src_file, file_system=dst_dir, dest_file="config.json",
                              overwrite_file=True, verify_file=False)
        full_path = os.path.join(dst_dir, "config.json")
        self.cli_obj.general.load_configuration(full_path)

    def get_configuration_file_path(self, scenario,
                                    template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests", template_suite,
                                 scenario, "sonic", f"{self.dut_alias}.json")
        logging.info("Full Path returned is {}".format(full_path))
        return full_path

from pprint import pprint
import tempfile
import yaml
from ngts.helpers.performance.traffic_helpers import convert_to_percentage
from ngts.cli_wrappers.common.trimming_clis_common import TrimmingCommon
import allure
import json
import logging
from infra.tools.exceptions.test_issue import TestIssue
from ngts.constants.performance_constants import Cl_Consts, ValidationConsts
import time
import os
from jinja2 import Environment, FileSystemLoader
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts


class NvueTrimmingCli(TrimmingCommon):

    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        super().__init__(topology_obj, engine, dut_alias, cli_obj)
        self.topology_obj = topology_obj
        self.engine = engine
        self.dut_alias = dut_alias
        self.cli_obj = cli_obj

    def configure_trimming_size(self, trimming_size):
        self.cli_obj.performance.execute_cmd(f"nv set system forwarding packet-trim size {trimming_size}")
        self.cli_obj.performance.execute_cmd(f"nv config apply -y")

    def get_trimming_counters(self):
        output_json = self.engine.run_cmd("nv sh system forwarding packet-trim -o json", print_output=False)
        output_dict = json.loads(output_json)
        trimming_counters = output_dict["session-info"]["trimmed-packet-counters"]
        return trimming_counters

    def clear_trimming_counters(self):
        self.engine.run_cmd("nv action clear system forwarding packet-trim counters")
        time.sleep(1)

    def validate_trimmed_untrimmed_dropped_percentages(self, interface_list, trimming_queue=[], drop_queues=[], violations_list=[], initial_trimming_counters=0, return_dict=False):
        with allure.step("Get trimming counters for all egress interfaces"):
            queue_counters = self.cli_obj.interface.get_interface_queue_counters(interface_list, counters_type="egress-queue-stats", sub_type=["tx-frames"])
            trimmed_packets = sum(queue_counters[interface][trimming_queue]["tx-frames"] for interface in interface_list)
            drop_counters = self.cli_obj.interface.get_interface_counters(interface_list, counters_type="tx-drop")
            try:
                total_drop_packets = sum(drop_counters.values())
            except ValueError:
                logging.error("Drop Counters are not available for all interfaces")
                logging.error(drop_counters)
                raise TestIssue(f"Error getting drop counters for {interface_list}")
            trimming_percentage = convert_to_percentage(trimmed_packets / total_drop_packets)
            dropped_without_trimming_percentage = convert_to_percentage((total_drop_packets - trimmed_packets) / total_drop_packets)
            if trimmed_packets == total_drop_packets:
                logging.info("All packets are dropped and trimmed")
                logging.info(f"Dropped packets: {total_drop_packets}")
            else:
                logging.error(f"Dropped packets: {total_drop_packets}")
                logging.error(f"Trimmed packets: {trimmed_packets}")
                logging.error(f"Dropped without trimming : {total_drop_packets - trimmed_packets}")
                logging.error(f"Trimmed percentage: {trimming_percentage}")
                logging.error(f"Dropped without trimming percentage: {dropped_without_trimming_percentage}")
                violations_list.append("Some packets are not dropped and trimmed")
            if return_dict:
                queue_packet_percentages_dict = {ValidationConsts.OS_PORT_NAME: ', '.join(interface_list),
                                                 ValidationConsts.TRIMMING_PERCENTAGE: trimming_percentage,
                                                 ValidationConsts.DROPPED_WITHOUT_TRIMMING_PERCENTAGE: dropped_without_trimming_percentage,
                                                 "Dropped packets": total_drop_packets,
                                                 "Trimmed packets": trimmed_packets}
                return queue_packet_percentages_dict
        return trimming_percentage

    def configure_trim_of_all_packets(self, ports, queues, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        self.cli_obj.general.detach_config(self.engine)
        templates_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                      template_suite, scenario, "cumulus_jinja")
        templateLoader = FileSystemLoader(searchpath=templates_path)
        templateEnv = Environment(loader=templateLoader)
        TEMPLATE_FILE = "trim_scheduler.jinja"
        jinja_template = templateEnv.get_template(TEMPLATE_FILE)
        parameter_dict = {
            "port_list": ports
        }
        outputText = jinja_template.render(parameter_dict=parameter_dict)
        try:
            yaml.safe_load(outputText)  # just for checking the YAML sanity
        except yaml.YAMLError as yex:
            logging.error(yex)
            logging.error(f"{self.dut_alias}'s Jinja file has resulted in incorrect YAML configuration :- \r\n{pprint.pformat(outputText, depth=12, width=128)}\r\n")
            raise
        fd, path = tempfile.mkstemp()
        with open(path, 'w') as f:
            f.write(outputText)
        self.engine.copy_file(source_file=path, file_system=Cl_Consts.CL_HOME_DIR,
                              dest_file="trim_scheduler.yaml", overwrite_file=True, verify_file=False)
        full_path = os.path.join(Cl_Consts.CL_HOME_DIR, "trim_scheduler.yaml")
        self.cli_obj.general.patch_config(self.engine, full_path)
        self.cli_obj.general.apply_config(self.engine, option="-y", verify_execution=True)

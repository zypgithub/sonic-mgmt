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
import pandas as pd
from infra.tools.redmine.redmine_api import is_redmine_issue_active


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

    def validate_trimmed_untrimmed_dropped_percentages(self, interface_list, trimming_queue, drop_queues, violations_list, return_dict=False, duration=None, pairing_df=None):
        queue_packet_percentages = []
        with allure.step(f"Validate all packets sent to queue {drop_queues} are dropped and trimmed on queue {trimming_queue} for all egress interfaces"):
            queue_counters = self.cli_obj.interface.get_interface_queue_counters(interface_list, counters_type="egress-queue-stats", sub_type=["tx-frames"])
            drop_counters = self.cli_obj.interface.get_interface_counters(interface_list, counters_type="tx-drop")

            for interface in interface_list:
                with allure.step(f"Validate all packets sent to queue {drop_queues} are dropped and trimmed on queue {trimming_queue} for {interface}"):
                    total_drop_packets, trimmed_packets, trimming_percentage, dropped_without_trimming_percentage, untrimmed_percentage, trimming_packets_per_second = self.get_trimming_counters_for_interface(interface, queue_counters, drop_counters, drop_queues, trimming_queue, duration)

                    queue_packet_percentages_dict = {
                        ValidationConsts.PORT: self.cli_obj.performance.get_sdk_port(interface),
                        ValidationConsts.OS_PORT_NAME: interface,
                        ValidationConsts.UNTRIMMED_PERCENTAGE: untrimmed_percentage,
                        ValidationConsts.TRIMMING_PERCENTAGE: trimming_percentage,
                        ValidationConsts.DROPPED_WITHOUT_TRIMMING_PERCENTAGE: dropped_without_trimming_percentage,
                        ValidationConsts.DROPPED_WITHOUT_TRIMMING: bool(total_drop_packets - trimmed_packets),
                        ValidationConsts.TRIMMING_PPS: trimming_packets_per_second
                    }
                    queue_packet_percentages.append(queue_packet_percentages_dict)

                    self.validate_trimming_counters(interface, total_drop_packets, trimmed_packets, violations_list)
                    if return_dict:
                        return queue_packet_percentages_dict

        queue_packet_percentages_df = self.attach_queue_packet_percentages_df(queue_packet_percentages, pairing_df)
        return queue_packet_percentages_df.to_dict(orient='records') if not queue_packet_percentages_df.empty else []

    def get_trimming_counters_for_interface(self, interface, queue_counters, drop_counters, drop_queues, trimming_queue, duration):
        total_untrimmed_packets = sum([queue_counters[interface][drop_queue]["tx-frames"] for drop_queue in drop_queues])
        trimmed_packets = queue_counters[interface][trimming_queue]["tx-frames"]
        total_drop_packets = drop_counters.get(interface, 0)
        total_egress_port_packets = total_untrimmed_packets + total_drop_packets

        if total_drop_packets == 0:
            trimming_percentage = 0
            dropped_without_trimming_percentage = 0
            untrimmed_percentage = 0
        else:
            trimming_percentage = convert_to_percentage(trimmed_packets / total_egress_port_packets)
            dropped_without_trimming = total_drop_packets - trimmed_packets
            dropped_without_trimming_percentage = convert_to_percentage(dropped_without_trimming / total_drop_packets)
            untrimmed_percentage = convert_to_percentage(total_untrimmed_packets / total_egress_port_packets)

        if duration and total_drop_packets > 0:
            trimming_packets_per_second = trimmed_packets / duration
        else:
            trimming_packets_per_second = 0

        return total_drop_packets, trimmed_packets, trimming_percentage, dropped_without_trimming_percentage, untrimmed_percentage, trimming_packets_per_second

    def validate_trimming_counters(self, interface, total_drop_packets, trimmed_packets, violations_list):
        if trimmed_packets != total_drop_packets and total_drop_packets > 0:
            if not is_redmine_issue_active([4702808])[0]:
                violations_list.append(f"Some packets are not dropped and trimmed on {interface}")

    def attach_queue_packet_percentages_df(self, queue_packet_percentages, pairing_df=None):
        queue_packet_percentages_df = pd.DataFrame(queue_packet_percentages)
        if not queue_packet_percentages_df.empty:
            average_row = queue_packet_percentages_df.mean(numeric_only=True)
            average_row[ValidationConsts.PORT] = "Average"
            average_row[ValidationConsts.OS_PORT_NAME] = "Average"
            average_row[ValidationConsts.DROPPED_WITHOUT_TRIMMING] = queue_packet_percentages_df[ValidationConsts.DROPPED_WITHOUT_TRIMMING].all()
            queue_packet_percentages_df = pd.concat([queue_packet_percentages_df, average_row.to_frame().T], ignore_index=True)

            if pairing_df is not None:
                queue_packet_percentages_df = pd.merge(queue_packet_percentages_df, pairing_df, on=ValidationConsts.OS_PORT_NAME, how='left')

            with allure.step(f"Attach queue_packet_percentages_df"):
                allure.attach(queue_packet_percentages_df.to_html(), "Queue packet percentages dataframe", attachment_type=allure.attachment_type.HTML)
        return queue_packet_percentages_df

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

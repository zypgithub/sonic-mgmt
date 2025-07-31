from ngts.helpers.performance.traffic_helpers import convert_to_percentage
from ngts.cli_wrappers.common.trimming_clis_common import TrimmingCommon
import allure
import json
import logging
from infra.tools.exceptions.test_issue import TestIssue
from ngts.constants.performance_constants import ValidationConsts
import time


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
            trimmed_packets = self.cli_obj.trimming.get_trimming_counters() - initial_trimming_counters
            drop_counters = self.cli_obj.interface.get_tx_drop_counters(interface_list)
            try:
                total_drop_packets = sum(drop_counters.values())
            except ValueError:
                logging.error("Drop Counters are not available for all interfaces")
                logging.error(drop_counters)
                raise TestIssue(f"Error getting drop counters for {interface_list}")
            if trimmed_packets == total_drop_packets:
                logging.info("All packets are dropped and trimmed")
                logging.info(f"Dropped packets: {total_drop_packets}")
            else:
                logging.error(f"Dropped packets: {total_drop_packets}")
                logging.error(f"Trimmed packets: {trimmed_packets}")
                logging.error(f"Dropped without trimming : {total_drop_packets - trimmed_packets}")
                violations_list.append("Some packets are not dropped and trimmed")
            trimming_percentage = convert_to_percentage(trimmed_packets / total_drop_packets)
            dropped_without_trimming_percentage = convert_to_percentage((total_drop_packets - trimmed_packets) / total_drop_packets)
            if return_dict:
                queue_packet_percentages_dict = {ValidationConsts.OS_PORT_NAME: interface_list,
                                                 ValidationConsts.TRIMMING_PERCENTAGE: trimming_percentage,
                                                 ValidationConsts.DROPPED_WITHOUT_TRIMMING_PERCENTAGE: dropped_without_trimming_percentage}
                return queue_packet_percentages_dict
        return trimming_percentage

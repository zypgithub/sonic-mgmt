import os
import json
import allure
import logging
import pandas as pd
from ngts.helpers.system_helpers import copy_files_to_syncd
from ngts.helpers.performance.traffic_helpers import convert_to_percentage
from ngts.constants.constants import BugHandlerConst, InfraConst
from ngts.constants.performance_constants import PerfConsts, MRCConsts, ValidationConsts
from ngts.cli_wrappers.common.trimming_clis_common import TrimmingCommon
from jinja2 import Environment, FileSystemLoader


class SonicTrimmingCli(TrimmingCommon):
    """
    This class is for trimming cli commands for sonic only
    """

    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        super().__init__(topology_obj, engine, dut_alias, cli_obj)
        self.topology_obj = topology_obj
        self.engine = engine
        self.dut_alias = dut_alias
        self.cli_obj = cli_obj

    def configure_trim_of_all_packets(self, ports, queues, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        """
        This function is used to manufacture the behaviour where all the packets are trimmed
        for selected ports and queue.
        This is done by configuring a custom zero scheduler and
        configure it to drop all the packets for selected queue on selected ports.
        :param ports: list of ports, i.e ['Ethernet111', 'Ethernet112']
        :param queues: list of queues, i.e [1, 2]
        :param scenario: scenario, i.e 'srv6'
        :param template_suite: path to the template suite, i.e 'ngts/performance_tests/srv6/sonic'
        """
        self.configure_zero_scheduler()
        for queue in queues:
            self.get_disable_queue_json(ports, queue, scenario, template_suite)
            self.execute_cmd("sonic-cfggen -w -j /tmp/disable_queue.json")

    def disable_packets_aging(self):
        """
        This function is used to disable the packets aging on the buffer, this along with
        the zero scheduler will drop all the packets on the selected queue on selected ports.
        results in all the packets being trimmed.
        """
        packets_aging_file_name = "packets_aging.py"
        copy_files_to_syncd(self.engine, [packets_aging_file_name], PerfConsts.CONFIG_FILES_DIR)
        self.configure_packets_aging(mode='disable')

    def configure_packets_aging(self, mode='enable'):
        docker_exec_syncd_cmd = InfraConst.DOCKER_EXEC_BASH_CMD.format(DOCKER=InfraConst.SYNCD_DOCKER)
        syncd_packets_aging_disable_cmd = f"{docker_exec_syncd_cmd} './packets_aging.py {mode}'"
        self.execute_cmd(syncd_packets_aging_disable_cmd)

    def get_disable_queue_json(self, ports, queue, scenario, template_suite):
        templates_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                      template_suite, scenario, "sonic")
        env = Environment(loader=FileSystemLoader(templates_path))
        template_name = "disable_queue.jinja"
        jinja_template = env.get_template(template_name)
        template_string = jinja_template.render(ports=ports, queue=queue)
        json_dict = json.loads(template_string)
        disable_queue_file_name = "disable_queue.json"
        full_path = os.path.join(PerfConsts.CONFIG_FILES_DIR, disable_queue_file_name)
        with open(full_path, 'w') as f:
            json.dump(json_dict, f)
        self.engine.copy_file(source_file=os.path.join(PerfConsts.CONFIG_FILES_DIR, disable_queue_file_name),
                              dest_file=disable_queue_file_name,
                              file_system='/tmp',
                              direction='put'
                              )

    def configure_zero_scheduler(self):
        zero_scheduler_file_name = "zero_scheduler.json"
        self.engine.copy_file(source_file=os.path.join(PerfConsts.CONFIG_FILES_DIR, zero_scheduler_file_name),
                              dest_file=zero_scheduler_file_name,
                              file_system='/tmp',
                              direction='put'
                              )
        self.execute_cmd("sonic-cfggen -w -j /tmp/zero_scheduler.json")

    def configure_custom_dwrr_weights(self):
        file_name = "configure_custom_dwrr_weights.json"
        full_path = os.path.join(PerfConsts.CONFIG_FILES_DIR, file_name)
        self.engine.copy_file(source_file=full_path, dest_file=file_name, file_system='/tmp', direction='put')
        self.execute_cmd(f"sonic-cfggen -w -j /tmp/{file_name}")

    def enable_trimming_on_lossy_queue(self):
        for queue_num in MRCConsts.TRIMMING_ELEGABLE_QUEUE_NUM:
            self.execute_cmd(f"sudo config mmu -p queue{queue_num}_uplink_lossy_profile -t on")
            self.execute_cmd(f"sudo config mmu -p queue{queue_num}_downlink_lossy_profile -t on")

    def configure_trimming_size(self, trimming_size):
        with allure.step(f"Configure trimming size to {trimming_size}"):
            self.execute_cmd(f"sudo config switch-trimming global --size {trimming_size} "
                             f"--dscp {MRCConsts.MRC_TRIMMED_DSCP} "
                             f"--queue {MRCConsts.MRC_TRIMMED_TC}")

    def validate_trimming_counters(self, interface_list, violations_list):
        """
        validate that trimming counters are set correctly for all interfaces
        :param interface_list: list of interfaces, i.e ['Ethernet111', 'Ethernet112']
        :param violations_list: list of violations
        """
        interfaces_with_dropped_trimming_counters = []
        for interface in interface_list:
            portstat_dict = self.cli_obj.interface.parse_port_portstat(interface, trim_flag=True)
            logging.info(f"portstat for {interface}:\n{portstat_dict}")
            portstat_trimmed_pkts, portstat_dropped_trimmed_pkts = self.get_trimming_portstat_counters(portstat_dict)
            if portstat_dropped_trimmed_pkts > 0:
                interfaces_with_dropped_trimming_counters.append(interface)
        if interfaces_with_dropped_trimming_counters:
            interfaces = ", ".join(interfaces_with_dropped_trimming_counters)
            violations_list.append(f"Dropped packets detected on interfaces: {interfaces}")

    def validate_trimmed_untrimmed_dropped_percentages(self, interface_list, trimming_queue, drop_queues, violations_list, return_dict=False, duration=None, pairing_df=None):
        """
        validate that packets sent to queue drop_queue which are dropped are trimmed on queue trimming_queue for all interfaces
        :param interface_list: list of interfaces, i.e ['Ethernet111', 'Ethernet112']
        :param trimming_queue: trimming queue, i.e 'UC4'
        :param drop_queues: drop queue, i.e 'UC1'
        """
        queue_packet_percentages = []
        with allure.step(f"Validate all packets sent to queue {drop_queues} are dropped and trimmed on queue {trimming_queue} for all egress interfaces"):
            for interface in interface_list:
                with allure.step(f"Validate all packets sent to queue {drop_queues} are dropped and trimmed on queue {trimming_queue} for {interface}"):
                    total_drop_queue_counter_pkts = 0
                    total_packets_egress_port = 0
                    total_packets_egress_port_dropped = 0
                    total_drop_queue_counter_pkts_bytes = 0
                    total_packets_egress_port_bytes = 0
                    total_packets_egress_port_dropped_bytes = 0
                    show_queue_counters_dict = self.cli_obj.interface.parse_show_queue_counters(interface)
                    logging.info(f"show queue counters for {interface}:\n{show_queue_counters_dict}")
                    for drop_queue in drop_queues:
                        total_drop_queue_counter_pkts, total_packets_egress_port_dropped, total_drop_queue_counter_pkts_bytes, total_packets_egress_port_dropped_bytes = self.update_queue_counters(show_queue_counters_dict, drop_queue,
                                                                                                                                                                                                    total_drop_queue_counter_pkts, total_packets_egress_port_dropped,
                                                                                                                                                                                                    total_drop_queue_counter_pkts_bytes, total_packets_egress_port_dropped_bytes)
                    total_packets_egress_port = total_drop_queue_counter_pkts + total_packets_egress_port_dropped
                    trimming_queue_counter_pkts, trimming_queue_drop_pkts = self.cli_obj.interface.get_counters_for_queue(show_queue_counters_dict, trimming_queue)
                    trimming_queue_counter_pkts_bytes, trimming_queue_drop_pkts_bytes = self.cli_obj.interface.get_counters_for_queue_bytes(show_queue_counters_dict, trimming_queue, MRCConsts.MRC_DATA_PACKET_SIZE)
                    total_packets_egress_port_bytes = total_drop_queue_counter_pkts_bytes + trimming_queue_counter_pkts_bytes
                    dropped_without_trimming = total_packets_egress_port_dropped - trimming_queue_counter_pkts
                    if dropped_without_trimming > 0:
                        dropped_without_trimming_percentage = convert_to_percentage(dropped_without_trimming / total_packets_egress_port)
                    else:
                        dropped_without_trimming_percentage = 0
                    untrimmed_percentage = convert_to_percentage(total_drop_queue_counter_pkts / total_packets_egress_port)
                    untrimmed_bytes_percentage = convert_to_percentage(total_drop_queue_counter_pkts_bytes / total_packets_egress_port_bytes)
                    trimming_percentage = convert_to_percentage(trimming_queue_counter_pkts / total_packets_egress_port)
                    trimming_bytes_percentage = convert_to_percentage(trimming_queue_counter_pkts_bytes / total_packets_egress_port_bytes)
                    if duration:
                        trimming_packets_per_second = trimming_queue_counter_pkts / duration
                    else:
                        trimming_packets_per_second = 0
                    queue_packet_percentages_dict = {ValidationConsts.PORT: self.cli_obj.performance.get_sdk_port(interface),
                                                     ValidationConsts.OS_PORT_NAME: interface,
                                                     ValidationConsts.OS_PORT_ALIAS: self.cli_obj.performance.sonic_ports_aliases_dict[interface],
                                                     ValidationConsts.UNTRIMMED_PERCENTAGE: untrimmed_percentage,
                                                     ValidationConsts.TRIMMING_PERCENTAGE: trimming_percentage,
                                                     ValidationConsts.DROPPED_WITHOUT_TRIMMING_PERCENTAGE: dropped_without_trimming_percentage,
                                                     ValidationConsts.DROPPED_WITHOUT_TRIMMING: bool(dropped_without_trimming),
                                                     ValidationConsts.UNTRIMMED_BYTES_PERCENTAGE: untrimmed_bytes_percentage,
                                                     ValidationConsts.TRIMMING_BYTES_PERCENTAGE: trimming_bytes_percentage,
                                                     ValidationConsts.TRIMMING_PPS: trimming_packets_per_second}
                    queue_packet_percentages.append(queue_packet_percentages_dict)
                    if trimming_queue_drop_pkts > 0:
                        violations_list.append(f"Dropped packets detected on Trimming queue {trimming_queue} for {interface}")
                    if dropped_without_trimming > 0:
                        violations_list.append(f"Dropped packets without trimming detected on {interface}")
                    if return_dict:
                        return queue_packet_percentages_dict
        queue_packet_percentages_df = pd.DataFrame(queue_packet_percentages)
        average_row = queue_packet_percentages_df.mean(numeric_only=True)
        average_row[ValidationConsts.PORT] = "Average"
        average_row[ValidationConsts.OS_PORT_NAME] = "Average"
        average_row[ValidationConsts.OS_PORT_ALIAS] = "Average"
        average_row[ValidationConsts.DROPPED_WITHOUT_TRIMMING] = queue_packet_percentages_df[ValidationConsts.DROPPED_WITHOUT_TRIMMING].all()
        queue_packet_percentages_df = pd.concat([queue_packet_percentages_df, average_row.to_frame().T], ignore_index=True)
        if pairing_df is not None:
            queue_packet_percentages_df = pd.merge(queue_packet_percentages_df, pairing_df, on=ValidationConsts.OS_PORT_NAME, how='left')

        with allure.step(f"Attach queue_packet_percentages_df"):
            allure.attach(queue_packet_percentages_df.to_html(), "Queue packet percentages dataframe", attachment_type=allure.attachment_type.HTML)
        return queue_packet_percentages_df.to_dict(orient='records')

    def update_queue_counters(self, show_queue_counters_dict, queue,
                              queue_pkts_counter, queue_drop_pkts_counter,
                              queue_pkts_bytes_counter, queue_dropped_bytes_counter):
        queue_pkts, queue_drop = self.cli_obj.interface.get_counters_for_queue(show_queue_counters_dict, queue)
        queue_bytes, queue_drop_bytes = self.cli_obj.interface.get_counters_for_queue_bytes(show_queue_counters_dict, queue, MRCConsts.MRC_DATA_PACKET_SIZE)
        queue_pkts_counter += queue_pkts
        queue_drop_pkts_counter += queue_drop
        queue_pkts_bytes_counter += queue_bytes
        queue_dropped_bytes_counter += queue_drop_bytes
        return queue_pkts_counter, queue_drop_pkts_counter, queue_pkts_bytes_counter, queue_dropped_bytes_counter

    def validate_no_dropped_packets_on_queue(self, interface_list, queue_list, violations_list):
        for interface in interface_list:
            with allure.step(f"Validate no dropped packets on queues {queue_list} for {interface}"):
                show_queue_counters_dict = self.cli_obj.interface.parse_show_queue_counters(interface)
                logging.info(f"show queue counters for {interface}:\n{show_queue_counters_dict}")
                for queue in queue_list:
                    queue_counter_pkts, queue_drop_pkts = self.cli_obj.interface.get_counters_for_queue(show_queue_counters_dict, queue)
                    if queue_drop_pkts > 0:
                        violations_list.append(f"Dropped packets on {interface} queue {queue}")

    def get_queue_packet_percentages(self, interface_list, queues_list):
        queue_packet_percentages = {}
        for interface in interface_list:
            total_queue_counter_pkts = 0
            show_queue_counters_dict = self.cli_obj.interface.parse_show_queue_counters(interface)
            logging.info(f"show queue counters for {interface}:\n{show_queue_counters_dict}")
            for queue in queues_list:
                queue_counter_pkts, queue_counter_drop_pkts = self.cli_obj.interface.get_counters_for_queue(show_queue_counters_dict, queue)
                total_queue_counter_pkts += queue_counter_pkts
            for queue in queues_list:
                queue_counter_pkts, queue_counter_drop_pkts = self.cli_obj.interface.get_counters_for_queue(show_queue_counters_dict, queue)
                queue_packet_percentage = round(queue_counter_pkts / total_queue_counter_pkts, 2)
                queue_packet_percentages[f"Queue{queue}"] = queue_packet_percentage
        return queue_packet_percentages

    def config_optimal_trimming_size(self, chip_type):
        if chip_type == "SPC5":
            opt_ts = os.environ.get("OPT_TS", default=MRCConsts.OPT_TS_DEFAULT)
            self.cli_obj.trimming.enable_trimming_on_lossy_queue()
            self.cli_obj.trimming.configure_trimming_size(opt_ts)
            self.enable_trimming_counterpoll()

    def enable_trimming_counterpoll(self):
        for entity in MRCConsts.TRIMMING_COUNTERPOLL_LIST:
            self.cli_obj.counterpoll.enable_counterpoll(entity)
            self.cli_obj.counterpoll.set_counterpoll_interval(entity, MRCConsts.TRIMMING_COUNTERPOLL_INTERVAL)

    def get_trimming_portstat_counters(self, portstat_dict):
        portstat_trimmed_pkts = int(portstat_dict["TRIM_TX_PKTS"].replace(",", ""))
        portstat_dropped_trimmed_pkts = int(portstat_dict["TRIM_DRP_PKTS"].replace(",", ""))
        return portstat_trimmed_pkts, portstat_dropped_trimmed_pkts

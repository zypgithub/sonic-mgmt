import logging
import os
import json
from ngts.constants.performance_constants import PerfConsts
from infra.tools.exceptions.test_issue import TestIssue
from ngts.cli_wrappers.common.performance_clis_common import PerformanceCommon


class TrimmingCommon(PerformanceCommon):
    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        self.topology_obj = topology_obj
        self.engine = engine
        self.dut_alias = dut_alias
        self.cli_obj = cli_obj

    def clear_trimming_counters(self):
        """
        Clear trimming counters
        """
        pass

    def enable_disable_packet_trim(self, enable=True):
        """
        This method is used to enable the packet trim on the dut
        Implemented for Cumulus only
        """
        pass

    def validate_trimmed_untrimmed_dropped_percentages(self, interface_list, trimming_queue, drop_queues, violations_list, return_dict=False):
        """
        This method is used to validate the trimmed and untrimmed dropped percentages on the dut
        :param interface_list: list of interfaces, i.e ['Ethernet111', 'Ethernet112']
        :param trimming_queue: trimming queue, i.e 'TC4'
        :param drop_queues: drop queue, i.e 'TC1'
        :param violations_list: list of violations
        :param return_dict: return a dict of the queue packet percentages
        Implemented for Sonic and Cumulus only
        """
        pass

    def config_optimal_trimming_size(self, chip_type):
        '''
        This method is used to configure the optimal trimming size on the dut
        Implemented for Sonic only
        '''
        pass

    def configure_trim_of_all_packets(self, ports, queues, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        """
        Configure trimming of all packets on the selected ports and queues.
        """
        pass

    def disable_packets_aging(self):
        """
        Disable packets aging on the selected ports.
        """
        pass

    def configure_packets_aging(self, mode='enable'):
        """
        Configure packets aging on the selected ports.
        """
        pass

    def configure_zero_scheduler(self):
        """
        Configure zero scheduler on the selected ports.
        """
        pass

    def configure_custom_dwrr_weights(self):
        """
        Configure custom DWRR weights on the selected ports.
        """
        pass

    def enable_trimming_on_lossy_queue(self):
        """
        Enable trimming on the lossy queue on the selected ports.
        """
        pass

    def validate_trimming_counters(self, interface_list, violations_list):
        """
        Validate trimming counters on the selected ports.
        """
        pass

#!/usr/bin/env python3

import os
import sys
import json
import numpy as np
import pandas as pd
import time
import threading
from collections import defaultdict
import matplotlib.pyplot as plt

LIB_ROOT = os.path.join(os.path.abspath(__file__)[:os.path.abspath(__file__)
                        .find('sx_sdk_py_tests')]) + 'sx_sdk_py_tests'
if LIB_ROOT not in sys.path:
    sys.path.append(LIB_ROOT)

from python_sdk_api.sx_api import *
from python_sdk_api.sxd_api import *
from libs.utils.basic_test import PLATFORM, RUN_SUITE
import libs.python_wrappers.cos.shared_buffer_wrappers as sb_lib
import libs.python_wrappers.port.port_wrappers as port_lib
import libs.python_wrappers.tele.tele_wrappers as tele_lib
from libs.performance_infra.python_ixia_wrapper import retry
import libs.python_wrappers.bulk_counter.bulk_counter_wrappers as bulk_counter_lib
import libs.utils.test_infra_trap as trap_lib
from libs.base_classes.multi_nos.multi_nos_basic_test import MultiNosTest, PACKET_SIZE
from libs.base_classes.multi_nos.multi_os_constants import MultiNosConstants
from libs.base_classes.multi_nos.power_temp_constants import PowerTempConsts
import libs.common.test_decorators as td
from libs.multi_nos_lib.multi_nos_helpers import create_new_json_file
from libs.multi_nos_lib.power_temp_helpers import get_sensors_data, get_temperature_data
import libs.utils.test_infra_common as common_lib

# pylint: disable=too-many-positional-arguments


class TrafficValidator(MultiNosTest):
    """
    Traffic validator for multi NOS tests. This validator runs while there is traffic on the setup,
    and samples all desired parameters.

    Available validation factors:
        1)  print AVG, MIN and MAX BW
        2)  AVG OCC, 99% OCC, MAX OCC, MAX watermark
    """

    run_suite = RUN_SUITE.MULTI_NOS_PERFORMANCE

    def __init__(self):
        super().__init__()
        self.trap_thread_pool = None
        self.validator_json_obj = {}
        self.validator_json_path = "/tmp/TrafficValidator.json"
        self.connected_ports = []
        self.unconnected_ports = []
        self.speed = None

    def collect_sensors(self):
        self.logger.debug("Getting sensors data")
        sensors_dict = get_sensors_data()
        return sensors_dict

    def collect_temperature(self):
        self.logger.debug("Getting temperature data")
        temperature_dict = get_temperature_data()
        return temperature_dict

    def set_tc_latency_histogram(self, port, tc):
        hist_type = SX_TELE_HISTOGRAM_TYPE_PORT_TC_LATENCY_E
        queue_histogram = tele_lib.TeleQueueDepthHistogram(hist_type=hist_type, port=port, port_tc=tc, sample_time_resolution=self.new_sample_time, min_boundary=self.new_min_boundary, bin_size_resolution=self.new_bin_size, mode=SX_TELE_HISTOGRAM_MODE_LINEAR_E)
        tele_lib.tele_histogram_set(self.handle, SX_ACCESS_CMD_SET, queue_histogram)
        tele_lib.tele_histogram_data_get(self.handle, port, tc, hist_type, clear=True)
        # to avoid garbage in the histogram so the next sample will be accurate
        common_lib.sleep(0.1)  # to get accurate results, sample over 100 msec
        return queue_histogram

    def collect_latency(self):
        """
        This function collects the latency data for all the ports in the port group.
        It returns a dictionary with the latency data for each port group.
        The latency data is a list of dictionaries, each containing the statistics for a traffic class, i.e. [
            {
                "tc": 0,
                "latency_avg": 11,
                "latency_99": 22,
                "latency_max": 22
            },
            ...
        ]
        """
        self.logger.debug("Getting latency data")
        latency_dict = {}
        for port_group_name, port_group in self.port_groups.items():
            tc_latency_stats = {tc: [] for tc in range(MultiNosConstants.TC_NUM)}
            tc_latency_df = []
            for port in port_group:
                for tc in range(MultiNosConstants.TC_NUM):
                    queue_histogram = self.set_tc_latency_histogram(port, tc)
                    tc_latency_histogram, _ = tele_lib.tele_histogram_data_get(self.handle, port, tc, SX_TELE_HISTOGRAM_TYPE_PORT_TC_LATENCY_E)
                    tele_histogram = tele_lib.tele_histogram_get(self.handle, port, tc, SX_TELE_HISTOGRAM_TYPE_PORT_TC_LATENCY_E)
                    bins_range = tele_lib.tele_bins_range_get(SX_TELE_HISTOGRAM_TYPE_PORT_TC_LATENCY_E, tele_histogram.mode, tele_histogram.min_boundary, tele_histogram.bin_size_resolution)
                    tc_latency_stats[tc].append(self.get_latency_mean(tc_latency_histogram, bins_range))
                    tele_lib.tele_histogram_set(self.handle, SX_ACCESS_CMD_DESTROY, queue_histogram)
            for tc in range(MultiNosConstants.TC_NUM):
                np_arr_tc_latency_stats = np.array(tc_latency_stats[tc])
                tc_latency_avg = float(np.mean(np_arr_tc_latency_stats))
                tc_latency_99 = float(np.percentile(np_arr_tc_latency_stats, 99))
                tc_latency_max = int(np.max(np_arr_tc_latency_stats))
                self.logger.info(f'Port group: {port_group_name}.')
                self.logger.info(f'TC {tc} Latency average  is: {tc_latency_avg}')
                self.logger.info(f'TC {tc} Latency 99% is: {tc_latency_99}')
                self.logger.info(f'TC {tc} Latency max is: {tc_latency_max}\n\n')
                tc_latency_df.append({
                    MultiNosConstants.TC: tc,
                    MultiNosConstants.TC_AVG_LATENCY: tc_latency_avg,
                    MultiNosConstants.TC_99_LATENCY: tc_latency_99,
                    MultiNosConstants.TC_MAX_LATENCY: tc_latency_max
                })
            latency_dict[port_group_name] = {
                MultiNosConstants.TC_LATENCY_DATAFRAME: tc_latency_df
            }
        return latency_dict

    def get_latency_mean(self, tc_latency_histogram, bins_range):
        """
        This function calculates the latency for a given tc_latency_histogram and bins_range.
        Args:
            tc_latency_histogram: The histogram data for the tc latency.i.e, [0, 0, 0, 0, 121519027, 86173468, 0, 0, 0, 0]
            each histogram bin is a packet count in the bin. i.e, 121519027 packets in the bin 4,
            represents the number of packets that were received in the latency range of the bin.
            bins_range: The range of the bins. i.e. OrderedDict([('0', [0, 63]), ('1', [64, 127.0]), ...])
            the bin range is the latency range of the bin. i.e, bin 1 is [64, 127.0] microseconds.

        Returns:
            The latency mean per port per tc.
        """
        packets_count = sum(tc_latency_histogram)
        latency_sum = 0
        latency_mean = 0
        for idx, packet_num_in_bin in enumerate(tc_latency_histogram):
            bin_min = bins_range[str(idx)][0]
            bin_max = bins_range[str(idx)][1]
            bin_range = bin_max - bin_min
            mid_point = bin_min + bin_range / 2
            latency_sum += packet_num_in_bin * mid_point
        if packets_count > 0:
            latency_mean = latency_sum / packets_count
        return latency_mean

    def collect_bw(self):
        """
        Print average, maximum, and minimum bandwidth measurements, with corresponding ports.
        bw_dict will contain values for each port group separately.
        """
        self.logger.debug("Getting bandwidth measurements")

        bw_dict = {}
        for port_group_name, port_group in self.port_groups.items():
            bw_df = []
            for port in port_group:
                port_bw = port_lib.get_ports_bandwidth(self.handle, port)[port]
                port_bw_dict = {MultiNosConstants.PORT: hex(port),
                                MultiNosConstants.TX_RATE: port_bw["tx_rate"] / self.speed,
                                MultiNosConstants.RX_RATE: port_bw["rx_rate"] / self.speed}
                bw_df.append(port_bw_dict)

            self.logger.debug('Calculate average')
            bw_dataframe = pd.DataFrame(bw_df)
            avg_tx_bw = bw_dataframe[MultiNosConstants.TX_RATE].mean()
            avg_rx_bw = bw_dataframe[MultiNosConstants.RX_RATE].mean()

            self.logger.debug('Calculate min and max BW')
            tx_min_port, tx_min_bw, _ = bw_dataframe.loc[bw_dataframe[MultiNosConstants.TX_RATE].idxmin()]
            tx_max_port, tx_max_bw, _ = bw_dataframe.loc[bw_dataframe[MultiNosConstants.TX_RATE].idxmax()]
            rx_min_port, _, rx_min_bw = bw_dataframe.loc[bw_dataframe[MultiNosConstants.RX_RATE].idxmin()]
            rx_max_port, _, rx_max_bw = bw_dataframe.loc[bw_dataframe[MultiNosConstants.RX_RATE].idxmax()]

            group_stats = {
                MultiNosConstants.TX_MIN_BW_PERCENTAGE: tx_min_bw,
                MultiNosConstants.TX_MIN_BW_PORT: tx_min_port,
                MultiNosConstants.TX_MAX_BW_PERCENTAGE: tx_max_bw,
                MultiNosConstants.TX_MAX_BW_PORT: tx_max_port,
                MultiNosConstants.TX_BW_DIFF: tx_max_bw - tx_min_bw,
                MultiNosConstants.TX_BW_AVG: avg_tx_bw,
                MultiNosConstants.RX_BW_AVG: avg_rx_bw,
                MultiNosConstants.RX_MIN_BW_PERCENTAGE: rx_min_bw,
                MultiNosConstants.RX_MIN_BW_PORT: rx_min_port,
                MultiNosConstants.RX_MAX_BW_PERCENTAGE: rx_max_bw,
                MultiNosConstants.RX_MAX_BW_PORT: rx_max_port,
                MultiNosConstants.RX_BW_DIFF: rx_max_bw - rx_min_bw
            }

            self.logger.info(
                f"Port group: {port_group_name}. "
                f"Average tx_rate BW: {group_stats[MultiNosConstants.TX_BW_AVG]}. "
                f"Min: {tx_min_bw} (port {tx_min_port}). "
                f"Max: {tx_max_bw} (port {tx_max_port}). "
                f"Diff: {group_stats[MultiNosConstants.TX_BW_DIFF]}")

            bw_dict[port_group_name] = {
                MultiNosConstants.BW_STATS: group_stats,
                MultiNosConstants.BW_DATAFRAME: bw_df}
        return bw_dict

    def _set_hft_session(self, hft_counter_buffer):
        """
        This function starts the HFT bulk counter session and wait for the bulk counter (mocs) done event.

        Args:
            hft_counter_buffer: HFT counter buffer
        """
        # Create trap
        self.logger.debug('Configures the bulk trap channel')
        trap_group_hft = 10  # chosen arbitrary
        trap_id_list = [SX_TRAP_ID_BULK_COUNTER_DONE_EVENT]

        self.logger.debug('Set trap')
        trap_fd_hft, trap_group_hft = trap_lib.trap_rx_set(
            self.handle, trap_lib.TrapGroupAttr(trap_group=trap_group_hft, prio=1), trap_id_list, SX_TRAP_ACTION_TRAP_2_CPU
        )
        self.un(trap_lib.trap_close, (self.handle, trap_id_list, trap_fd_hft, trap_group_hft))
        self.trap_thread_pool.add_rcv_trap(trap_fd_hft)
        self.un(self.trap_thread_pool.del_rcv_trap, (trap_fd_hft,))

        self.logger.debug("Starting HFT session")
        bulk_counter_lib.bulk_counters_transaction_set(self.handle, hft_counter_buffer)

        # wait for mocs done event
        self.trap_thread_pool.trap_data_validate_bulk_counters(trap_fd_hft, [hft_counter_buffer], timeout=30)

    def start_hft_session(self, ports: list, counters: list, prio_list: list = None, tc_list: list = None,
                          pg_list: list = None,
                          sample_count: int = 1000, min_sample_interval: int = 0,
                          read_clear_buffer_watermark: bool = False):
        """
        This function configures and starts HFT session based on the given arguments.
        The function then returns a dictionary, with same keys as ports_list, and a list of all the measurements on those ports.

        Args:
            ports:                       list of ports
            counters:                    list of counters (HFT enumss)
            prio_list:                   list of prios (list of ints), by default, uses the default prio 0.
            tc_list:                     list of tcs (list of ints), by default, uses the default TC 0.
            pg_list:                     list of pgs (list of ints), by default, uses the default PG 0.
            sample_count:                the number of desired HFT samples
            min_sample_interval:         the minimum amount of time between the start of i sample to the start of the i+1
                                         sample. 0 -> start the i+1 sample right after the i sample has finished.
            read_clear_buffer_watermark: clear watermark counters

        Returns:
            A list of all HFT samples.
        """
        prio_list = prio_list or [0]
        tc_list = tc_list or [0]
        pg_list = pg_list or [0]

        self.logger.debug("Create HFT buffer")
        metadata_config = bulk_counter_lib.HftSampleMetadataConfig()
        port_counter_config = bulk_counter_lib.HftSamplePortCounterConfig(
            port_counter_list=counters, prio_id_list=prio_list, tc_id_list=tc_list, pg_id_list=pg_list,
            port_list=ports, read_clear_buffer_watermark=read_clear_buffer_watermark
        )
        global_counter_config = bulk_counter_lib.HftSampleGlobalCounterConfig()

        hft_key_dict = bulk_counter_lib.HFTKey(sample_count, min_sample_interval, metadata_config,
                                               port_counter_config, global_counter_config)
        counter_buffer = bulk_counter_lib.bulk_counters_buffer_create(self.handle, hft_key_dict,
                                                                      bulk_counter_lib.BULK_COUNTER_TYPE_HFT)
        self.un(bulk_counter_lib.bulk_counters_buffer_destroy, (self.handle, counter_buffer))

        self._set_hft_session(counter_buffer)
        time.sleep(10)
        return bulk_counter_lib.bulk_counters_transaction_get(self.handle, counter_buffer, cntr_key_dict=hft_key_dict,
                                                              counter_type=bulk_counter_lib.BULK_COUNTER_TYPE_HFT)

    def _rearrange_occ_results(self, sample_list, port_group, port_group_name):
        '''
        This is a helper function, in order to best show occupancy and watermark results
        Args:
            sample_list:            A list containing all of the occ and watermark measurements.
            tc:                     The traffic class to plot
        Returns:
            a list of dictionaries, each containing the statistics for a traffic class, i.e. [
                {
                    "tc": 0,
                    "occ_avg": 11,
                    "occ_99": 22,
                    "occ_max": 22,
                    "max_watermark": 22
                },
                ...
            ]
        '''
        tc_stats = {tc: [] for tc in range(MultiNosConstants.TC_NUM)}
        tc_watermark_stats = {tc: [] for tc in range(MultiNosConstants.TC_NUM)}
        pg_stats = {pg: [] for pg in range(MultiNosConstants.PG_NUM)}
        pg_watermark_stats = {pg: [] for pg in range(MultiNosConstants.PG_NUM)}
        for port in port_group:
            port_samples = []
            port_watermark_samples = []
            port_headroom_samples = []
            port_headroom_watermark_samples = []
            for sample in sample_list:
                port_data = sample.port_data[port]
                port_samples.append(port_data.tc_curr_occupancy_list)
                port_watermark_samples.append(port_data.tc_watermark_list)
                port_headroom_samples.append(port_data.headroom_curr_occupancy_list)
                port_headroom_watermark_samples.append(port_data.headroom_watermark_list)
            port_array = np.array(port_samples)
            port_watermark_array = np.array(port_watermark_samples)
            port_headroom_array = np.array(port_headroom_samples)
            port_headroom_watermark_array = np.array(port_headroom_watermark_samples)
            for tc in range(MultiNosConstants.TC_NUM):
                self.update_stats(tc, port_array, port_watermark_array, tc_stats, tc_watermark_stats)
            for pg in range(MultiNosConstants.PG_NUM):
                self.update_stats(pg, port_headroom_array, port_headroom_watermark_array, pg_stats, pg_watermark_stats)
        tc_df = []
        pg_df = []
        for tc in range(MultiNosConstants.TC_NUM):
            self.update_df(tc, tc_stats, tc_watermark_stats, tc_df, port_group_name, MultiNosConstants.TC)
        for pg in range(MultiNosConstants.PG_NUM):
            self.update_df(pg, pg_stats, pg_watermark_stats, pg_df, port_group_name, MultiNosConstants.PG)
        return tc_df, pg_df

    def update_stats(self, idx, port_array, port_watermark_array, stats, watermark_stats):
        port_data = port_array[:, idx]
        stats[idx].extend(port_data)
        port_watermark_data = port_watermark_array[:, idx]
        watermark_stats[idx].extend(port_watermark_data)

    def update_df(self, idx, stats, watermark_stats, df, port_group_name, data_type=MultiNosConstants.TC):
        occ_avg = float(np.mean(stats[idx]))
        occ_99 = float(np.percentile(stats[idx], 99))
        occ_max = int(np.max(stats[idx]))
        max_watermark = int(np.max(watermark_stats[idx]))
        self.logger.info(f'Port group: {port_group_name}.')
        self.logger.info(f'{data_type} {idx} Occupancy average  is: {occ_avg}')
        self.logger.info(f'{data_type} {idx} Occupancy 99% is: {occ_99}')
        self.logger.info(f'{data_type} {idx} Max occupancy is: {occ_max}')
        self.logger.info(f'{data_type} {idx} Max watermark is: {max_watermark}\n\n')
        df.append({

            data_type: idx,
            MultiNosConstants.OCC_AVG: occ_avg,
            MultiNosConstants.OCC_99: occ_99,
            MultiNosConstants.OCC_MAX: occ_max,
            MultiNosConstants.MAX_WATERMARK: max_watermark
        })
        return df

    def plot_occupancy_matrix(self, sample_list, tc):
        """
        This function plots the occupancy matrix for a given traffic class.
        Args:
            sample_list:            A list containing all of the occ and watermark measurements.
            tc:                     The traffic class to plot
        Returns:
            None, but plots the occupancy matrix for the given traffic class.
            it does so by grouping the ports into groups of 50, and plotting the occupancy matrix for each group.
            the plot is saved to a file, and the file name is the traffic class number and the group number.
        """
        occupancy_matrix = np.zeros((len(self.connected_ports), len(sample_list) + 1), dtype=object)

        for idx, port in enumerate(self.connected_ports):
            port_occ_samples = []
            for sample in sample_list:
                port_data = sample.port_data[port]
                port_occ_samples.append(port_data.tc_curr_occupancy_list[tc])
            # Assign the flattened list to the matrix row
            occupancy_matrix[idx, :-1] = port_occ_samples  # All columns except the last one
            occupancy_matrix[idx, -1] = hex(port)
        num_ports = occupancy_matrix.shape[0]
        ports_per_group = 50

        # Calculate number of groups needed
        num_groups = (num_ports + ports_per_group - 1) // ports_per_group  # Ceiling division

        for group_idx in range(num_groups):
            # Calculate start and end indices for this group
            start_port = group_idx * ports_per_group
            end_port = min((group_idx + 1) * ports_per_group, num_ports)

            # Create figure for this group of ports
            num_ports_in_group = end_port - start_port
            _, axes = plt.subplots(num_ports_in_group, 1, figsize=(12, 4 * num_ports_in_group))

            if num_ports_in_group == 1:
                axes = [axes]

            # Plot each port in the group
            for i, ax in enumerate(axes):
                port_idx = start_port + i
                port_id = occupancy_matrix[port_idx, -1]
                port_data = occupancy_matrix[port_idx, :-1]

                # Create time series plot
                ax.plot(port_data, '-', alpha=0.7)
                ax.set_title(f'Port {port_id} Occupancy Over Time for TC {tc}')
                ax.set_xlabel('Sample Number')
                ax.set_ylabel('Occupancy Value')

                # Add statistics
                stats_text = f'Mean: {np.mean(port_data):.2f}\n'
                stats_text += f'Max: {np.max(port_data):.2f}\n'
                stats_text += f'Min: {np.min(port_data):.2f}'
                ax.text(0.95, 0.95, stats_text,
                        transform=ax.transAxes,
                        verticalalignment='top',
                        horizontalalignment='right',
                        bbox={"boxstyle": 'round', "facecolor": 'white', "alpha": 0.8})

            plt.tight_layout()
            plt.savefig(f'port_occupancy_tc_{tc}_group_{group_idx}.png', dpi=100)
            plt.close()

    def collect_ports_tc_occ_and_watermark(self):
        """
        This function configures and starts HFT session, testing occupancy and watermark. The function then prints:
            1) AVG OCC
            2) 99% OCC
            3) MAX OCC
            4) MAX watermark

        """
        self.logger.debug('Clean buffer statistics for clean occupency and watermark')
        sb_lib.clear_all_ports_sb_statistics(self.handle, self.connected_ports)

        hft_occ_watermark_counters = [
            SX_BULK_CNTR_HFT_SAMPLE_COUNTER_EGRESS_PORT_TRAFFIC_CLASS_BUFFER_CURRENT_OCCUPANCY_E,
            SX_BULK_CNTR_HFT_SAMPLE_COUNTER_EGRESS_PORT_TRAFFIC_CLASS_BUFFER_WATERMARK_E,
            SX_BULK_CNTR_HFT_SAMPLE_COUNTER_INGRESS_PORT_PRIORITY_GROUP_HEADROOM_BUFFER_WATERMARK_E,
            SX_BULK_CNTR_HFT_SAMPLE_COUNTER_INGRESS_PORT_PRIORITY_GROUP_HEADROOM_BUFFER_CURRENT_OCCUPANCY_E]

        self.logger.debug('Starting HFT measurement')
        tc_pg_dict = {}
        for port_group_name, port_group in self.port_groups.items():
            sample_list = self.start_hft_session(port_group, counters=hft_occ_watermark_counters,
                                                 sample_count=1000, tc_list=list(range(MultiNosConstants.TC_NUM)),
                                                 pg_list=list(range(MultiNosConstants.PG_NUM)))
            self.logger.debug('Rearranging results for better readability')
            tc_df, pg_df = self._rearrange_occ_results(sample_list, port_group, port_group_name)
            tc_pg_dict[port_group_name] = {
                MultiNosConstants.TC_DATAFRAME: tc_df,
                MultiNosConstants.PG_DATAFRAME: pg_df
            }
        return tc_pg_dict

    def collect_port_custom_counters(self, port, port_counters_dict, clear_counters_value):
        counters = port_lib.port_counter_dict_discard_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict.update(counters)
        port_counters_dict.pop('ingress_general')

        counters = port_lib.port_counter_dict_ieee_802_dot_3_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict['a_alignment_errors'] = counters['a_alignment_errors']
        port_counters_dict['a_frame_check_sequence_errors'] = counters['a_frame_check_sequence_errors']
        port_counters_dict['a_frame_too_long_errors'] = counters['a_frame_too_long_errors']
        port_counters_dict['a_in_range_length_errors'] = counters['a_in_range_length_errors']
        port_counters_dict['a_symbol_error_during_carrier'] = counters['a_symbol_error_during_carrier']
        port_counters_dict['a_unsupported_opcodes_received'] = counters['a_unsupported_opcodes_received']
        port_counters_dict['a_in_range_length_errors'] = counters['a_in_range_length_errors']
        port_counters_dict['a_mac_control_frames_transmitted'] = counters['a_mac_control_frames_transmitted']
        port_counters_dict['a_mac_control_frames_received'] = counters['a_mac_control_frames_received']
        port_counters_dict['a_pause_mac_ctrl_frames_transmitted'] = counters['a_pause_mac_ctrl_frames_transmitted']
        port_counters_dict['a_pause_mac_ctrl_frames_received'] = counters['a_pause_mac_ctrl_frames_received']

        counters = port_lib.port_counter_dict_rfc_2863_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict['if_in_discards'] = counters['if_in_discards']
        port_counters_dict['if_in_errors'] = counters['if_in_errors']
        port_counters_dict['if_out_discards'] = counters['if_out_discards']
        port_counters_dict['if_out_errors'] = counters['if_out_errors']

        counters = port_lib.port_counter_dict_rfc_2819_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict['ether_stats_crc_align_errors'] = counters['ether_stats_crc_align_errors']
        port_counters_dict['ether_stats_drop_events'] = counters['ether_stats_drop_events']

        counters = port_lib.port_counter_dict_rfc_3635_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict['dot3stats_alignment_errors'] = counters['dot3stats_alignment_errors']
        port_counters_dict['dot3stats_carrier_sense_errors'] = counters['dot3stats_carrier_sense_errors']
        port_counters_dict['dot3stats_fcs_errors'] = counters['dot3stats_fcs_errors']
        port_counters_dict['dot3stats_frame_too_longs'] = counters['dot3stats_frame_too_longs']
        port_counters_dict['dot3stats_sqe_test_errors'] = counters['dot3stats_sqe_test_errors']
        port_counters_dict['dot3stats_symbol_errors'] = counters['dot3stats_symbol_errors']
        port_counters_dict['dot3stats_internal_mac_transmit_errors'] = counters['dot3stats_internal_mac_transmit_errors']
        port_counters_dict['dot3stats_internal_mac_receive_errors'] = counters['dot3stats_internal_mac_receive_errors']

        counters = port_lib.port_counter_dict_cli_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict['port_rx_fcs_errors'] = counters['port_rx_fcs_errors']
        port_counters_dict['port_rx_no_buffer'] = counters['port_rx_no_buffer']
        port_counters_dict['port_rx_other_errors'] = counters['port_rx_other_errors']
        port_counters_dict['port_tx_errors'] = counters['port_tx_errors']

        for tc in range(MultiNosConstants.TC_NUM):
            counters = port_lib.port_traffic_classes_counters_get(self.handle, port, tc, read_clear=clear_counters_value)
            port_counters_dict[f'tx_no_buffer_discard_uc_tc_{tc}'] = counters['tx_no_buffer_discard_uc']
            port_counters_dict[f'tx_wred_discard_tc_{tc}'] = counters['tx_wred_discard']
            port_counters_dict[f'tx_ecn_marked_tc_{tc}'] = counters['tx_ecn_marked_tc']

    def collect_port_counters(self):
        '''
        This function prints the sum of:
            1) All control packets (sent and received)
            2) All pause packets (sent and received)
        '''
        control_sent_counter = 0
        control_received_counter = 0
        pauses_sent_counter = 0
        pauses_received_counter = 0
        counters_dict = {}
        counter_list = [control_sent_counter, control_received_counter, pauses_sent_counter, pauses_received_counter]
        counter_names_list = MultiNosConstants.VALIDATOR_COUNTERS_LIST
        clear_counters_env_var_value = os.getenv(MultiNosConstants.CLEAR_COUNTERS_ENV_VAR, MultiNosConstants.CLEAR_COUNTERS_DEFAULT)
        clear_counters_value = clear_counters_env_var_value == 'True'
        self.logger.info(f'Clear counters value is: {clear_counters_value}')
        self.logger.debug('Iterate over all port control counters, and add to sum')
        for port_group_name, port_group in self.port_groups.items():
            counters_df = []
            for port in port_group:
                port_counters_dict = {MultiNosConstants.PORT: hex(port)}
                self.collect_port_custom_counters(port, port_counters_dict, clear_counters_value)
                for counter_value, counter_name in zip(counter_list, counter_names_list):
                    counter_value += port_counters_dict[counter_name]
                counters_df.append(port_counters_dict)
            counters_dict[port_group_name] = {MultiNosConstants.COUNTERS_DATAFRAME: counters_df}

            self.logger.info(f'print the sum of all port counters. Port group: {port_group_name}')
            for counter_name, counter_value in zip(counter_names_list, counter_list):
                self.logger.info(f'counter {counter_name}: {counter_value}\n')
        return counters_dict

    def load_port_group_from_config(self):
        """
        Load port group configuration from file or set default configuration.
        If configuration file exists, loads port groups and test scenario settings.
        Otherwise, splits connected ports into two groups (left and right).
        """
        if os.path.isfile(self.configuration_path):
            with open(self.configuration_path) as f:
                configuration = json.load(f)
            self.load_from_json(configuration)
            self.port_groups = {port_group_name: [int(port) for port in port_group]
                                for port_group_name, port_group in self.port_groups.items()}
        else:
            self.port_groups = {"left_ports": self.connected_ports[:len(self.connected_ports) // 2],
                                "right_Ports": self.connected_ports[len(self.connected_ports) // 2:]}

    def pre_test(self):
        super().pre_test()
        self.new_sample_time = 11
        self.new_min_boundary = 1
        self.new_bin_size = 0
        self.trap_thread_pool = trap_lib.TrapThreadPool(self.handle)
        if not os.path.isfile(self.ports_connectivity_path):
            self.get_connected_unconnected_ports()
        else:
            with open(self.ports_connectivity_path) as f:
                ports_connectivity_dict = json.load(f)
                self.connected_ports = ports_connectivity_dict["connected_ports"]
                self.unconnected_ports = ports_connectivity_dict["unconnected_ports"]
                self.speed = ports_connectivity_dict["speed"]

        self.load_port_group_from_config()
        if not tele_lib.is_tele_init():
            tele_lib.tele_init(self.handle)

    def post_test(self):
        super().post_test()
        if tele_lib.is_tele_init():
            tele_lib.tele_deinit(self.handle)

    def sample_collector(self, samples_name, collector, delay, sample_count, duration):
        sample_num = int(duration / delay) + 1
        start_time = time.time()
        all_sample_dict = {}
        for i in range(1, sample_num):
            current_time = time.time()
            elapsed_time = current_time - start_time
            if elapsed_time > duration:
                break
            sample_id = f"sample #{i} {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(current_time))}"
            sample_dict = collector()
            all_sample_dict[sample_id] = sample_dict
            time.sleep(delay)
        sample_params = {MultiNosConstants.SAMPLE_DURATION_PARAM: duration,
                         MultiNosConstants.DELAY_BETWEEN_SAMPLES_PARAM: delay,
                         MultiNosConstants.SAMPLE_RATE_PARAM: len(all_sample_dict.keys()) / duration * 60,
                         MultiNosConstants.SAMPLE_COUNT: sample_count}
        all_sample_dict[MultiNosConstants.SAMPLE_PARAMS] = sample_params
        self.validator_json_obj[samples_name] = all_sample_dict

    def test_command(self):
        duration = os.getenv(MultiNosConstants.SAMPLE_DURATION_ENV_VAR, str(MultiNosConstants.SAMPLE_DURATION_DEFAULT))
        bw_delay = os.getenv(MultiNosConstants.BW_SAMPLE_DELAY_ENV_VAR,
                             str(MultiNosConstants.BW_SAMPLE_DELAY_DEFAULT))
        tc_delay = os.getenv(MultiNosConstants.TC_SAMPLE_DELAY_ENV_VAR,
                             str(MultiNosConstants.TC_SAMPLE_DELAY_DEFAULT))
        counters_delay = os.getenv(MultiNosConstants.COUNTERS_SAMPLE_DELAY_ENV_VAR,
                                   str(MultiNosConstants.COUNTERS_SAMPLE_DELAY_DEFAULT))
        power_delay = os.getenv(PowerTempConsts.POWER_SAMPLE_DELAY_ENV_VAR,
                                str(PowerTempConsts.POWER_SAMPLE_DELAY_DEFAULT))
        temperature_delay = os.getenv(PowerTempConsts.TEMPERATURE_SAMPLE_DELAY_ENV_VAR,
                                      str(PowerTempConsts.TEMPERATURE_SAMPLE_DELAY_DEFAULT))
        collectors_info = [
            (MultiNosConstants.BW_SAMPLES, self.collect_bw, bw_delay, MultiNosConstants.BW_SAMPLE_COUNT),
            (MultiNosConstants.COUNTERS_SAMPLES, self.collect_port_counters,
             counters_delay, MultiNosConstants.COUNTERS_SAMPLE_COUNT),
            (PowerTempConsts.POWER_SAMPLES, self.collect_sensors,
             power_delay, PowerTempConsts.SENSORS_SAMPLE_COUNT),
            (PowerTempConsts.TEMPERATURE_SAMPLES, self.collect_temperature,
             temperature_delay, PowerTempConsts.TEMPERATURE_SAMPLE_COUNT)
        ]
        self.logger.info(f'speed is: {self.speed}')
        if self.speed < 800:
            collectors_info.append((MultiNosConstants.TC_PG_SAMPLES,
                                    self.collect_ports_tc_occ_and_watermark, tc_delay,
                                    MultiNosConstants.TC_PG_SAMPLE_COUNT))
            collectors_info.append((MultiNosConstants.TC_LATENCY_SAMPLES,
                                    self.collect_latency, tc_delay,
                                    MultiNosConstants.TC_LATENCY_SAMPLE_COUNT))
        threads = []
        for samples_name, collector, collector_delay, sample_count in collectors_info:
            threads.append(threading.Thread(target=self.sample_collector,
                                            args=(samples_name, collector,
                                                  int(collector_delay), sample_count, int(duration))))
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        create_new_json_file(json_obj=self.validator_json_obj, file_path=self.validator_json_path)


if __name__ == "__main__":
    test = TrafficValidator()
    test.execute_test()
    sys.exit(test.rc)

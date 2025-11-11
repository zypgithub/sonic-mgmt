#!/usr/bin/env python3

import os
import sys
import json
import time
import threading
import shutil

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
from libs.utils.sdk_exception import SdkException
from libs.base_classes.multi_nos.multi_nos_basic_test import MultiNosTest, PACKET_SIZE
from libs.base_classes.multi_nos.multi_os_constants import MultiNosConstants
from libs.base_classes.multi_nos.power_temp_constants import PowerTempConsts
import libs.common.test_decorators as td
from libs.multi_nos_lib.multi_nos_helpers import create_new_json_file
from libs.multi_nos_lib.power_temp_helpers import get_sensors_data, get_temperature_data
import libs.utils.test_infra_common as common_lib
import libs.python_wrappers.dbg.dbg_wrappers as dbg_lib

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

    def collect_sdk_dump(self):
        # pylint: disable=import-outside-toplevel
        # Used here to avoid import issues on OSes without this lib
        import pandas as pd
        dump_dir_with_perf_counters = "/tmp/dump_with_perf_counters/"
        dump_dir_without_perf_counters = "/tmp/dump_without_perf_counters/"
        self.logger.debug("Getting SDK dump")
        if not os.path.exists(dump_dir_with_perf_counters):
            os.makedirs(dump_dir_with_perf_counters)
        if not os.path.exists(dump_dir_without_perf_counters):
            os.makedirs(dump_dir_without_perf_counters)
        dump_modules_without_perf_counters = ((~SX_DBG_DUMP_MODULE_BIN_ALLOCATOR_E) & 0xFFFFFFFFFFFFFFFF) & ((~SX_DBG_DUMP_MODULE_PMC_E) & 0xFFFFFFFFFFFFFFFF)
        debug_dump_with_perf_counters_path, _, _, time_to_generate_dump_with_perf_counters = dbg_lib._dbg_dump(self.handle, path=dump_dir_with_perf_counters)
        debug_dump_without_perf_counters_path, _, _, time_to_generate_dump_without_perf_counters = dbg_lib._dbg_dump(self.handle, path=dump_dir_without_perf_counters,
                                                                                                                     dump_modules=dump_modules_without_perf_counters)
        performance_counters_json_path = os.path.join(debug_dump_with_perf_counters_path, "PERFORMANCE_COUNTER_4.json")
        with open(performance_counters_json_path, 'r') as f:
            counters_data = json.load(f)
        performance_counters = counters_data["Performance Counters Module"]["Performance Counters"]["perf_cntr_clmns"]
        performance_counters_df = pd.DataFrame(performance_counters)
        performance_counters_df = performance_counters_df[performance_counters_df["Counter Name"] == "DCI2DCL_FIFO_S0_PACKET_IN"]
        performance_counters_df = performance_counters_df[["Instance", "Counter Name", "Counter Value"]]
        performance_counters_df = performance_counters_df.rename(columns={"Instance": "instance",
                                                                          "Counter Name": MultiNosConstants.PERFORMANCE_COUNTER_NAME,
                                                                          "Counter Value": MultiNosConstants.PERFORMANCE_COUNTER_VALUE})
        performance_counters_df[MultiNosConstants.PERFORMANCE_COUNTER_VALUE] = performance_counters_df[MultiNosConstants.PERFORMANCE_COUNTER_VALUE].apply(lambda x: int(x, 16))
        performance_counters = performance_counters_df.to_dict(orient='records')
        performance_counters_dict = {
            MultiNosConstants.PERFORMANCE_COUNTERS_DATAFRAME: performance_counters,
            MultiNosConstants.SDK_GENERATION_TIME_WITH_PERF_COUNTERS: time_to_generate_dump_with_perf_counters
        }
        if not os.path.exists(os.path.join(debug_dump_without_perf_counters_path, "PERFORMANCE_COUNTER_4.json")):
            performance_counters_dict[MultiNosConstants.SDK_GENERATION_TIME_WITHOUT_PERF_COUNTERS] = time_to_generate_dump_without_perf_counters
        shutil.rmtree(dump_dir_with_perf_counters)
        shutil.rmtree(dump_dir_without_perf_counters)
        return performance_counters_dict

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
        queue_histogram = tele_lib.TeleQueueDepthHistogram(hist_type=hist_type, port=port, port_tc=tc,
                                                           sample_time_resolution=self.new_sample_time,
                                                           min_boundary=self.new_min_boundary,
                                                           bin_size_resolution=self.new_bin_size,
                                                           mode=SX_TELE_HISTOGRAM_MODE_LINEAR_E)
        tele_lib.tele_histogram_set(self.handle, SX_ACCESS_CMD_SET, queue_histogram)
        tele_lib.tele_histogram_data_get(self.handle, port, tc, hist_type, clear=True)
        # to avoid garbage in the histogram so the next sample will be accurate
        common_lib.sleep(0.1)  # to get accurate results, sample over 100 msec
        return queue_histogram

    def _collect_latency_data_per_port_tc(self, port, tc):
        """
        Collect latency histogram data for a specific port and traffic class.

        Args:
            port: Port to collect latency data from
            tc: Traffic class to collect latency data for

        Returns:
            float: Mean latency for the port/tc combination
        """
        queue_histogram = self.set_tc_latency_histogram(port, tc)
        tc_latency_histogram, _ = tele_lib.tele_histogram_data_get(self.handle, port, tc, SX_TELE_HISTOGRAM_TYPE_PORT_TC_LATENCY_E)
        tele_histogram = tele_lib.tele_histogram_get(self.handle, port, tc, SX_TELE_HISTOGRAM_TYPE_PORT_TC_LATENCY_E)
        bins_range = tele_lib.tele_bins_range_get(SX_TELE_HISTOGRAM_TYPE_PORT_TC_LATENCY_E, tele_histogram.mode, tele_histogram.min_boundary, tele_histogram.bin_size_resolution)
        latency_mean = self.get_latency_mean(tc_latency_histogram, bins_range)
        tele_lib.tele_histogram_set(self.handle, SX_ACCESS_CMD_DESTROY, queue_histogram)
        return latency_mean

    def _calculate_latency_statistics(self, tc_latency_stats, port_group_name):
        """
        Calculate and log latency statistics for all traffic classes.

        Args:
            tc_latency_stats: Dictionary mapping TC to list of latency measurements
            port_group_name: Name of the port group for logging

        Returns:
            list: List of dictionaries containing latency statistics per TC
        """
        # pylint: disable=import-outside-toplevel
        # Used here to avoid import issues on OSes without this lib
        import numpy as np

        tc_latency_df = []
        for tc in range(MultiNosConstants.TC_NUM):
            np_arr_tc_latency_stats = np.array(tc_latency_stats[tc])
            tc_latency_avg = float(np.mean(np_arr_tc_latency_stats))
            tc_latency_99 = float(np.percentile(np_arr_tc_latency_stats, 99))
            tc_latency_max = float(np.max(np_arr_tc_latency_stats))
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
        return tc_latency_df

    def _collect_latency_for_port_group(self, port_group, port_group_name):
        """Collect TC latency statistics for a single port group."""
        tc_latency_stats = {tc: [] for tc in range(MultiNosConstants.TC_NUM)}
        for port in port_group:
            for tc in range(MultiNosConstants.TC_NUM):
                latency_mean = self._collect_latency_data_per_port_tc(port, tc)
                tc_latency_stats[tc].append(latency_mean)

        return self._calculate_latency_statistics(tc_latency_stats, port_group_name)

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
            tc_latency_df = self._collect_latency_for_port_group(port_group, port_group_name)
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
        # pylint: disable=import-outside-toplevel
        # Used here to avoid import issues on OSes without this lib
        import pandas as pd
        self.logger.debug("Getting bandwidth measurements")

        bw_dict = {}
        for port_group_name, port_group in self.port_groups.items():
            self.logger.info(f"Port group: {port_group_name}")
            bw_df = []
            for port in port_group:
                port_bw = port_lib.get_ports_bandwidth(self.handle, port)[port]
                self.logger.info(f"Port {port} RX bandwidth: {port_bw['rx_rate']} TX bandwidth: {port_bw['tx_rate']}")
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
                f"Min TX BW: {tx_min_bw} (port {tx_min_port}). "
                f"Max TX BW: {tx_max_bw} (port {tx_max_port}). "
                f"Diff: {group_stats[MultiNosConstants.TX_BW_DIFF]} "
                f"Average rx_rate BW: {group_stats[MultiNosConstants.RX_BW_AVG]}. "
                f"Min RX BW: {rx_min_bw} (port {rx_min_port}). "
                f"Max RX BW: {rx_max_bw} (port {rx_max_port}). "
                f"Diff: {group_stats[MultiNosConstants.RX_BW_DIFF]}")

            bw_dict[port_group_name] = self._create_bw_dict_entry(group_stats, bw_df)
        return bw_dict

    def _create_bw_dict_entry(self, stats, dataframe):
        """Create a dictionary entry with bandwidth stats and dataframe."""
        return {
            MultiNosConstants.BW_STATS: stats,
            MultiNosConstants.BW_DATAFRAME: dataframe
        }

    def _create_counters_dict_entry(self, dataframe):
        """Create a dictionary entry with counters dataframe."""
        return {MultiNosConstants.COUNTERS_DATAFRAME: dataframe}

    def _get_buffer_configs(self):
        """Get buffer configuration for TC and PG monitoring."""
        return [
            {
                'name': 'TC',
                'buffer_type': SX_COS_EGRESS_PORT_TRAFFIC_CLASS_ATTR_E,
                'buffer_ids': list(range(MultiNosConstants.TC_NUM)),
                'description': 'Traffic Class occupancy (egress)'
            },
            {
                'name': 'PG',
                'buffer_type': SX_COS_INGRESS_PORT_PRIORITY_GROUP_ATTR_E,
                'buffer_ids': list(range(MultiNosConstants.PG_NUM)),
                'description': 'Priority Group occupancy (ingress)'
            },
        ]

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

        @common_lib.retry_on_failure_till_timeout(timeout=30)
        def _wait_for_hft_event(trap_thread_pool, trap_fd_hft):
            trap_queue = trap_thread_pool._queue_dict[trap_fd_hft]
            trap_list = list(trap_queue.queue)
            trap_id_list = [trap.recv_info.trap_id for trap in trap_list]
            if SX_TRAP_ID_BULK_COUNTER_DONE_EVENT not in trap_id_list:
                raise common_lib.NotifyFailure()
        try:
            _wait_for_hft_event(self.trap_thread_pool, trap_fd_hft)
        except common_lib.TimeOutException:
            raise SdkException("HFT event not received")

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
        return bulk_counter_lib.bulk_counters_transaction_get(self.handle, counter_buffer, cntr_key_dict=hft_key_dict,
                                                              counter_type=bulk_counter_lib.BULK_COUNTER_TYPE_HFT)

    def _build_dataframes_from_stats(self, tc_stats, tc_watermark_stats, pg_stats, pg_watermark_stats, port_group_name):
        """Build TC and PG data frames from collected statistics."""
        tc_df = []
        pg_df = []
        for tc in range(MultiNosConstants.TC_NUM):
            self.update_df(tc, tc_stats, tc_watermark_stats, tc_df, port_group_name, MultiNosConstants.TC)
        for pg in range(MultiNosConstants.PG_NUM):
            self.update_df(pg, pg_stats, pg_watermark_stats, pg_df, port_group_name, MultiNosConstants.PG)
        return tc_df, pg_df

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
        # pylint: disable=import-outside-toplevel
        # Used here to avoid import issues on OSes without this lib
        import numpy as np

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
        return self._build_dataframes_from_stats(tc_stats, tc_watermark_stats, pg_stats, pg_watermark_stats, port_group_name)

    def _rearrange_non_hft_occ_results(self, all_iterations_stats, port_group_name):
        """
        Helper function to rearrange non-HFT occupancy results in the same format as _rearrange_occ_results.
        This converts PortOccupancyStats objects into the same dataframe format as the HFT method.

        Args:
            all_iterations_stats: Dictionary with 'TC' and 'PG' keys, each containing list of PortOccupancyStats
            port_group_name: Name of the port group for logging

        Returns:
            Tuple of (tc_df, pg_df) where each is a list of dictionaries with stats
        """
        tc_stats = {tc: [] for tc in range(MultiNosConstants.TC_NUM)}
        tc_watermark_stats = {tc: [] for tc in range(MultiNosConstants.TC_NUM)}
        pg_stats = {pg: [] for pg in range(MultiNosConstants.PG_NUM)}
        pg_watermark_stats = {pg: [] for pg in range(MultiNosConstants.PG_NUM)}

        for stat in all_iterations_stats['TC']:
            tc_stats[stat.buffer_id].append(stat.curr_occupancy)
            tc_watermark_stats[stat.buffer_id].append(stat.watermark)

        for stat in all_iterations_stats['PG']:
            pg_stats[stat.buffer_id].append(stat.curr_occupancy)
            pg_watermark_stats[stat.buffer_id].append(stat.watermark)

        return self._build_dataframes_from_stats(tc_stats, tc_watermark_stats, pg_stats, pg_watermark_stats, port_group_name)

    def update_stats(self, idx, port_array, port_watermark_array, stats, watermark_stats):
        port_data = port_array[:, idx]
        stats[idx].extend(port_data)
        port_watermark_data = port_watermark_array[:, idx]
        watermark_stats[idx].extend(port_watermark_data)

    def _calculate_buffer_statistics(self, stats_values, watermark_values):
        """Calculate average, 99th percentile, and max for buffer statistics."""
        # pylint: disable=import-outside-toplevel
        # Used here to avoid import issues on OSes without this lib
        import numpy as np

        return {
            'avg': float(np.mean(stats_values)),
            'percentile_99': float(np.percentile(stats_values, 99)),
            'max': int(np.max(stats_values)),
            'max_watermark': int(np.max(watermark_values))
        }

    def update_df(self, idx, stats, watermark_stats, df, port_group_name, data_type=MultiNosConstants.TC):
        calculated_stats = self._calculate_buffer_statistics(stats[idx], watermark_stats[idx])

        self.logger.info(f'Port group: {port_group_name}.')
        self.logger.info(f'{data_type} {idx} Occupancy average  is: {calculated_stats["avg"]}')
        self.logger.info(f'{data_type} {idx} Occupancy 99% is: {calculated_stats["percentile_99"]}')
        self.logger.info(f'{data_type} {idx} Max occupancy is: {calculated_stats["max"]}')
        self.logger.info(f'{data_type} {idx} Max watermark is: {calculated_stats["max_watermark"]}\n\n')

        df.append({
            data_type: idx,
            MultiNosConstants.OCC_AVG: calculated_stats['avg'],
            MultiNosConstants.OCC_99: calculated_stats['percentile_99'],
            MultiNosConstants.OCC_MAX: calculated_stats['max'],
            MultiNosConstants.MAX_WATERMARK: calculated_stats['max_watermark']
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
        # pylint: disable=import-outside-toplevel
        # Used here to avoid import issues on OSes without this lib
        import matplotlib.pyplot as plt
        import numpy as np

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

    def _create_tc_pg_dict_entry(self, tc_df, pg_df):
        """Create a dictionary entry with TC and PG data frames."""
        return {
            MultiNosConstants.TC_DATAFRAME: tc_df,
            MultiNosConstants.PG_DATAFRAME: pg_df
        }

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
            tc_pg_dict[port_group_name] = self._create_tc_pg_dict_entry(tc_df, pg_df)
        return tc_pg_dict

    def _extract_counter_fields(self, counters, field_names):
        """Extract specific fields from counter dictionary."""
        return {field: counters[field] for field in field_names}

    def collect_port_custom_counters(self, port, port_counters_dict, clear_counters_value):
        counters = port_lib.port_counter_dict_discard_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict.update(counters)
        port_counters_dict.pop('ingress_general')

        # IEEE 802.3 counters
        ieee_fields = [
            'a_alignment_errors', 'a_frame_check_sequence_errors', 'a_frame_too_long_errors',
            'a_in_range_length_errors', 'a_symbol_error_during_carrier', 'a_unsupported_opcodes_received',
            'a_mac_control_frames_transmitted', 'a_mac_control_frames_received',
            'a_pause_mac_ctrl_frames_transmitted', 'a_pause_mac_ctrl_frames_received'
        ]
        counters = port_lib.port_counter_dict_ieee_802_dot_3_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict.update(self._extract_counter_fields(counters, ieee_fields))

        # RFC 2863 counters
        rfc_2863_fields = ['if_in_discards', 'if_in_errors', 'if_out_discards', 'if_out_errors']
        counters = port_lib.port_counter_dict_rfc_2863_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict.update(self._extract_counter_fields(counters, rfc_2863_fields))

        # RFC 2819 counters
        rfc_2819_fields = ['ether_stats_crc_align_errors', 'ether_stats_drop_events']
        counters = port_lib.port_counter_dict_rfc_2819_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict.update(self._extract_counter_fields(counters, rfc_2819_fields))

        # RFC 3635 counters
        rfc_3635_fields = [
            'dot3stats_alignment_errors', 'dot3stats_carrier_sense_errors', 'dot3stats_fcs_errors',
            'dot3stats_frame_too_longs', 'dot3stats_sqe_test_errors', 'dot3stats_symbol_errors',
            'dot3stats_internal_mac_transmit_errors', 'dot3stats_internal_mac_receive_errors'
        ]
        counters = port_lib.port_counter_dict_rfc_3635_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict.update(self._extract_counter_fields(counters, rfc_3635_fields))

        # CLI counters
        cli_fields = ['port_rx_fcs_errors', 'port_rx_no_buffer', 'port_rx_other_errors', 'port_tx_errors']
        counters = port_lib.port_counter_dict_cli_get(self.handle, port, clear=clear_counters_value)
        port_counters_dict.update(self._extract_counter_fields(counters, cli_fields))

        # Traffic class counters
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
        counters_dict = {}
        clear_counters_env_var_value = os.getenv(MultiNosConstants.CLEAR_COUNTERS_ENV_VAR, MultiNosConstants.CLEAR_COUNTERS_DEFAULT)
        clear_counters_value = clear_counters_env_var_value == 'True'
        self.logger.info(f'Clear counters value is: {clear_counters_value}')
        self.logger.debug('Iterate over all port control counters, and add to sum')
        for port_group_name, port_group in self.port_groups.items():
            counters_df = []
            for port in port_group:
                port_counters_dict = {MultiNosConstants.PORT: hex(port)}
                self.collect_port_custom_counters(port, port_counters_dict, clear_counters_value)
                counters_df.append(port_counters_dict)
            counters_dict[port_group_name] = self._create_counters_dict_entry(counters_df)
            non_zero_counters = {}

            for port_counters in counters_df:
                for port_counter_name, port_counter_value in port_counters.items():
                    if port_counter_name != MultiNosConstants.PORT and port_counter_value > 0:
                        non_zero_counters.setdefault(port_counter_name, []).append(port_counters[MultiNosConstants.PORT])

            if non_zero_counters:
                self.logger.info(f'Non zero counters for Port group: {port_group_name}')
                for port_counter_name, ports in non_zero_counters.items():
                    self.logger.info(f'Counter {port_counter_name}: {ports}')

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
                                "right_Ports": self.connected_ports[len(self.connected_ports) // 2:]
                                }

    def collect_non_hft_tc_pg_occupancy(self):
        """
        Collect TC and PG occupancy statistics for all TCs/PGs across all port groups using shared buffer statistics API.
        This provides comprehensive buffer occupancy monitoring for debugging no_buffer_discard_mc and other buffer issues.

        Returns:
            Dictionary with occupancy statistics per port group containing:
            - TC dataframe with avg, 99%, max occupancy and max watermark for all TCs (0-15)
            - PG dataframe with avg, 99%, max occupancy and max watermark for all PGs (0-7)
        """
        self.logger.info("Collecting comprehensive TC/PG occupancy statistics for all port groups")
        self.logger.debug('Clean buffer statistics for clean occupancy and watermark')
        sb_lib.clear_all_ports_sb_statistics(self.handle, self.connected_ports)

        tc_pg_dict = {}

        for port_group_name, port_group in self.port_groups.items():
            self.logger.info(f"Processing port group: {port_group_name} - Running 100 iterations")

            buffer_configs = self._get_buffer_configs()

            try:
                all_iterations_stats = {config['name']: [] for config in buffer_configs}

                for iteration in range(100):
                    if iteration % 10 == 0:
                        self.logger.debug(f"  Iteration {iteration + 1}/100")

                    for config in buffer_configs:
                        params = [sb_lib.PortStatUsageParams(
                            buffer_type=config['buffer_type'],
                            log_port_list=port_group,
                            buffer_ids=config['buffer_ids']
                        )]

                        stats = sb_lib.get_port_buff_type_stats(self.handle, params, clear=False)
                        all_iterations_stats[config['name']].extend(stats)

                    time.sleep(0.01)

                self.logger.info(f"  Completed 100 iterations for port group {port_group_name}")

                tc_df, pg_df = self._rearrange_non_hft_occ_results(
                    all_iterations_stats, port_group_name
                )

                tc_pg_dict[port_group_name] = self._create_tc_pg_dict_entry(tc_df, pg_df)

            except Exception as e:
                self.logger.error(f"Failed to collect occupancy stats for port group {port_group_name}: {e}")
                tc_pg_dict[port_group_name] = {"error": str(e)}

        return tc_pg_dict

    def _process_occupancy_stats(self, buffer_type_name, stats):
        """
        Process and organize occupancy statistics for a single buffer type into a structured format.

        Args:
            buffer_type_name (str): Name of the buffer type ('TC', 'PG', 'PG_HEADROOM')
            stats (list): List of PortOccupancyStats for this buffer type

        Returns:
            dict: Organized data per port and buffer ID
        """
        buffer_data = {}

        for stat in stats:
            port_hex = hex(stat.port)
            buffer_id = stat.buffer_id

            if port_hex not in buffer_data:
                buffer_data[port_hex] = {}

            # Create appropriate key based on buffer type
            if buffer_type_name == 'TC':
                key = f"tc_{buffer_id}"
            elif buffer_type_name == 'PG':
                key = f"pg_{buffer_id}"
            elif buffer_type_name == 'PG_HEADROOM':
                key = f"pg_{buffer_id}_headroom"
            else:
                key = f"buffer_{buffer_id}"

            buffer_data[port_hex][key] = {
                "current_occupancy": stat.curr_occupancy,
                "watermark": stat.watermark
            }

        return buffer_data

    def _calculate_per_buffer_statistics(self, buffer_type_name, stats, buffer_ids):
        """
        Calculate average, 99th percentile, and max occupancy statistics for each individual buffer ID.

        Args:
            buffer_type_name (str): Name of the buffer type ('TC', 'PG')
            stats (list): List of PortOccupancyStats for this buffer type across all iterations
            buffer_ids (list): List of buffer IDs (TC or PG numbers)

        Returns:
            dict: Statistics per buffer ID including avg, 99th percentile, and max occupancy
        """
        if not stats:
            return {}

        buffer_stats = {}
        for buffer_id in buffer_ids:
            buffer_specific_stats = [stat for stat in stats if stat.buffer_id == buffer_id]

            if not buffer_specific_stats:
                continue

            occupancy_values = [stat.curr_occupancy for stat in buffer_specific_stats]
            watermark_values = [stat.watermark for stat in buffer_specific_stats]

            calculated_stats = self._calculate_buffer_statistics(occupancy_values, watermark_values)

            if buffer_type_name == 'TC':
                key = f"tc_{buffer_id}"
            elif buffer_type_name == 'PG':
                key = f"pg_{buffer_id}"
            else:
                key = f"buffer_{buffer_id}"

            buffer_stats[key] = {
                "avg_occupancy": calculated_stats['avg'],
                "percentile_99_occupancy": calculated_stats['percentile_99'],
                "max_occupancy": calculated_stats['max'],
                "max_watermark": calculated_stats['max_watermark'],
                "total_samples": len(buffer_specific_stats)
            }

            self.logger.info(f"{buffer_type_name} {buffer_id} Statistics:")
            self.logger.info(f"  Occupancy - Avg: {calculated_stats['avg']:.1f}, 99%: {calculated_stats['percentile_99']:.1f}, Max: {calculated_stats['max']}")
            self.logger.info(f"Max watermark: {calculated_stats['max_watermark']}")

        return buffer_stats

    def pre_test(self):
        super().pre_test()
        self.new_sample_time = MultiNosConstants.LATENCY_SAMPLE_TIME
        self.new_min_boundary = MultiNosConstants.LATENCY_MIN_BOUNDARY
        self.new_bin_size = MultiNosConstants.LATENCY_BIN_SIZE_RESOLUTION
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

    def _get_env_var(self, env_var, default):
        """Get environment variable with default value."""
        return os.getenv(env_var, str(default))

    def test_command(self):
        duration = self._get_env_var(MultiNosConstants.SAMPLE_DURATION_ENV_VAR, MultiNosConstants.SAMPLE_DURATION_DEFAULT)
        bw_delay = self._get_env_var(MultiNosConstants.BW_SAMPLE_DELAY_ENV_VAR, MultiNosConstants.BW_SAMPLE_DELAY_DEFAULT)
        tc_delay = self._get_env_var(MultiNosConstants.TC_SAMPLE_DELAY_ENV_VAR, MultiNosConstants.TC_SAMPLE_DELAY_DEFAULT)
        counters_delay = self._get_env_var(MultiNosConstants.COUNTERS_SAMPLE_DELAY_ENV_VAR, MultiNosConstants.COUNTERS_SAMPLE_DELAY_DEFAULT)
        power_delay = self._get_env_var(PowerTempConsts.POWER_SAMPLE_DELAY_ENV_VAR, PowerTempConsts.POWER_SAMPLE_DELAY_DEFAULT)
        temperature_delay = self._get_env_var(PowerTempConsts.TEMPERATURE_SAMPLE_DELAY_ENV_VAR, PowerTempConsts.TEMPERATURE_SAMPLE_DELAY_DEFAULT)
        collectors_info = [
            (MultiNosConstants.BW_SAMPLES, self.collect_bw, bw_delay, MultiNosConstants.BW_SAMPLE_COUNT),
            (MultiNosConstants.COUNTERS_SAMPLES, self.collect_port_counters,
             counters_delay, MultiNosConstants.COUNTERS_SAMPLE_COUNT),
            (PowerTempConsts.POWER_SAMPLES, self.collect_sensors,
             power_delay, PowerTempConsts.SENSORS_SAMPLE_COUNT),
            (PowerTempConsts.TEMPERATURE_SAMPLES, self.collect_temperature,
             temperature_delay, PowerTempConsts.TEMPERATURE_SAMPLE_COUNT),
            (MultiNosConstants.TC_LATENCY_SAMPLES, self.collect_latency,
             tc_delay, MultiNosConstants.TC_LATENCY_SAMPLE_COUNT)
        ]
        self.logger.info(f'speed is: {self.speed}')
        if self.speed < 800:
            collectors_info.append((MultiNosConstants.TC_PG_SAMPLES,
                                    self.collect_ports_tc_occ_and_watermark, tc_delay,
                                    MultiNosConstants.TC_PG_SAMPLE_COUNT))
        else:
            collectors_info.append((MultiNosConstants.TC_PG_SAMPLES,
                                    self.collect_non_hft_tc_pg_occupancy, tc_delay,
                                    MultiNosConstants.TC_PG_SAMPLE_COUNT))
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

    def filter_collectors_list(self, collectors_info):
        filtered_collectors_info = []
        for samples_name, collector, collector_delay, sample_count in collectors_info:
            if samples_name in self.collectors_list:
                filtered_collectors_info.append((samples_name, collector, collector_delay, sample_count))
        return filtered_collectors_info


if __name__ == "__main__":
    test = TrafficValidator()
    test.execute_test()
    sys.exit(test.rc)

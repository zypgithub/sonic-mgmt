import logging
import os
import json
from ngts.constants.constants import BugHandlerConst
from ngts.constants.performance_constants import PerfConsts
from infra.tools.exceptions.test_issue import TestIssue
from ngts.helpers.performance.traffic_helpers import create_json_traffic_file
from ngts.cli_wrappers.common.performance_clis_common import PerformanceCommon


class DvsPerformance(PerformanceCommon):
    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
        super().__init__(topology_obj, engine, dut_alias, cli_obj)
    '''
    TODO :- Shahaf Bodner
    Implement the following methods exactly as defined,
    Tests would be dependent upon these methods therefore any change in the method call
    should be translated into equivalent for sonic and cumulus(NVUE)
    '''

    def get_ports(self, ports_dict):
        '''
        For performance setups only, gets the physical and sdk ports.
        This assumes the following physical topology :-
        LEFT_TG (First 32 ports) ---- (First 32 ports) DUT (Last 32 ports) ---- (Last 32 Ports) RIGHT_TG

        :param ports_dict: dictionary containing the following arguments :-
            split_upstream : 1x or 2x or 4x or 8x
            split_downstream : 1x or 2x or 4x or 8x
            port_sku : HW_SKU for moose devices.

        :param get_sdk_ports: bool: Whether or not we want to set the sdk ports.

        returns 2 dictionaries phy_port_dict, sdk_port_dict
        phy_port_dict = {
            'right_tg' : [],
            'left_tg' : [],
            'dut' : []
        }
        sdk_port_dict = {
            'right_tg' : [],
            'left_tg' : [],
            'dut' : []
        }
        TODO :- Shahaf Bodner
        return
        fanout left ---- [10001, 10004, 10008 ........]
        dut -------- [10001, 10003, ..........., 100dd, ....., 100ff]
        fanout right [10001, 10003, 10004, 10007]
        800G <-> 400G
        Args: split_upstream : 1x
                split_downstream: 2x
        '''
        raise NotImplementedError

    '''
    Define a set_port_breakout to fix the port breakout on a single dut
    def set_port_breakout()
    '''

    def get_sdk_port_from_physical_ports(self, physical_port):
        '''
        Since SDK ports are same as physical ports this function should just return the list of sdk port only.
        In case of DVS we would treat the sdk ports and physical ports as same.
        '''
        return physical_port

    def get_configuration_file_path(self, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR):
        full_path = os.path.join(BugHandlerConst.NGTS_PATH, "performance_tests",
                                 template_suite, scenario, "dvs", f"{self.dut_alias}.txt")
        logging.info(f"Full Path returned is {full_path}")
        with open(full_path, 'r') as file:
            json_str = file.read().replace('\n', '')
            json_dict = json.loads(json_str)
        return json_dict["sdk_test_name"]

    def apply_configuration_file(self, scenario, template_suite=PerfConsts.DEFAULT_PERF_TEMPLATES_DIR, dst_dir=None):
        test_name = self.get_configuration_file_path(scenario, template_suite)
        logging.info(f"Configuration to be run {test_name}")
        logging.info(f"Applying the configuration on {self.dut_alias}")
        cmd = f"{PerfConsts.DVS_RUN_TEST_PATH} --names {test_name}"
        self.execute_cmd(cmd)

    def save_basic_configuration(self, players):
        pass

    def restore_basic_configuration(self):
        restart_cmd = "dvs_stop.sh && dvs_start.sh --sdk_bridge_mode=HYBRID"
        self.execute_cmd(restart_cmd)

    def set_ibm(self, ibm_mode=True, run_fw_latency_optimization=False):
        self.restore_basic_configuration()
        set_ibm_mode_cmd = f"export BUFFER_AUTO_MODE={not (ibm_mode)}"
        self.execute_cmd(set_ibm_mode_cmd)
        if run_fw_latency_optimization:
            # TODO: replace calling the script with calling the SDK api
            fw_latency_optimization_cmd = f"python /root/sys_sdk/sx_sdk_py_tests/tools/multi_nos/dqs_to_glc.py 5 24"
            self.execute_cmd(fw_latency_optimization_cmd)

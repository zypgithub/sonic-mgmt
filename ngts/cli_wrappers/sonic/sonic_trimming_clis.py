import os
import json
import allure
import logging
from ngts.helpers.system_helpers import copy_files_to_syncd
from ngts.constants.constants import BugHandlerConst, InfraConst
from ngts.constants.performance_constants import PerfConsts, MRCConsts
from ngts.cli_wrappers.common.performance_clis_common import PerformanceCommon
from jinja2 import Environment, FileSystemLoader


class SonicTrimmingCli(PerformanceCommon):
    """
    This class is for trimming cli commands for sonic only
    """

    def __init__(self, topology_obj, engine, dut_alias, cli_obj):
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

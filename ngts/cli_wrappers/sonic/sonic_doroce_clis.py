import logging
import random
import re

from retry.api import retry_call
from ngts.constants.constants import SonicConst, DoroceConsts
logger = logging.getLogger()

DEFAULT_POOLS_LIST = ['egress_lossless_pool',
                      'egress_lossy_pool',
                      'ingress_lossless_pool',
                      'ingress_lossy_pool']

DEFAULT_MSFT_POOLS_LIST = ['egress_lossless_pool',
                           'egress_lossy_pool',
                           'ingress_lossless_pool']


class SonicDoroceCli:
    """
    This class is for DoRoCE cli commands
    """

    def __init__(self, engine, cli_obj):
        self.engine = engine
        self.cli_obj = cli_obj

    def config_doroce(self, type=None, mode=None, perc=None, ports_list=None):
        """
        Configure the DoRoCE
        :param type: the buffer type. lossless or lossy
        :param mode: the mode. double-ipool or single-ipool
        :param perc: list of percentage to set. Example ['90', '10']
        :param ports_list: list of ports to check, if required
        :return: the output of cli command
        """
        cmd = 'sudo config doroce enabled'
        if type:
            cmd += f' --type {type}'
        if mode:
            cmd += f' --mode {mode}'
        if perc:
            cmd += f' --percentage {perc[0]} {perc[1]}'
        output = self.engine.run_cmd(cmd)
        # sometimes the configuration is not applied see details in https://redmine.mellanox.com/issues/3769105
        if 'please save and reload configuration' in output:
            if not ports_list:
                ports_list = ['Ethernet0']
            self.cli_obj.general.save_configuration()
            self.cli_obj.general.reboot_reload_flow(r_type=SonicConst.CONFIG_RELOAD_CMD, ports_list=ports_list)
        return output

    def config_doroce_lossless_double_ipool(self, perc=None, ports_list=None):
        """
        Apply 2 ingress pools - lossless RoCE ingress pool and lossy ingress pool
        :param perc: list of percentage to set
        :param ports_list: list of port to check
        :return: the output of cli command
        """
        if perc is None:
            perc = ['90', '10']
        return self.config_doroce(type='lossless', mode='double-ipool', perc=perc, ports_list=ports_list)

    def config_doroce_lossless_single_ipool(self):
        """
        Apply 1 ingress pools - lossless RoCE pool and lossy ingress pool
        :return: the output of cli command
        """
        return self.config_doroce(type='lossless', mode='single-ipool')

    def config_doroce_lossy_double_ipool(self, perc=None):
        """
        Apply 2 ingress pools - lossy RoCE ingress pool and lossy ingress pool
        :param perc: list of percentage to set
        :return: the output of cli command
        """
        if perc is None:
            perc = ['90', '10']
        return self.config_doroce(type='lossy', mode='double-ipool', perc=perc)

    def disable_doroce(self):
        """
        Delete RoCE configuration.
        :return: the output of cli command
        """
        return self.engine.run_cmd('sudo config doroce disabled')

    def show_doroce_status(self):
        """
        Displaying RoCE configuration
        :return: the output of cli command
        """
        return self.engine.run_cmd('show doroce status')

    def is_doroce_configuration_enabled(self):
        """
        Check if the DoRoCE configured
        :return: the output of cli command
        """
        return 'enabled' in self.show_doroce_status()

    def show_buffer_configuration(self):
        """
        Displaying buffer configuration
        :return: the output of cli command
        """
        return self.engine.run_cmd('show buffer configuration')

    def check_buffer_configurations(self, expected_pools_list=None, hwsku=None):
        if expected_pools_list is None:
            if hwsku.startswith('Mellanox'):
                expected_pools_list = DEFAULT_MSFT_POOLS_LIST
            else:
                expected_pools_list = DEFAULT_POOLS_LIST
        retry_call(self._check_buffer_configurations, fargs=[expected_pools_list], tries=3, delay=3, logger=None)

    def _check_buffer_configurations(self, expected_pools_list):
        buffer_conf_output = self.show_buffer_configuration()
        assert "No buffer pool information available" not in buffer_conf_output, \
            "No buffer pool information available. Try running 'qos reload' to overcome that."
        for expected_pool in expected_pools_list:
            assert f'Pool: {expected_pool}' in buffer_conf_output, f'The expected pool:{expected_pool} not' \
                f' found in the buffer configuration output'

    def parse_and_show_buffer_information(self):
        """
        Parsing pool sizes in show buffer information
        :return: parsed dictionary. Example:
            {'egress_lossy_pool': 12328960,
             'ingress_lossy_pool': 12328960,
             'egress_lossless_pool': 34287552,
             'ingress_lossless_pool': 12328960}
        """
        buffer_info_output = self.show_buffer_information()
        pool_sizes_dict = self.parse_pool_sizes_from_buffer_info_output(buffer_info_output)
        return pool_sizes_dict

    def show_buffer_information(self):
        """
        Displaying buffer information
        :return: the output of cli command
        """
        return self.engine.run_cmd('show buffer information')

    @staticmethod
    def parse_pool_sizes_from_buffer_info_output(output):
        """
        Parse buffer information output
        :param output: output from show buffer information cli
        :return: parsed dictionary.
        Example:
            {'egress_lossy_pool': 12328960,
             'ingress_lossy_pool': 12328960,
             'egress_lossless_pool': 34287552,
             'ingress_lossless_pool': 12328960}
        """
        pool_sizes = {}
        # Split the output into sections based on "Pool: "
        sections = output.strip().split("Pool: ")
        # Iterate through each section (starting from index 1 since index 0 is empty)
        for section in sections[1:]:
            lines = section.strip().splitlines()
            # Extract the pool name (first line after "Pool: ")
            pool_name = lines[0].strip()
            size = None
            for line in lines:
                if line.strip().startswith("size"):
                    size = line.strip().split()[1]
                    break
            # If size is found, store it in the dictionary
            if size:
                pool_sizes[pool_name] = int(size)
        return pool_sizes

    def parse_and_show_doroce_status(self):
        doroce_status_output = self.show_doroce_status()
        pool_configurations = self.parse_configurations_from_doroce_status(doroce_status_output)
        return pool_configurations

    @staticmethod
    def parse_configurations_from_doroce_status(output):
        """
        Parse doroce status
        :param output: output from show doroce status cli
        :return: parsed dictionary.
        Example:
            {'egress_lossless_pool': {'size': 34287552, 'percentage': 'N/A'},
             'egress_lossy_pool': {'size': 2807808, 'percentage': '10'},
             'ingress_lossless_pool': {'size': 25270272, 'percentage': '90'},
             'ingress_lossy_pool': {'size': 2807808, 'percentage': '10'}
             }
        """
        pool_configurations = {}
        # Split the output into sections based on major headings
        sections = re.split(r'\n(?:RoCE|Congestion|Pools|PFC|QoS|Scheduler) configurations\n', output.strip(),
                            flags=re.IGNORECASE)

        # If there are at least two sections (before and after "Pools configurations"), proceed
        if len(sections) >= 2:
            pools_section = sections[1].strip()
            lines = pools_section.splitlines()

            for line in lines:
                # Skip lines that are empty or don't contain pool information
                if line.startswith("Pool") or 'pool' not in line:
                    continue

                match = re.match(r'(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', line.strip())
                if match:
                    pool_name = match.group(1)
                    pool_size = int(match.group(4))
                    pool_percentage = match.group(6)
                    pool_details = {
                        'size': pool_size,
                        'percentage': pool_percentage
                    }
                    pool_configurations[pool_name] = pool_details
        return pool_configurations

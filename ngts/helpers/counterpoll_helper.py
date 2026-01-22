import re
import operator
import logging
import pytest
from collections import namedtuple, Counter
from ngts.constants.constants import CounterpollConstants


logger = logging.getLogger()

MONIT_RESULT = namedtuple('MonitResult', ['processes', 'memory'])
VALID_CPU_USAGE_NUMBER_IN_ONE_INTERVAL = 3.0


class CounterpollHelper:

    @staticmethod
    def get_available_counterpoll_types(engines):
        """
        This method is used to get the available counterpoll types
        :param engines: engines fixture
        :return: available counterpoll types list
        """
        dut_engine = engines.dut
        available_option_list = []
        COMMANDS = 'Commands:'
        counterpoll_show = dut_engine.run_cmd(CounterpollConstants.COUNTERPOLL_QUEST)
        index = counterpoll_show.find(COMMANDS) + len(COMMANDS) + 1
        for line in counterpoll_show[index:].splitlines():
            available_option_list.append(line.split()[0])
        return [option for option in available_option_list if option not in CounterpollConstants.EXCLUDE_COUNTER_SUB_COMMAND]

    @staticmethod
    def get_parsed_counterpoll_show(counterpoll_show):
        """
        This method is used to get the formatted parsed counterpoll show output
        It removes the type key
        :param counterpoll_show:
        :return: formatted parsed counterpoll show output which removes the type key
        """
        parsed_counterpoll = {}
        for _, counterpoll in counterpoll_show.items():
            parsed_counterpoll[counterpoll[CounterpollConstants.TYPE]] = {
                CounterpollConstants.INTERVAL: counterpoll[CounterpollConstants.INTERVAL],
                CounterpollConstants.STATUS: counterpoll[CounterpollConstants.STATUS]}
        return parsed_counterpoll

    @staticmethod
    def restore_counterpoll_status(engines, counterpoll_before, counterpoll_after):
        """
        This method is used to restore the counterpoll status
        :param engines: engines fixture
        :param counterpoll_before: counterpoll show output before test case
        :param counterpoll_after:  counterpoll show output after test case
        """
        dut_engine = engines.dut
        for counterpoll, value in counterpoll_after.items():
            if counterpoll not in counterpoll_before:
                continue
            else:
                if counterpoll_after[counterpoll][CounterpollConstants.STATUS] \
                        != counterpoll_before[counterpoll][CounterpollConstants.STATUS]:
                    dut_engine.run_cmd(CounterpollConstants.COUNTERPOLL_RESTORE.format(
                        CounterpollConstants.COUNTERPOLL_MAPPING[counterpoll],
                        counterpoll_before[counterpoll][CounterpollConstants.STATUS]))

    @staticmethod
    def disable_counterpolls(cli_obj, counter_type_list):
        """
        This method is used to disable counterpoll types
        :param cli_obj: cli_obj fixture
        :param counter_type_list: counterpoll type list
        """
        for counterpoll_type in counter_type_list:
            cli_obj.counterpoll.disable_counterpoll(counterpoll_type)

    @staticmethod
    def check_memory(i, memory_threshold, monit_result, outstanding_mem_polls):
        """
        This method is used to check memory
        :param i: memory usage index
        :param memory_threshold: memory threshold
        :param monit_result: cpu and memory monitor result
        :param outstanding_mem_polls: outstanding memory list
        """
        if monit_result.memory['used_percent'] > memory_threshold:
            logger.debug(f"system memory usage exceeds {memory_threshold}%: {monit_result.memory}")
            outstanding_mem_polls[i] = monit_result.memory

    @staticmethod
    def update_cpu_usage_desired_program(proc, program_to_check, program_to_check_cpu_usage):
        """
        This method is used to update cpu usage for desired process
        :param proc: process monitor information
        :param program_to_check: the desired process name
        :param program_to_check_cpu_usage: cpu usage list of desired process
        """
        if program_to_check:
            if proc['name'] == program_to_check:
                program_to_check_cpu_usage.append(proc['cpu_percent'])

    @staticmethod
    def prepare_ram_cpu_usage_results(memory_threshold, monit_results, outstanding_mem_polls, program_to_check,
                                      program_to_check_cpu_usage):
        """
        This method is used to check memory usage and update cpu usage for desired process
        :param memory_threshold: memory threshold
        :param monit_results: cpu and memory monitor results
        :param outstanding_mem_polls: outstanding memory usage records
        :param program_to_check: the special process to be checked
        :param program_to_check_cpu_usage: the list that store cpu usages
        """
        for i, monit_result in enumerate(MONIT_RESULT(*_) for _ in monit_results):
            logger.debug(f"------ Iteration {i} ------")
            CounterpollHelper.check_memory(i, memory_threshold, monit_result, outstanding_mem_polls)
            for proc in monit_result.processes:
                CounterpollHelper.update_cpu_usage_desired_program(proc, program_to_check, program_to_check_cpu_usage)

    @staticmethod
    def check_cpu_usage(cpu_threshold, outstanding_procs, outstanding_procs_counter, proc):
        """
        This method is used to check cpu usage and record it if it's larger than the cpu threshold
        :param cpu_threshold: the cpu threshold
        :param outstanding_procs: outstanding cpu consume lprocess list
        :param outstanding_procs_counter:
        :param proc:
        """
        if proc['cpu_percent'] >= cpu_threshold:
            logger.debug(f"process {proc['name']} ({proc['pid']}) cpu usage exceeds {cpu_threshold}%")
            outstanding_procs[proc['pid']] = proc.get('cmdline', proc['name'])
            outstanding_procs_counter[proc['pid']] += 1

    @staticmethod
    def extract_valid_cpu_usage_data(program_to_check_cpu_usage, poll_interval):
        """
        This method it to extract the valid cpu usage data according to the poll_interval
        1. Find the index for the max one for every poll interval,
        2. Discard the data if the index is on the edge(0 o the length of program_to_check_cpu_usage -1)
        3. If the index is closed in the neighbour interval, only keep the former one
        4. Return all indexes
        :param program_to_check_cpu_usage: the list that store cpu usages
        :param poll_interval: specific counterpoll poll interval
        :return: valid cpu usage index list
        """
        valid_cpu_usage_center_index_list = []
        poll_number = len(program_to_check_cpu_usage) // poll_interval

        def find_max_cpu_usage(cpu_usage_list, poll_times):
            max_cpu_usage = cpu_usage_list[0]
            max_cpu_usage_index = 0
            for i, cpu_usage in enumerate(cpu_usage_list):
                if cpu_usage > max_cpu_usage:
                    max_cpu_usage = cpu_usage
                    max_cpu_usage_index = i
            return [max_cpu_usage, max_cpu_usage_index + poll_times * poll_interval]

        for i in range(0, poll_number):
            max_cpu_usage, max_cpu_usage_index = find_max_cpu_usage(
                program_to_check_cpu_usage[poll_interval * i:poll_interval * (i + 1)], i)
            if max_cpu_usage_index == 0 or max_cpu_usage_index == len(program_to_check_cpu_usage) - 1:
                logger.info(f"The data is on the edge, index is in [0, {max_cpu_usage_index}], discard it")
            else:
                if valid_cpu_usage_center_index_list and valid_cpu_usage_center_index_list[-1] + 1 == max_cpu_usage_index:
                    continue
                logger.info(f"One valid cpu peak found - index:{max_cpu_usage_index} cpu usage:{program_to_check_cpu_usage[max_cpu_usage_index]}")
                valid_cpu_usage_center_index_list.append(max_cpu_usage_index)

        return valid_cpu_usage_center_index_list

    @staticmethod
    def disable_all_counterpoll_type_except_tested(engines, cli_obj, counterpoll_type):
        """
        This method is used to disable all counterpoll except the tested counterpoll
        :param engines: engines fixture
        :param cli_obj: cli_obj fixture
        :param counterpoll_type: the tested counterpoll
        """
        available_types = CounterpollHelper.get_available_counterpoll_types(engines)
        available_types.remove(counterpoll_type)
        CounterpollHelper.disable_counterpolls(cli_obj, available_types)

    @staticmethod
    def caculate_cpu_usge_average_value(valid_cpu_usage_center_index_list, program_to_check_cpu_usage):
        """
        This method is used to calculate the final cpu usage for the desired program
        :param valid_cpu_usage_center_index_list: the highest cpu usage index in each poll interval
        :param program_to_check_cpu_usage: all monitored cpu usage list
        :return: the final cpu usage for the desired program
        """
        len_valid_cpu_usage = len(valid_cpu_usage_center_index_list)
        cpu_usage_average = 0.0
        for i in valid_cpu_usage_center_index_list:
            cpu_usage_average += sum(program_to_check_cpu_usage[i - 1: i + 2])
            logger.info(f"cpu usage center index: {i}: cpu usage: {program_to_check_cpu_usage[i - 1:i + 2]}")
        return cpu_usage_average / len_valid_cpu_usage / VALID_CPU_USAGE_NUMBER_IN_ONE_INTERVAL if len_valid_cpu_usage != 0 else 0

    @staticmethod
    def check_and_analyse_cpu_memory_usage(monit_results, setup_thresholds):
        memory_threshold, normal_cpu_threshold, high_cpu_consume_procs = setup_thresholds
        outstanding_mem_polls = {}
        outstanding_procs = {}
        cpu_threshold = 0
        outstanding_procs_counter = Counter()
        for i, monit_result in enumerate(MONIT_RESULT(*_) for _ in monit_results):
            logger.debug("------ Iteration %d ------", i)
            CounterpollHelper.check_memory(i, memory_threshold, monit_result, outstanding_mem_polls)
            for proc in monit_result.processes:
                cpu_threshold = normal_cpu_threshold
                if proc['name'] in high_cpu_consume_procs:
                    cpu_threshold = high_cpu_consume_procs[proc['name']]
                CounterpollHelper.check_cpu_usage(cpu_threshold, outstanding_procs, outstanding_procs_counter, proc)
        logger.info("Analyze CPU and Memory usage")
        CounterpollHelper.analyse_monitoring_results(cpu_threshold, memory_threshold, outstanding_mem_polls, outstanding_procs, outstanding_procs_counter)

    @staticmethod
    def analyse_monitoring_results(cpu_threshold, memory_threshold, outstanding_mem_polls, outstanding_procs,
                                   outstanding_procs_counter):
        """
        This method is used to analysis cpu and memory usage result and mark case as failed if certain conditions matched
        :param cpu_threshold: cpu threshold
        :param memory_threshold: memory threshold
        :param outstanding_mem_polls: outstanding memory usage dict
        :param outstanding_procs: outstanding cpu consume processes
        :param outstanding_procs_counter: outstanding process persist time statistics
        """
        persist_outstanding_procs = []
        for pid, freq in outstanding_procs_counter.most_common():
            if freq <= CounterpollConstants.CPU_HIGH_CONSUME_PERSIST_TIME_THRESHOLD:
                break
            logger.info(f"A outstanding cpu consume process found - PID: {pid}")
            persist_outstanding_procs.append(pid)
        if outstanding_mem_polls or persist_outstanding_procs:
            if outstanding_mem_polls:
                logger.error(f"system memory usage exceeds {memory_threshold}%")
            if persist_outstanding_procs:
                logger.error(
                    f"processes that persistently exceeds cpu usage {cpu_threshold}%: {[outstanding_procs[p] for p in persist_outstanding_procs]}")
            pytest.fail("system cpu and memory usage check fails")

    @staticmethod
    def monit_process(engines, interval, iterations):
        """
        This method is used to get the cpu and memory usage monitor result
        Use top command with -E m to collect cpu and memory usage in MiB
        The typical output of top command is listed

        top - 05:50:42 up 28 min,  1 user,  load average: 0.47, 0.53, 0.62
        Tasks: 285 total,   1 running, 281 sleeping,   0 stopped,   3 zombie
        %Cpu(s):  3.6 us,  1.8 sy,  0.0 ni, 94.3 id,  0.0 wa,  0.0 hi,  0.3 si,  0.0 st
        MiB Mem :  15900.0 total,  11124.6 free,   3354.8 used,   1420.6 buff/cache
        MiB Swap:      0.0 total,      0.0 free,      0.0 used.  12123.8 avail Mem

            PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
           8010 root      20   0 1030044 616524  48952 S  18.6   3.8   2:51.30 sx_sdk
           3178 root      20   0  112308  58808   7824 S  10.6   0.4   2:11.68 redis-server
          16484 root      20   0  128052  37376  13528 S   7.3   0.2   2:15.40 python3
           7984 root      20   0 1868848 147204 111260 S   3.7   0.9   0:44.64 syncd
          16373 tcpdump   20   0   30940  12628   9032 S   0.7   0.1   0:02.00 snmpd
          16486 root      20   0 1689580  70456  16628 S   0.7   0.4   0:08.57 dialout_client_
           5965 root      20   0   29452  24804   9148 S   0.3   0.2   0:00.87 supervisord
           8322 root      20   0  136512  86848  30664 S   0.3   0.5   0:04.71 python3
           9697 root      20   0   29452  24768   9104 S   0.3   0.2   0:00.70 supervisord
          16376 root      20   0 1693856  72684  19124 S   0.3   0.4   0:08.45 telemetry
          51558 admin     20   0   10800   3936   3164 R   0.3   0.0   0:00.02 top
              1 root      20   0  167696  11320   7900 S   0.0   0.1   0:17.66 systemd
              2 root      20   0       0      0      0 S   0.0   0.0   0:00.00 kthreadd
        ......

        :param engines: engines fixture
        :param interval: top command update interval
        :param iterations: top command iterations
        :return: cpu and memory usage monitor result
        """
        dut_engine = engines.dut
        MonitResult = namedtuple('MonitResult', ['processes', 'memory'])
        cmd = f"top -d {interval} -n {iterations + 1} -b -E m"
        stdout = dut_engine.run_cmd(cmd)

        monit_results = []
        proc_section = False
        mem_re = re.compile(
            (r"^MiB Mem\s+:\s+(?P<total>[\d.]+)\+?\s*total,\s+(?P<free>[\d.]+)"
             r"\+?\s*free,\s+(?P<used>[\d.]+)\+?\s*used,\s+[\d.]+\+?\s*buff/cache\s*$")
        )
        mem_attrs = ('total', 'free', 'used')
        proc_attrs = ('pid', 'status', 'cpu_percent', 'memory_percent', 'name')
        proc_attrs_getter = operator.itemgetter(0, 7, 8, 9, 11)
        for line in stdout.splitlines():
            if not line:
                proc_section = False
            elif line.startswith('top'):
                monit_results.append(MonitResult([], {}))
            elif line.startswith('MiB Mem'):
                CounterpollHelper.process_mem_section(monit_results, mem_re, line, mem_attrs)
            elif "PID" in line:
                proc_section = True
            elif proc_section:
                CounterpollHelper.process_proc_section(monit_results, proc_attrs_getter, line, proc_attrs)

        monit_results = monit_results[1:]
        return monit_results

    @staticmethod
    def process_mem_section(monit_results, mem_re, line, mem_attrs):
        """
        This method is used to process memory section in top command output
        :param monit_results: a list which stores the top monitor result
        :param mem_re: memory re pattern
        :param line: line in top command output
        :param mem_attrs: a tuple which stores the memory attributes
        """
        line_match = mem_re.match(line)
        values = (line_match.group(_) for _ in mem_attrs)
        memory = {k: float(v) for k, v in zip(mem_attrs, values)}
        used_percent = memory['used'] * 100 / float(memory['total'])
        memory['used_percent'] = round(used_percent, 2)
        monit_results[-1].memory.update(memory)

    @staticmethod
    def process_proc_section(monit_results, proc_attrs_getter, line, proc_attrs):
        """
        This method is used to process the proc section in top command output
        :param monit_results: a list which stores the top monitor result
        :param proc_attrs_getter: attribute getter for proc
        :param line: line in top command output
        :param proc_attrs: a tuple which stores the process attributes
        """
        process = dict(
            zip(proc_attrs, proc_attrs_getter(line.split()))
        )
        process['cpu_percent'] = float(process['cpu_percent'])
        process['memory_percent'] = float(process['memory_percent'])
        process['pid'] = int(process['pid'])
        monit_results[-1].processes.append(process)

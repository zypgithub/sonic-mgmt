import allure
import logging
import pytest
import random
import os
from retry.api import retry_call
from ngts.constants.constants import InfraConst, PytestConst
from ngts.common.util import get_specified_installed_dpus

logger = logging.getLogger()


def generate_test_flavors(config):
    """Generate test flavors based on setup name."""
    hwsku = config.getoption("--dut_hwsku", default="")
    if hwsku and "4280" in hwsku:
        return ["dpu", "switch-ignore_dpu_errors", "switch-dpu_errors_only"]
    return ["switch"]


def pytest_generate_tests(metafunc):
    """Parametrize flavor from setup name."""
    if "flavor" in metafunc.fixturenames:
        params = generate_test_flavors(metafunc.config)
        metafunc.parametrize("flavor", params)


@pytest.fixture(scope="function")
def flavor(request):
    return request.param


@pytest.fixture()
def dut_host(engines, flavor, topology_obj):
    if flavor == 'dpu':
        dut_alias = 'dut'
        dut_name = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Common']['Name']
        specified_installed_dpus = get_specified_installed_dpus(dut_alias, dut_name)
        if specified_installed_dpus:
            dpu_name = random.choice(specified_installed_dpus)
        else:
            dpu_index = random.randint(0, 3)
            dpu_name = f'dpu{dpu_index}'
        if dpu_name in engines:
            os.environ[InfraConst.SELECTED_DPUS] = dpu_name
            return engines[dpu_name]
        else:
            pytest.skip("Skip it due to the device doesn't has dpu")
    else:
        return engines.dut


@pytest.mark.loganalyzer_hosts(include='dpu')
def test_check_errors_in_log_during_deploy_sonic_image(dut_host, request, loganalyzer, flavor, topology_obj):
    """
    Test checks errors in logs which happen during deploy SONiC image.
    This test must be executed as first test case after deploy SONiC image.
    Test logic:
    - Get current LogAnalyzer start_string and remove existing start_string from syslog file
    - Try to find 'sonic-installer: Installing image' log:
       - If found: Insert start_string before install log (to avoid analyzing logs from previous image)
       - If not found: Create new oldest syslog file with start_string inside
    - Then on teardown step LogAnalyzer will analyze all logs since start_string till end_string(which will be
    added after current test case automatically by LogAnalyzer logic)
    :param dut_host: dut engine
    :param request: pytest build-in
    :param loganalyzer: loganalyzer fixture
    """
    os.environ[PytestConst.GET_DUMP_AT_TEST_FALIURE] = "False"
    log_analyzer_start_string_line = get_la_start_string(dut_host, request)

    # Find sonic-installer log and insert start_string before it (avoid logs from previous image)
    install_info = find_install_image_log(dut_host)

    if install_info:
        syslog_file, line_number, timestamp = install_info
        logger.info(f'Found install image log in {syslog_file} at line {line_number}')
        new_start_string = ' '.join([timestamp, log_analyzer_start_string_line])
        insert_start_string_before_line(dut_host, syslog_file, line_number, new_start_string)
    elif flavor == 'switch-dpu_errors_only':
        is_dark_mode = topology_obj.players['dut']['cli'].general.is_dark_mode()
        if is_dark_mode:
            pytest.skip("Skip the [switch-dpu_errors_only] test while it's dark mode")
        # Find the log of bfb installation success and insert start_string after it
        bfb_installation_success_pattern = "sonic-bfb-installer.sh.*Installation Successful"
        bfb_installation_success_log = find_install_image_log(dut_host, bfb_installation_success_pattern, 'tail')
        if not bfb_installation_success_log:
            assert False, "BFB installation success log is not found."
        syslog_file, line_number, timestamp = bfb_installation_success_log
        logger.info(f'Found bfb installation success log in {syslog_file} at line {line_number}')
        new_start_string = ' '.join([timestamp, log_analyzer_start_string_line])
        insert_start_string_before_line(dut_host, syslog_file, line_number, new_start_string)
    else:
        # Fallback to original logic: create new oldest syslog file
        logger.warning('Install image log not found, falling back to oldest syslog')
        oldest_syslog_id = get_oldest_syslog_id(dut_host)
        new_start_string = get_new_start_string(dut_host, oldest_syslog_id, log_analyzer_start_string_line)
        insert_new_start_string(dut_host, oldest_syslog_id, new_start_string)
    ignore_regex = [
        r".*crashkernel=\d+M",
        r".*Command line: BOOT_IMAGE=.*",
        r".*kexec: Reserving the low 1M of memory for crashkernel.*",
        r".*Reserving .* memory .* for crashkernel .*",
        r".*Kernel command line: BOOT_IMAGE=.*",
        r".*DMA: preallocated .* pool for atomic allocations.*",
        r".*DPC: error containment capabilities:.*",
        r".*GPT: Use GNU Parted to correct GPT errors.*",
        r".*NOHZ tick-stop error: Non-RCU local softirq work is pending, handler #08!!!.*",
        r".*ERR rsyslogd: cannot connect to [\d\.]+:\d+: (Connection timed out|Network is unreachable).*",
        r".*ERR rsyslogd: omfwd: remote server at [\d\.]+:\d+ seems to have closed connection.*",
        r".*TPM interrupt not working, polling instead.*",
        r".*Failed to get link config: No such device.*",
        r".*ERR configmgrd: Failed to get primary ASIC for.*",
    ]

    ignore_regex_dpu_errors = [
        r".*kernel.*mlx5_core.*err.*",
    ]
    if flavor == 'switch-ignore_dpu_errors':
        ignore_regex.extend(ignore_regex_dpu_errors)

    logger.info('Adding end_marker in syslog')
    for analyzer in loganalyzer.values():
        if 'switch' in flavor and 'dpu' in analyzer.ansible_host.hostname:
            continue
        analyzer.ignore_regex.extend(ignore_regex)
        if flavor == 'switch-dpu_errors_only':
            analyzer.match_regex = ignore_regex_dpu_errors
        # Logic below is required to overcome the issue the when end_marker is not present in syslog - in this case,
        # the end_marker will be added forcefully
        run_id = analyzer.ansible_loganalyzer.run_id
        cmd = f'sudo python /tmp/loganalyzer.py --action add_end_marker --run_id {run_id}'
        retry_call(dut_host.run_cmd,
                   fkwargs={"cmd": cmd, "timeout": 10},
                   tries=3,
                   delay=3,
                   logger=logger)


def find_install_image_log(engine, search_pattern=None, match_rule='head'):
    """
    Find the 'sonic-installer: Installing image SONiC-OS-' log or the specified log in syslog files.
    :param engine: dut engine object
    :param search_pattern: search pattern to use, default is "sonic-installer: Installing image SONiC-OS-"
    :param match_rule: match the first or last line if there are multiple matches, default is 'head'
    :return: tuple (syslog_file, line_number, timestamp) or None if not found
    """
    search_pattern = "sonic-installer: Installing image SONiC-OS-" if search_pattern is None else search_pattern

    with allure.step('Finding sonic-installer log for upgrade start point'):
        logger.info(f'Searching for pattern: {search_pattern}')
        # Search all syslog files including .gz files, get first match
        cmd = f'sudo zgrep -Hn "{search_pattern}" /var/log/syslog* 2>/dev/null | {match_rule} -1'
        result = engine.run_cmd(cmd, validate=False)

        if result:
            # Result format: "file_path:line_number:log_content"
            columns = result.split(':', 2)
            syslog_file = columns[0]
            line_number = int(columns[1])
            timestamp = ' '.join(columns[2].split()[:4])
            return (syslog_file, line_number, timestamp)

        logger.warning(f'"{search_pattern}" log not found in any syslog file')
        return None


def insert_start_string_before_line(engine, syslog_file, line_number, start_string):
    """
    Insert start_string before the specified line in syslog file.
    Handles both regular and .gz compressed files.
    :param engine: dut engine object
    :param syslog_file: path to syslog file
    :param line_number: line number to insert before
    :param start_string: the start_string to insert
    """
    with allure.step(f'Inserting start_string before line {line_number} in {syslog_file}'):
        logger.info(f'Inserting start_string before line {line_number} in {syslog_file}')
        if syslog_file.endswith('.gz'):
            # For .gz files: decompress, edit, re-compress
            engine.run_cmd(f'sudo gunzip {syslog_file}')
            uncompressed_file = syslog_file[:-3]  # Remove .gz suffix
            engine.run_cmd(f"sudo sed -i '{line_number}i\\{start_string}' {uncompressed_file}")
            engine.run_cmd(f'sudo gzip {uncompressed_file}')
        else:
            engine.run_cmd(f"sudo sed -i '{line_number}i\\{start_string}' {syslog_file}")


def get_la_start_string(engine, request):
    """
    Get LogAnalyzer start string line and remove line which was added by LogAnalyzer at the beginning of current test
    :param engine: dut engine object
    :param request: pytest build-in
    :return: LogAnalyzer start_string line, example: r-lionfish-07 INFO start-LogAnalyzer-test_a.2022-05-16-13:49:02
    """
    test_name = request.node.name
    test_name = test_name.replace("[", r"\[")
    test_name = test_name.replace("]", r"\]")
    start = 'start-LogAnalyzer'
    start_prefix = start + '-' + test_name

    msg = 'Getting original LogAnalyzer start_string'
    with allure.step(msg):
        logger.info(msg)
        start_string_full_line = engine.run_cmd(f'sudo cat /var/log/syslog -n | grep "{start_prefix}"')
        # line example:  "   9	May 16 13:48:23.535689 r-lionfish-07 INFO start-LogAnalyzer-test_a.2022-05-16-13:49:02"
        start_string_line = ' '.join(start_string_full_line.split()[4:])
        start_string_line_number = start_string_full_line.split()[0]

    msg = 'Remove original LogAnalyzer start_string'
    with allure.step(msg):
        logger.info(msg)
        engine.run_cmd(f'sudo sed -i \'{start_string_line_number}d\' /var/log/syslog')

    return start_string_line


def get_oldest_syslog_id(engine):
    """
    Get oldest syslog file ID
    :param engine: dut engine
    :return: oldest syslog file ID
    """
    with allure.step('Getting oldest syslog file ID'):
        syslogs_list = engine.run_cmd('sudo ls /var/log/syslog*').split()
        list_of_file_ids = []
        for syslog_name in syslogs_list:
            for s in syslog_name.split('.'):
                if s.isdigit():
                    list_of_file_ids.append(int(s))
        # Get first element - which is bigger(oldest syslog file index) that other
        if not list_of_file_ids:
            # There is only one file: /var/log/syslog
            oldest_syslog_id = 0
        else:
            oldest_syslog_id = sorted(list_of_file_ids, reverse=True)[0]
        logger.info(f'Oldest syslog file id is: {oldest_syslog_id}')

    return oldest_syslog_id


def get_new_start_string(engine, oldest_syslog_id, start_string_line):
    """
    Get new LogAnalyzer start string with oldest timestamp inside
    :param engine: dut engine
    :param oldest_syslog_id: oldest syslog ID
    :param start_string_line: original LogAnalyzer start string line without timestamp
    :return: new LogAnalyzer start string with oldest timestamp inside,
    example: May 16 09:30:19 r-lionfish-07 INFO start-LogAnalyzer-test_a.2022-05-16-13:49:02
    """
    with allure.step('Get oldest syslog timestamp'):
        if oldest_syslog_id == 0:
            oldest_syslog_file = '/var/log/syslog'
        else:
            oldest_syslog_file = f'/var/log/syslog.{oldest_syslog_id}'
        file_reader = 'cat'
        if oldest_syslog_id > 1:
            oldest_syslog_file = oldest_syslog_file + '.gz'
            file_reader = 'zcat'

        oldest_syslog_line = engine.run_cmd(f'sudo {file_reader} {oldest_syslog_file} | head -1')
        # Add first 3 elements(oldest timestamp) at the beginning of new LogAnalyzer start string
        oldest_syslog_timestamp_string = ' '.join(oldest_syslog_line.split()[:3])

    with allure.step('Creating new start_string'):
        new_start_string = ' '.join([oldest_syslog_timestamp_string, start_string_line])
        logger.info(f'New start_string line is: {new_start_string}')

    return new_start_string


def insert_new_start_string(engine, oldest_syslog_id, new_start_string):
    """
    Insert new LogAnalyzer start string at the beginning of syslog entries(by creating new syslog.x.gz file
    with one line inside)
    :param engine: due engine
    :param oldest_syslog_id: oldest syslog id
    :param new_start_string: new LogAnalyzer start string
    """
    new_oldest_syslog_id = oldest_syslog_id + 1
    with allure.step(f'Inserting start_sting line into syslog file with ID: {new_oldest_syslog_id}'):
        engine.run_cmd(f'sudo echo \'{new_start_string}\' > syslog.{new_oldest_syslog_id}')
        if new_oldest_syslog_id > 1:
            engine.run_cmd(f'sudo gzip syslog.{new_oldest_syslog_id}')
            engine.run_cmd(f'sudo mv syslog.{new_oldest_syslog_id}.gz /var/log/')
        else:
            engine.run_cmd(f'sudo mv syslog.{new_oldest_syslog_id} /var/log/')

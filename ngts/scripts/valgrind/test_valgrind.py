#!/usr/bin/env python
import json
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import pytest
from ngts.cli_wrappers.common.general_clis_common import GeneralCliCommon
from ngts.cli_wrappers.sonic.sonic_general_clis import SonicGeneralCli
from ngts.helpers import system_helpers
from ngts.nvos_tools.infra import ExceptionTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.infra import get_dumps_folder

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.exceptions.test_issue import TestIssue

logger = logging.getLogger()

SRC_DIR = os.path.dirname(os.path.realpath(__file__))
VALGRIND_CONFIG_PATH = os.path.join(SRC_DIR, 'valgrind_config')
VALGRIND_DIR = '/valgrind/'
VALGRIND_OUT_FILE_NAME = 'vg.{}.out'
VALGRIND_OUT_FILE_PATH = VALGRIND_DIR + VALGRIND_OUT_FILE_NAME
VALGRIND_RUNNER = 'valgrind_runner'
VALGRIND_RUNNER_STAMP = '# VALGRIND_RUNNER'  # Used to differentiate between the wrapper and the original bin
VALGRIND_RUNNER_STAMP_LINE_NUM = 2  # The line number where the stamp is expected
VALGRIND_RUNNER_SRC_PATH = os.path.join(SRC_DIR, VALGRIND_RUNNER)
VALGRIND_RUNNER_PATH = os.path.join(VALGRIND_DIR, VALGRIND_RUNNER)
BACKUP_EXTENSION = '.backup'
IGNORE_PATH = str(Path(__file__).with_name('ignores') / 'ignore.{}.txt')

HOST_PROCESSES_KEY = 'host_processes'
DOCKER_PROCESSES_KEY = 'docker_processes'
NO_SERVICE_KEY = 'null'  # For processes that are not associated with any service

# These are all services on croc/mamba where we successfully run valgrind
SERVICE_LIST = ('aaastatsd.service', 'configmgrd.service', 'containerd.service', 'countermgrd.service', 'cron.service',
                'dbus.service', 'featured.service', 'getty@tty1.service', 'haveged.service', 'health-statsd.service',
                'hostcfgd.service', 'hw-management-sync.service',
                'nginx-authenticator.service', 'nginx.service', 'nvued.service', 'pam-auth.service',
                'portsyncmgrd.service', 'rasdaemon.service', 'rsyslog.service', 'serial-getty@ttyS0.service',
                'smartmontools.service', 'ssh.service', 'statemgrd.service', 'stats-reportd.service')


@pytest.fixture
def valgrind_config():
    """
    Reads the valgrind config file and returns the parsed dict.
    The valgrind config file is in json format. It describes the processes on
    which valgrind will run.
    Processes are either "host processes", which run directly on the host, or
    "docker processes", which run inside a Docker container.
    The processes are grouped by the service that uses them. When valgrind is
    installed/uninstalled, the corresponding service is restarted to apply.
    Host processes may be specified under the 'NO_SERVICE_KEY' ('null'), in
    which case no service will be restarted for them.
    """
    with open(VALGRIND_CONFIG_PATH) as valgrind_config_file:
        return json.load(valgrind_config_file)


@pytest.mark.disable_loganalyzer
def test_start_valgrind(engines):
    """ Configures the services in SERVICE_LIST to run through valgrind, and restarts them. """
    engine = engines.dut
    sudo_engine = system_helpers.PrefixEngine(engine, 'sudo')
    clear_valgrind_dir(sudo_engine)
    install_valgrind_package(sudo_engine)

    failed_to_edit_service = []
    with allure.step("Edit all .service files"):
        for service in SERVICE_LIST:
            try:
                configure_service_to_valgrind(sudo_engine, service)
            except BaseException as e:
                ExceptionTool.log_exception(e)
                failed_to_edit_service.append(service)

    if failed_to_edit_service:
        logger.error("Failed to edit the following services, check log for details: " + ' '.join(failed_to_edit_service))
    services_to_restart = sorted(set(SERVICE_LIST) - set(failed_to_edit_service))

    try:
        with allure.step("Restart services"):
            SonicGeneralCli(engine=sudo_engine).systemctl_restart(services_to_restart, daemon_reload=True)
    except TestIssue as e:
        ExceptionTool.log_exception(e, "Some services failed to restart")
        with allure.step(f"Attempting to restore services that failed to run with valgrind"):
            failed_services = sorted(re.findall(r'Job for (\S+) failed', str(e), re.IGNORECASE))
            for service in failed_services:
                restore_service(sudo_engine, service)
                try:
                    fail_log = engine.run_cmd(f"journalctl -xu {service}", validate=True)
                except BaseException as e:
                    fail_log = "Failed to collect journal: " + ExceptionTool.format_exception(e)
                allure.attach(service + ".log", fail_log)
            SonicGeneralCli(engine=sudo_engine).systemctl_restart(failed_services, daemon_reload=True)
    # todo: decide how to behave if valgrind fails to start for some services


@pytest.mark.disable_loganalyzer
def test_stop_valgrind(engines, setup_name, session_id, topology_obj):
    """
    Restores the services in SERVICE_LIST to non-valgrind operation and restarts them.
    Also attaches all valgrind output files to the allure report, under Valgrind Results step.
    """
    engine = engines.dut
    sudo_engine = system_helpers.PrefixEngine(engine, 'sudo')
    cli = SonicGeneralCli(engine=sudo_engine)
    try:
        with allure.step("Restore all services to non-valgrind"):
            for service in SERVICE_LIST:
                with allure.independent_step(service):
                    restore_service(sudo_engine, service)
            with allure.independent_step("run systemctl restart"):
                cli.systemctl_restart(SERVICE_LIST, daemon_reload=True)

    finally:
        with allure.step("Analyze valgrind output"):
            player_valgrind_dir = os.path.join(get_dumps_folder(setup_name, session_id, topology_obj), 'valgrind')
            Path(player_valgrind_dir).mkdir(parents=True, exist_ok=True)
            for service in SERVICE_LIST:
                file_name = VALGRIND_OUT_FILE_NAME.format(service)
                path_on_drive = os.path.join(player_valgrind_dir, file_name)
                path_on_switch = os.path.join(VALGRIND_DIR, file_name)
                with allure.independent_step(path_on_drive):
                    engine.copy_file(source_file=path_on_switch, dest_file=path_on_drive, file_system='/',
                                     direction='get', overwrite=True, verify_file=False)
                    leaks = LeakSummary.from_file(path_on_drive)
                    if not leaks.leaks:
                        continue

                    with allure.step(f'{len(leaks.leaks)} leaks found totaling {leaks.total_bytes} bytes. '
                                     f'Comparing against ignore-list'):
                        ignores = LeakSummary.read_ignore_list(IGNORE_PATH.format(service))
                        unexpected_leaks, unused_ignores = leaks.compare(ignores)
                        message = ''
                        for leak, count in unexpected_leaks.items():
                            message += format_leak_message(leak, count, ignores[leak])
                        if message:  # unexpected leaks were found - fail test
                            # Print items from the ignore list that were not found valgrind output. Basically we don't
                            # care about these, but if there are unexpected leaks then we want to have full context
                            # for analyzing them. In particular, it's possible the newly-found leak is essentially
                            # covered by the ignore-list, but was not matched because of some subtle difference.
                            if unused_ignores:
                                message += '\n\n' + '=' * 80 + '\n\n' + format_unused_ignores_message(unused_ignores)
                            raise AssertionError(message)


@pytest.mark.disable_loganalyzer
def test_install_valgrind(topology_obj, valgrind_config):
    """
    Wraps the requested processes by a valgrind runner.
    It installs the valgrind package if needed, then replaces each specified
    binary with a wrapper script which runs the original binary with valgrind.
    :param topology_obj: topology object fixture.
    :param valgrind_config: valgrind_config fixture.
    :raise AssertionError: in case of script failure.
    """
    install_uninstall_valgrind(topology_obj, valgrind_config, install=True)


@pytest.mark.disable_loganalyzer
def test_uninstall_valgrind(topology_obj, valgrind_config):
    """
    Returns the requested processes to run their original binaries.
    :param topology_obj: topology object fixture.
    :param valgrind_config: valgrind_config fixture.
    :raise AssertionError: in case of script failure.
    """
    install_uninstall_valgrind(topology_obj, valgrind_config, install=False)


def install_uninstall_valgrind(topology_obj, valgrind_config, install):
    """
    Installs/uninstalls valgrind for the requested processes.
    Install procedure wraps the requested processes by a valgrind runner.
    It installs the valgrind package if needed, then replaces each specified
    binary with a wrapper script which runs the original binary with valgrind.
    Uninstall procedure returns the requested processes to run their original binaries.
    :param topology_obj: topology object fixture.
    :param valgrind_config: valgrind_config fixture.
    :param install: boolean flag, whether to install (install=True) or uninstall (install=False)
    :raise AssertionError: in case of script failure.
    """
    try:
        engine = topology_obj.players['dut']['engine']
        sudo_engine = system_helpers.PrefixEngine(engine, 'sudo')

        if install:
            clear_valgrind_dir(sudo_engine)

            with allure.step(f'Copy valgrind runner onto host at {VALGRIND_RUNNER_PATH}'):
                engine.copy_file(source_file=VALGRIND_RUNNER_SRC_PATH,
                                 dest_file=os.path.basename(VALGRIND_RUNNER_PATH),
                                 file_system=os.path.dirname(VALGRIND_RUNNER_PATH),
                                 direction='put')

        services_to_restart = []

        host_processes = valgrind_config[HOST_PROCESSES_KEY]
        if host_processes:
            processes = flatten(host_processes.values())
            if install:
                with allure.step(f'Install valgrind on host processes: {processes}'):
                    install_valgrind(sudo_engine, processes)
            else:
                with allure.step(f'Uninstall valgrind on host processes: {processes}'):
                    uninstall_valgrind(sudo_engine, processes)

            services_to_restart.extend(service for service in host_processes.keys() if service != NO_SERVICE_KEY)

        docker_processes = valgrind_config[DOCKER_PROCESSES_KEY]
        if docker_processes:
            with allure.step('Verify containers are up: {}'.format(docker_processes.keys())):
                SonicGeneralCli(engine=engine).verify_dockers_are_up(docker_processes.keys())

            for (container, processes) in docker_processes.items():
                docker_exec_engine = system_helpers.PrefixEngine(engine, f'docker exec {container}')
                if install:
                    clear_valgrind_dir(docker_exec_engine)

                    with allure.step(f'Copy valgrind runner into {container} container at {VALGRIND_RUNNER_PATH}'):
                        SonicGeneralCli(engine=engine).copy_to_docker(container, VALGRIND_RUNNER_PATH, VALGRIND_RUNNER_PATH)

                    with allure.step(f'Install valgrind on {container} container processes: {processes}'):
                        install_valgrind(docker_exec_engine, processes)
                else:
                    with allure.step(f'Uninstall valgrind on {container} container processes: {processes}'):
                        uninstall_valgrind(docker_exec_engine, processes)

            services_to_restart.extend(docker_processes.keys())

        restart_services(engine, services_to_restart)

        if docker_processes:
            with allure.step('Verify containers are up: {}'.format(docker_processes.keys())):
                SonicGeneralCli(engine=engine).verify_dockers_are_up(docker_processes.keys())

    except Exception as err:
        raise AssertionError(err)


def flatten(l):
    """
    Flattens a list of lists
    :param l: a list of lists, e.g. [[1, 2], [3, 4], [5]]
    :return: the flattened list, e.g. [1, 2, 3, 4, 5]
    """
    return [item for sublist in l for item in sublist]


def clear_valgrind_dir(engine):
    """
    Clears the valgrind dir.
    :param engine: the engine to use, may use a PrefixEngine with prefix 'sudo'
        to act on the host, or with prefix 'docker exec <container>'
        to act on a Docker container.
    """
    with allure.step(f'Clear valgrind dir at {VALGRIND_DIR}'):
        GeneralCliCommon(engine=engine).rm(VALGRIND_DIR, flags='-rf')
        GeneralCliCommon(engine=engine).mkdir(VALGRIND_DIR, flags='-p')
        GeneralCliCommon(engine=engine).chmod_by_mode(VALGRIND_DIR, '777', flags='-R')


def install_valgrind_package(engine):
    """
    Installs valgrind package if it is not already installed.
    :param engine: the engine to use.
    """
    with allure.step("Install valgrind package"):
        if GeneralCliCommon(engine=engine).which('valgrind'):
            logger.info('Valgrind package is already installed, skipping...')
        else:
            GeneralCliCommon(engine=engine).apt_update()
            # due to a Debian dependency bug, libc6 must be downgraded to install valgrind
            GeneralCliCommon(engine=engine).apt_install('libc6=2.36-9+deb12u9', '-y --allow-downgrades')
            GeneralCliCommon(engine=engine).apt_install('valgrind', '-y')
            get_process_path(engine, 'valgrind')  # sanity check
            GeneralCliCommon(engine=engine).apt_install('python3.11-dbg', '-y')


def get_process_path(engine, process):
    """
    Returns the absolute path of a process, found by the 'which' command.
    :param engine: the engine to use.
    :param process: the process of which to get the absolute path.
    :return: the absolute path of the process.
    :raise Exception: if the process was not found.
    """
    path = GeneralCliCommon(engine=engine).which(process)
    if not path:
        raise Exception(f'Process {process} not found')
    return path


def install_valgrind(engine, processes):
    """
    Installs the valgrind package, and wraps processes with the valgrind runner.
    :param engine: the engine to use, may use a PrefixEngine with prefix 'sudo'
        to act on host processes, or with prefix 'docker exec <container>'
        to act on processes that run in a Docker container.
    :param processes: the list of processes to wrap with the valgrind runner.
    """
    install_valgrind_package(engine)

    with allure.step(f'Install valgrind for processes: {processes}'):
        for process in processes:
            process_path = get_process_path(engine, process)

            if is_valgrind_installed_for_process(engine, process_path):
                logger.info(f'Valgrind is already installed for process {process}, skipping...')
            else:
                new_process_path = f'{process_path}.bin'
                GeneralCliCommon(engine=engine).mv(process_path, new_process_path)
                GeneralCliCommon(engine=engine).cp(VALGRIND_RUNNER_PATH, process_path)
                GeneralCliCommon(engine=engine).chown_by_ref_file(process_path, new_process_path)
                GeneralCliCommon(engine=engine).chmod_by_ref_file(process_path, new_process_path)
                if not is_valgrind_installed_for_process(engine, process_path):
                    raise Exception(f'Failed to install valgrind for process {process}')


def uninstall_valgrind(engine, processes):
    """
    Returns the processes to run their original binaries.
    :param engine: the engine to use, may use a PrefixEngine with prefix 'sudo'
        to act on host processes, or with prefix 'docker exec <container>'
        to act on processes that run in a Docker container.
    :param processes: the list of processes to return to their original binaries.
    """
    with allure.step(f'Uninstall valgrind for processes: {processes}'):
        for process in processes:
            process_path = get_process_path(engine, process)

            if not is_valgrind_installed_for_process(engine, process_path):
                logger.info(f'Process {process} already uses its original binary, skipping...')
            else:
                orig_process_path = get_process_path(engine, f'{process_path}.bin')
                GeneralCliCommon(engine=engine).mv(orig_process_path, process_path)
                if is_valgrind_installed_for_process(engine, process_path):
                    raise Exception(f'Failed to uninstall valgrind for process {process}')


def is_valgrind_installed_for_process(engine, process_path):
    """
    Checks if valgrind is installed for a process. This is done by looking for
    a unique and well-known stamp which exists only in the valgrind runner.
    :param engine: the engine to use.
    :param process_path: the path to the process.
    :return: True if valgrind is installed for the process, False otherwise.
    """
    return VALGRIND_RUNNER_STAMP == GeneralCliCommon(engine=engine).sed(process_path, f'{VALGRIND_RUNNER_STAMP_LINE_NUM}q;d')


def restart_services(engine, services_to_restart):
    """
    Restart system services using service stop and start commands.
    We use explicit stop and start commands instead of a restart command, and
    we do it on each service one by one, to avoid bugs that may cause a
    "Job for <x>.service canceled" message to be printed.
    :param engine: the engine to use.
    :param services_to_restart: a list of services to restart
    """
    if services_to_restart:
        with allure.step(f'Restart system services: {services_to_restart}'):
            for service in services_to_restart:
                GeneralCliCommon(engine=engine).stop_service(service)
                system_helpers.wait_for_all_jobs_done(engine)

            for service in services_to_restart:
                GeneralCliCommon(engine=engine).start_service(service)
                system_helpers.wait_for_all_jobs_done(engine)


def get_services_and_dockers(engine: LinuxSshEngine):
    """
    A helper function to get all systemctl services, and to differentiate between services that run on dockers and
    those that don't. Valgrind should not run on the docker services because it should instead run inside the docker
    itself. Anyway this function is not currently used in code because the SERVICE_LIST const lists all the services
    for which we want to run valgrind.
    """
    services = engine.run_cmd("systemctl list-units --state=running | grep \\.service | awk '{print $1}'",
                              validate=True).splitlines()
    dockers = dict(line.split() for line in
                   engine.run_cmd("docker ps --format '{{.Names}} {{.Command}}' --no-trunc", validate=True
                                  ).splitlines())
    non_dockers = [s for s in services if not any([d in s.replace('@', '') for d in dockers])]
    logger.info(f"{services=}")
    logger.info(f"{dockers=}")
    logger.info(f"{non_dockers=}")
    return services, dockers, non_dockers


def configure_service_to_valgrind(engine, service_name):
    """
    Edits the .service file to run valgrind. After calling this function, one must restart the service for it to
    actually run valgrind.
    """
    with allure.step(f"Configure {service_name} file to run valgrind"):
        conf_file = get_conf_file(engine, service_name)
        line_number = engine.run_cmd(f"grep -nx '\\[Service]'  {conf_file} | cut -f1 -d:", validate=True)
        engine.run_cmd(f"""sed -i{BACKUP_EXTENSION} '{line_number}a Environment="PYTHONMALLOC=malloc"' {conf_file}""",
                       validate=True)
        engine.run_cmd(
            fr"sed -i -E 's|ExecStart=(.+)|ExecStart=valgrind --tool=memcheck --leak-check=full "
            fr"--log-file={VALGRIND_OUT_FILE_PATH.format(service_name)} \1|' {conf_file}",
            validate=True)
        try:
            engine.run_cmd(fr"sed -i -E 's|(ExecStart=.+) --daemon|\1|' {conf_file}", validate=True)
        except BaseException:
            restore_service(engine, service_name, conf_file)
            raise


def get_conf_file(engine, service):
    """Uses systemctl to obtain the service's .service file path."""
    out = engine.run_cmd(f"systemctl show {service} -P FragmentPath", validate=True).splitlines()[-1]
    allure.attach(out)
    return out


def restore_service(engine, service, conf_file=None):
    """Restores the .service file using the .backup file. This does not restart the service."""
    with allure.step(f"Restore {service} using {BACKUP_EXTENSION} file"):
        if not conf_file:
            conf_file = get_conf_file(engine, service)
        engine.run_cmd(f"ls {conf_file}{BACKUP_EXTENSION}", validate=True)  # assert .backup file exists
        engine.run_cmd(f"rm -f {conf_file}", validate=True)
        engine.run_cmd(f"mv {conf_file}{BACKUP_EXTENSION} {conf_file}", validate=True)


def restore_services(engine, services):
    """Restore all .service files using their .backup files. This does not restart the services."""
    restored = []
    failed = {}
    for service in services:
        conf_file = get_conf_file(engine, service)
        try:
            restore_service(engine, service, conf_file)
            restored.append(service)
        except Exception as e:
            failed[service] = ExceptionTool.format_exception(e)
    for s, e in failed.items():
        logger.error(f"{s}: {e}")
    return restored


@dataclass(frozen=True)
class Leak:
    text: str = field(compare=False)
    size: int = field(repr=False)
    stack: Tuple[str] = field(repr=False)
    title: str = field(compare=False)

    @staticmethod
    def from_log(lines: List[str]) -> 'Leak':
        return Leak(text=''.join(lines[1:]),
                    size=int(lines[0].split(maxsplit=2)[1].replace(',', '')),
                    title=lines[0].split(' ', 1)[-1],
                    stack=tuple(line.partition(':')[2] for line in lines[1:]))

    def __eq__(self, other):
        return self.size == other.size and self.stack == other.stack


@dataclass
class LeakSummary:
    leaks: List[Leak]
    total_bytes: int
    total_blocks: int

    @staticmethod
    def from_file(path: str) -> 'LeakSummary':
        """Parses a valgrind log file and returns a LeakSummary object."""
        leaks = []
        total_bytes, total_blocks = '-1', '-1'
        ARE_DEFINITELY_LOST = 'are definitely lost'
        SUMMARY = 'definitely lost:'
        with open(path) as f:
            while line := f.readline():
                if ARE_DEFINITELY_LOST in line:
                    lines = [line]
                    while line := f.readline():
                        if len(line.split()) < 2:
                            break
                        lines.append(line)
                    leaks.append(Leak.from_log(lines))
                elif SUMMARY in line:
                    total_bytes, total_blocks = re.search(r'([\d,]+) bytes in ([\d,]+) blocks', line).groups()
        return LeakSummary(leaks, int(total_bytes.replace(',', '')), int(total_blocks.replace(',', '')))

    @staticmethod
    def read_ignore_list(path: str):
        """Reads an ignore file (found in the 'ignores' directory) and returns a multiset (Counter) of expected leaks."""
        if os.path.exists(path):
            return Counter(LeakSummary.from_file(path).leaks)
        else:
            logger.warning(f"{path} doesn't exist, assuming an empty ignore list")
            return Counter()

    def compare(self, ignore_set: Counter) -> Tuple[Counter, Counter]:
        """
        Compares the leaks in the current LeakSummary with the expected leaks in the ignore_set.
        :param ignore_set: a multiset of expected leaks. "Multiset" means that we count the number of expected
        occurrences of each leak and compare against the number of found occurrences.
        :return: Counter of unexpected leaks, Counter of extra expected leaks that were not found.
        """
        unexpected_leaks = Counter(self.leaks) - ignore_set
        unused_ignores = ignore_set - Counter(self.leaks)
        return unexpected_leaks, unused_ignores


def format_leak_message(leak: 'Leak', count: int, ignore_count: int) -> str:
    return (f'Found {count} unexpected leaks of {leak.size} bytes each with the following stack trace' +
            (f'(in addition to {ignore_count} expected leaks of the same kind):\n' if ignore_count else ':\n') +
            leak.text + '\n')


def format_unused_ignores_message(unused_ignores: Counter) -> str:
    return '\n'.join(
        f'{count} more leaks of {leak.size} bytes with the following stack-trace were '
        f'expected but *NOT* encountered:\n' + leak.text
        for leak, count in unused_ignores.items()
    )

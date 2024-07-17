import time
import pytest
import logging
import re
from retry import retry

from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.Fae import Fae
from ngts.tests_nvos.system.test_system_health import verify_health_status_and_led
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import HealthConsts, SyslogConsts, SystemConsts
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.DutUtilsTool import wait_for_specific_regex_in_logs


logger = logging.getLogger(__name__)
# /etc/fae_platform_firmware/transceiver/
paths_order = ['/host/nos-images/', '/etc/fae_platform_firmware/ssd/', '/etc/fae_platform_firmware/cpld/',
               '/etc/fae_platform_firmware/bios/', '/host/stats/', '/var/stats/', '/host/dump/', '/var/core/',
               "/host/fw-images/"]


@pytest.mark.system
def test_ssd_cleanup_before_adding_files(engines, devices):
    """
    :summary:
    Test Flow:
        1. get ssd usage
        2. verify it's more threshold (5G)
        3. run nv action run fae system ssd-cleanup
        4. get ssd usage and verify it's still the same as before cleanup
        5. check logs - nothing has been deleted

    :param engines:
    :param devices:
    :return:
    """
    fae = Fae()
    ssd_usage_before_cleanup = _get_df_output(engines.dut)

    with allure.step("check usage is under threshold and the status is ok"):
        assert ssd_usage_before_cleanup[SystemConsts.SSD_SPACE_AVAILABLE_SIZE] >= 5, "can not complete the test, the SSD usage more than expected {}".format(ssd_usage_before_cleanup[SystemConsts.SSD_SPACE_USED_SIZE])

    with allure.step("try to cleanup SSD and verify nothing has been deleted"):
        fae.system.ssd_cleanup(expected_str='Action succeeded')
        ssd_usage_after_cleanup = _get_df_output(engines.dut)

        with allure.step("check usage is under threshold and the status is ok"):
            assert ssd_usage_after_cleanup == ssd_usage_before_cleanup, "at least one of the fields has been change, the usage before cleanup is {}, the usage after cleanup is {}".format(ssd_usage_before_cleanup, ssd_usage_after_cleanup)

        with allure.step("check no files deleted"):
            deleted_list = _get_deleted_files_list_from_logs(engines.dut)
            assert len(deleted_list) == 0, "no files should be deleted but the cleanup script deleted {}".format(deleted_list)


@pytest.mark.system
@pytest.mark.checklist
def test_ssd_cleanup_positive_flow(engines, devices):
    """
    :summary:
    Test Flow:
        1. add files until warning threshold (5G)
        1.5 wait 10-11 min
        2. verify health issue
        3. Run  nv action run fae system ssd-cleanup
        4. verify deleted files order
        5. verify health is ok
        6. add files until auto cleanup (3.5G)
        7. Run nv show system events and verify cleanup step
        7.5 search "INFO ssd_cleanup: SSD Cleanup Started" in the logs
        8. verify health
        9. verify deleting order

    :param engines:
    :param devices:
    :return:
    """
    with allure.step("create fae and system"):
        fae = Fae()
        system = System()

    _delete_all_files(engines.dut)
    file_path = '/etc/monit/conf.d/sonic-host'
    old_line = 'if status == 1 for 10 times within 20 cycles then alert repeat every 1 cycles'
    new_line = 'if status == 1 for 2 times within 20 cycles then alert repeat every 1 cycles'
    _change_monit_and_reload(engines.dut, old_line, new_line, file_path)

    try:
        df_output = _get_df_output(engines.dut)
        with allure.step("add file to reach usage threshold {}".format(5)):
            engines.dut.run_cmd(f"sudo fallocate -l {df_output[SystemConsts.SSD_SPACE_AVAILABLE_SIZE] - 5}G {paths_order[-1]}/big_file")

        files_to_delete = _add_files(engines.dut, 4, df_output[SystemConsts.SSD_SPACE_AVAILABLE_SIZE])

        with allure.step("health issue will be reported after 3 minutes"):
            time.sleep(180)

        with allure.step("check health status is not ok"):
            verify_health_status_and_led(system, HealthConsts.NOT_OK)
            issue = {
                'Disk space': {
                    "issue": "Not OK"
                }
            }
            health_dict = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).verify_result()
            temp = all(item in health_dict[HealthConsts.ISSUES].items() for item in issue.items())
            assert temp, "the expected issue is {} but the output is {}".format(issue, health_dict)

            with allure.step("check system events - two events expected "):
                events_dict = OutputParsingTool.parse_json_str_to_dictionary(system.events.show()).verify_result()
                _verify_system_event(events_dict, False)

        with allure.step("try to cleanup and verify health status and deleted files after it"):

            with allure.step("cleanup SSD"):
                fae.system.ssd_cleanup(expected_str='Action succeeded')

            with allure.step("check deleted files and the deleting order"):
                verify_deleted_folders_list(engines.dut, files_to_delete[:-2])

            with allure.step("check no disk issue"):
                time.sleep(120)
                health_dict = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).verify_result()
                temp = all(item in health_dict[HealthConsts.ISSUES].items() for item in issue.items())
                assert not temp, f"health issue still exist even after waiting for 120 seconds, health output: {health_dict}"

            with allure.step("check system events - two events expected "):
                events_dict = OutputParsingTool.parse_json_str_to_dictionary(system.events.show()).verify_result()
                _verify_system_event(events_dict, True)

        df_output = _get_df_output(engines.dut)
        file_name = 'Big_file'
        engines.dut.run_cmd('sudo fallocate -l {size}G /{path}/{file}'.format(size=df_output[SystemConsts.SSD_SPACE_AVAILABLE_SIZE] - 0.5, path=paths_order[0], file=file_name))

        with allure.step("check auto cleanup step"):
            with allure.step("check SSD Cleanup Started in the logs"):
                wait_for_specific_regex_in_logs(engines.dut, "ssd_cleanup: SSD Cleanup Done", timeout=70)

            with allure.step("Verify that deleted files are completely removed"):
                verify_deleted_folders_list(engines.dut, [file_name])
                assert "No such file or directory" in engines.dut.run_cmd(f"cat {paths_order[0]}/{files_to_delete[0]}"), f"{files_to_delete[0]} should be deleted"

            with allure.step("check health status is ok"):
                time.sleep(180)
                verify_health_status_and_led(system, HealthConsts.OK)
    finally:
        _delete_all_files(engines.dut)
        _change_monit_and_reload(engines.dut, new_line, old_line, file_path)


@pytest.mark.system
def test_ssd_cleanup_reboot_with_high_ssd_usage(engines, devices):
    """
    Test Flow:
        1. add one file to get 99% usage
        2. run nv action system reboot
        3. check health
        4. check serial logs

    :param engines:
    :param devices:
    :return:
    """

    system = System()
    _delete_all_files(engines.dut)
    df_output = _get_df_output(engines.dut)
    path = '/host/nos-images/'
    file_name = 'new_file'

    try:
        engines.dut.run_cmd('sudo fallocate -l {size}G /{path}/{file}'.format(size=df_output[SystemConsts.SSD_SPACE_AVAILABLE_SIZE] - 0.5, path=path, file=file_name))

        with allure.step('Reboot the system'):
            system.reboot.action_reboot()

        with allure.step('sleep 4 minutes - waiting for healthD cycle'):
            wait_for_specific_regex_in_logs(engines.dut, "ssd_cleanup: SSD Cleanup Done", timeout=250)

        with allure.step("check deleted files and the deleting order"):
            verify_deleted_folders_list(engines.dut, [file_name])

        with allure.step("check health status is ok"):
            with allure.step('sleep 2 minutes - waiting for healthD cycle'):
                time.sleep(120)

            verify_health_status_and_led(system, HealthConsts.OK)

        with allure.step("check ssd-cleanup deleted the {file}".format(file=file_name)):
            assert file_name not in engines.dut.run_cmd(f'ls {path}')
    finally:
        with allure.step(f"cleanup step - delete {file_name}"):
            engines.dut.run_cmd('sudo rm -f /{path}/{file}'.format(path=path, file=file_name))


def _add_files(engine, usage_threshold, available_space):
    """
    :summary:
        the method will add 2 files for each path in paths_order all same size
    :param engine:
    :param usage_threshold: available space after adding files
    :param available_space: available space before adding files
    :return: list of added files (with the adding order)
    """

    with allure.step("create new files to reach usage threshold {}".format(usage_threshold)):
        added_files_list = []

        size_each_file = 1000 / (2 * len(paths_order) - 1)
        file_size = f"{size_each_file}M"

        for i, path in enumerate(paths_order):
            file_name = f"new_file{i}"
            file_path = path + file_name

            with allure.step(f"adding {file_path} {file_path}.1 of size {file_size}"):
                engine.run_cmd(f"sudo fallocate -l {file_size} {file_path}")
                added_files_list.append(file_name)
                engine.run_cmd(f"sudo fallocate -l {file_size} {file_path}.1")
                added_files_list.append(file_name + '.1')

        logger.info(f"the current df command output is : {engine.run_cmd('df -h')}")
        return added_files_list


def _get_df_output(engine):
    """
    :summary:
        run command and parse it and return expected info
    :return:
    """
    with allure.step("run df command and parse the output into a dictionary"):
        df_output = engine.run_cmd('df -h | grep root-overlay')
        parts = df_output.split()
        result = {
            SystemConsts.SSD_SPACE_TOTAL_SIZE: float(parts[1][:-1]),
            SystemConsts.SSD_SPACE_USED_SIZE: float(parts[2][:-1]),
            SystemConsts.SSD_SPACE_AVAILABLE_SIZE: float(parts[3][:-1]),
            SystemConsts.SSD_SPACE_USAGE_PERCENTAGE: float(parts[4][:-1])
        }

        return result


def verify_deleted_folders_list(engine, files_to_delete):
    """
    :param engine:
    :param files_to_delete:
    :return:
    """
    with allure.step('compare the expected list to the deleted files list'):
        deleted_list = _get_deleted_files_list_from_logs(engine)
        it1 = iter(files_to_delete)
        for item in deleted_list:
            if item == next(it1, None):
                continue
        assert next(it1, None) is None, f"we expected to delete the files with this order: {files_to_delete}, but the deleting was in this order: {deleted_list}"


def _get_deleted_files_list_from_logs(engine, logs_history=200):
    """
    :summary:
        checking the system logs file to know the deleted files and the deleting order
    :param engine:
    :param logs_history:
    :return: deleted files list
    """
    with allure.step('Get the list of deleted files from logs'):
        logs_output = engine.run_cmd(f'tail -{logs_history} {SyslogConsts.SYSLOG_LOG_PATH}').splitlines()
        file_names = [line.split()[-1] for line in logs_output if "ssd_cleanup: Deleting" in line]

    return file_names


def _change_monit_and_reload(engine, old_line, new_line, file_path):
    """
    :summary:

    :param engine:
    :return:
    """
    with allure.step('Change monit and reload service'):
        engine.run_cmd(f"sudo sed -i 's/{old_line}/{new_line}/' {file_path}")
        engine.run_cmd('sudo monit reload')
        _wait_until_monit_is_running(engine)


def _delete_all_files(engine):
    """
    :summary:

    :param engine:
    :return:
    """
    with allure.step('Delete all files under this list of paths: {}'.format(paths_order)):
        for path in paths_order:
            logger.info(f"Deleting files under {path}")
            engine.run_cmd(f"sudo rm -rf {path}")
            cmd = f"sudo bash -c 'if [ ! -d '{path}' ]; then mkdir -p '{path}'; fi'"
            engine.run_cmd(cmd)
            logger.info(f"done with {path}")


def get_status_of_program(output, program_name):
    pattern = rf"Program '{program_name}'\s*[\s\S]*?status\s*([^\n]*)"
    match = re.search(pattern, output)
    if match:
        return match.group(1).strip()
    else:
        return None


@retry(Exception, tries=12, delay=10)
def _wait_until_monit_is_running(engine):
    """

    :param engine:
    :return:
    """
    with allure.step("check monit status"):
        output = engine.run_cmd('sudo monit status')
        monit_status = get_status_of_program(output, "root-overlay")
        if "Status ok" not in monit_status:
            raise Exception("Waiting for monit to finish initializing")


def _verify_system_event(events_output, is_ok):
    """

    :param events_output:
    :param is_ok:
    :return:
    """
    with allure.step("create expected events"):
        expected_disk_issue_event = {'severity': 'INFORMATIONAL' if is_ok else 'WARNING', 'text': 'Service goes back to normal' if is_ok else 'Disk space is not Status ok', 'type-id': 'Disk space'}
        expected_health_issue_event = {'severity': 'INFORMATIONAL' if is_ok else 'WARNING', 'text': 'Health status is ok' if is_ok else 'Health status is not ok', 'type-id': 'System'}

    with allure.step("get last two system events"):
        health_event = events_output['last']
        keys_list = list(map(int, health_event.keys()))
        keys_list_sorted = sorted(keys_list)
        system_health_event = health_event[str(keys_list_sorted[-1])]
        system_health_event.pop('time-created')
        disk_event = health_event[str(keys_list_sorted[-2])]
        disk_event.pop('time-created')

    with allure.step("verify health event"):
        assert expected_health_issue_event == system_health_event, f"the expected dic is {expected_health_issue_event} but the event output is {system_health_event}"

    with allure.step("verify disk issue event"):
        assert expected_disk_issue_event == disk_event, f"the expected dic is {expected_disk_issue_event} but the event output is {disk_event}"

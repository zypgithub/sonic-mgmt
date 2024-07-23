import allure
import os
import pytest
import time
from retry.api import retry_call
import re
import logging
import tarfile
from infra.tools.redmine.redmine_api import is_redmine_issue_active
from ngts.helpers.sonic_branch_helper import get_sonic_branch

logger = logging.getLogger(__name__)

SUCCESS_CODE = 0

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
FILES_DIR = os.path.join(BASE_DIR, 'files')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
SDK_DUMP_DIR = '/var/log/mellanox/sdk-dumps'
FW_EVENTS_DICT = {"FW_HEALTH_EVENT": 1, "PLL_LOCK_EVENT": 6}
HEALTH_CHECK_INJECT_FILE_PATH = '/proc/mlx_sx/sx_core'


@pytest.mark.disable_loganalyzer
@allure.title('Tests that DumpMeNow dump contains all the expected dumps when fw stuck occurs')
def test_techsupport_fw_stuck_dump(topology_obj, loganalyzer, engines, cli_objects):
    duthost = engines.dut
    chip_type = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['chip_type']

    pre_stuck_dumps = duthost.run_cmd('ls -t {}/*.tar | wc -l'.format(SDK_DUMP_DIR))
    if "No such file or directory" in pre_stuck_dumps:
        pre_stuck_dumps = '0'

    try:
        with allure.step('Trigger fw fatal event'):
            duthost.run_cmd("echo health_check_trigger sx_dbg_test_fw_fatal_event 1 > /proc/mlx_sx/sx_core")

        with allure.step('Wait for DumpMe dump to be created'):
            retry_call(
                verify_sdkdump_created,
                fargs=[duthost, pre_stuck_dumps],
                tries=30,
                delay=10,
                logger=logger,
            )

        with allure.step('Validate that the DumpMe dump contain all of the SDK extended dump files'):
            check_all_dumps_file_exsits(topology_obj, duthost, chip_type)

        # with allure.step('Count number of SDK extended dumps on dut after stuck occurred'):
        #     number_of_sdk_error_after = generate_tech_support_and_count_sdk_dumps(duthost)
        #     assert number_of_sdk_error_after == pre_stuck_dumps + 1
    except Exception as err:
        raise err
    finally:
        with allure.step('Rebooting the system - necessary to restart the iRISCs'):
            cli_objects.dut.general.reboot_reload_flow(topology_obj=topology_obj)


@pytest.mark.parametrize("fw_event", ["FW_HEALTH_EVENT", "PLL_LOCK_EVENT"])
def test_techsupport_mellanox_sdk_dump(topology_obj, engines, cli_objects, loganalyzer, fw_event):
    duthost = engines.dut
    logger.info("Health event generated is {}".format(fw_event))
    event_id = FW_EVENTS_DICT[fw_event]
    with allure.step('Copy to dut a script that triggers SDK health event'):
        cp_sdk_event_trigger_script_to_dut_syncd(duthost)

    logger.debug("Running show techsupport ... ")
    with allure.step('STEP1: Count number of SDK extended dumps at dut before test'):
        number_of_sdk_error_before = generate_tech_support_and_count_sdk_dumps(duthost)

    with allure.step('STEP2: Trigger SDK health event at dut'):
        duthost.run_cmd('docker exec -it syncd python mellanox_sdk_trigger_event_script.py --fw_event {}'.format(event_id))
        for dut in loganalyzer:
            loganalyzer[dut].expect_regex.extend(["Health event happened, severity"])
            ignoreRegex = [
                r".*SX_HEALTH_FATAL Detected with cause : FW health issue.*",
                r".*SDK health event, device.*",
                r".*FW health.*stopping further device monitoring.*",
                r".*on_switch_shutdown_request: Syncd stopped.*",
                r".*ERROR - Read PWM error. Possible hw-management is not running.*",
                r".*SX_HEALTH_FATAL: cause_string = \[FW health issue\].*",
                r".*SX_HEALTH_FATAL: cause_string.*error msg generated from SDK.*",
                r".*Failed command read at communication channel: Connection reset by peer.*",
                r".*mlnx_switch_health_event_handle: Health event happened.*"
            ]
            if fw_event == "PLL_LOCK_EVENT":
                ignoreRegex.extend([
                    r".*SXD_HEALTH_FW_FATAL: FW Fatal:fw_cause.*",
                    r".*SX_HEALTH_FATAL: cause_string = \[PLL lock failure\].*",
                    r".*Failed command read at communication channel: Connection reset by peer.*",
                    r".*SXD_HEALTH_FATAL:\s?On device \d+ cause =\'PLL lock failure\'.*",
                    r".*PLL lock failure.*further device monitoring.*"
                ])
            loganalyzer[dut].ignore_regex.extend(ignoreRegex)
    with allure.step('STEP3: Count number of SDK extended dumps at dut after event occurred'):
        number_of_sdk_error_after = generate_tech_support_and_count_sdk_dumps(duthost)

    with allure.step('Validate that the techsupport file contain one more SDK extended dump'):
        assert number_of_sdk_error_after == number_of_sdk_error_before + 1

    with allure.step('Reload switch'):
        cli_objects.dut.general.reload_flow(topology_obj=topology_obj, reload_force=True)


@allure.title('Tests that health check event dump contains all the expected dumps when health check event occurs')
def test_techsupport_health_event_sdk_dump(topology_obj, loganalyzer, engines, cli_objects):
    duthost = engines.dut
    chip_type = topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['chip_type']
    pre_stuck_dumps = duthost.run_cmd('ls -t {}/*.tar | wc -l'.format(SDK_DUMP_DIR))
    if "No such file or directory" in pre_stuck_dumps:
        pre_stuck_dumps = '0'

    try:
        with allure.step('Verify Health-Check: Trigger SYSFS failure appears in syslog'):
            for dut in loganalyzer:
                loganalyzer[dut].expect_regex.extend(["Health-Check: Trigger SYSFS failure"])
                ignoreRegex = [
                    r".*mlnx_switch_health_event_handle: Health event happened.*HW catastrophic.*"
                    r"event",
                    r"on_switch_shutdown_request: Syncd stopped",
                    r".*Sysfs running counter is not updated for more than \d+ sec.*"
                ]
                loganalyzer[dut].ignore_regex.extend(ignoreRegex)

        with allure.step('Generate health check trigger event'):
            duthost.run_cmd(f'sudo echo health_check_trigger sysfs > {HEALTH_CHECK_INJECT_FILE_PATH}')

        with allure.step('Get health_check_running_counter after trigger event'):
            health_check_counter_after_event_triggered = int(get_health_check_running_counter(duthost))

        with allure.step('Wait for health check dump to be created'):
            retry_call(
                verify_sdkdump_created,
                fargs=[duthost, pre_stuck_dumps],
                tries=30,
                delay=10,
                logger=logger,
            )

        with allure.step('Get health_check_running_counter after dumps generated'):
            health_check_counter_after_dump_generated = int(get_health_check_running_counter(duthost))

        with allure.step('Get health_check_running_counter after dump generated'):
            assert (health_check_counter_after_dump_generated < health_check_counter_after_event_triggered,
                    "Health check counter was not restarted")

        with allure.step('Validate that the health check dump contain all of the SDK extended dump files'):
            check_all_dumps_file_exsits(topology_obj, duthost, chip_type)

        with allure.step("Verify basic container is up before orchagent core dump generated"):
            cli_objects.dut.general.verify_dockers_are_up()

    except Exception as err:
        raise err

    finally:
        with allure.step('Reload switch'):
            cli_objects.dut.general.reload_flow(topology_obj=topology_obj, reload_force=True)


def cp_sdk_event_trigger_script_to_dut_syncd(engine):
    dst = os.path.join('/tmp', 'mellanox_sdk_trigger_event_script.py')
    engine.copy_file(source_file=os.path.join(FILES_DIR, 'mellanox_sdk_trigger_event_script.py'),
                     dest_file='mellanox_sdk_trigger_event_script.py',
                     file_system='/tmp',
                     direction='put'
                     )
    engine.run_cmd('docker cp {} {}'.format(dst, 'syncd:/'))


def generate_tech_support_and_count_sdk_dumps(engine):
    sdk_dump_dir = 'sai_sdk_dump'
    sdk_file_pattern = 'sai-dfw-.*'

    output_lines = engine.run_cmd('show techsupport').split('\n')

    tar_file = output_lines[len(output_lines) - 1]
    tarball_file_name = str(tar_file.replace('/var/dump/', ''))
    tarball_dir_name = str(tarball_file_name.replace('.tar.gz', ''))

    sdk_dump_pattern = '{}/{}/{}'.format(tarball_dir_name, sdk_dump_dir, sdk_file_pattern)

    engine.copy_file(source_file=tar_file, dest_file=tarball_file_name, file_system='/tmp/', direction='get')

    t = tarfile.open(tarball_file_name, "r")

    filenames = t.getnames()
    r = re.compile(sdk_dump_pattern)

    after_list = list(filter(r.match, filenames))

    engine.run_cmd("sudo rm -rf {}".format(tar_file))
    return len(after_list)


def verify_sdkdump_created(engine, before):
    after = engine.run_cmd('ls -t {}/*.tar | wc -l'.format(SDK_DUMP_DIR))
    assert "No such file or directory" not in after and after > before, 'Did not create DumpMe dump'


def stop_irisics(chip_type, host):
    if chip_type == 'SPC':
        host.run_cmd('sudo mcra /dev/mst/mt52100_pci_cr0 0xa01e4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt52100_pci_cr0 0xa05e4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt52100_pci_cr0 0xa07e4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt52100_pci_cr0 0xa09e4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt52100_pci_cr0 0xa0be4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt52100_pci_cr0 0xa0de4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt52100_pci_cr0 0xa0fe4 0x10')
    elif chip_type == 'SPC2':
        host.run_cmd('sudo mcra /dev/mst/mt53100_pci_cr0 0xa01e4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53100_pci_cr0 0xa05e4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53100_pci_cr0 0xa07e4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53100_pci_cr0 0xa09e4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53100_pci_cr0 0xa0be4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53100_pci_cr0 0xa0de4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53100_pci_cr0 0xa0fe4 0x10')
    elif chip_type == 'SPC3':
        host.run_cmd('sudo mcra /dev/mst/mt53104_pci_cr0 0xa01c4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53104_pci_cr0 0xa05c4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53104_pci_cr0 0xa07c4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53104_pci_cr0 0xa09c4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53104_pci_cr0 0xa0bc4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53104_pci_cr0 0xa0dc4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53104_pci_cr0 0xa0fc4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53104_pci_cr0 0xa11c4 0x10')
        host.run_cmd('sudo mcra /dev/mst/mt53104_pci_cr0 0xa11c4 0x10')
    else:
        raise ValueError("Not supported chip type: {}".format(chip_type))


def check_all_dumps_file_exsits(topology_obj, engine, chip_type):
    # DumpMe dumps should contain the following dumps:
    # 3 CR space dumps
    # SDK dump
    # mlxtrace dump
    # FW core dump - only on FW event from level CRITICAL or ERROR
    sonic_branch = get_sonic_branch(topology_obj)
    # Some files name are changed after the SDK 2000, now 202211 include the SDK older than 2000
    branch_with_old_sdk = ['202211']
    latest_fw_dump = engine.run_cmd('ls -t {}/*.tar | head -1'.format(SDK_DUMP_DIR))
    output_fw_dump = engine.run_cmd('sudo tar -tf {}'.format(latest_fw_dump))

    # Check CR space dump:
    sdk_dump = "sdkdump" if sonic_branch in branch_with_old_sdk else "sdk_dump"
    assert len(re.findall(fr'{sdk_dump}_ext_.*cr_space.*.udmp', output_fw_dump)) == 3, 'Missing CR space dump'

    # Check SDK dump:
    assert 'sai_sdk_dump.txt' in output_fw_dump, 'Missing SDK dump'
    # Check mlxtrace dump:
    if not (is_redmine_issue_active([3587386]) and chip_type == "SPC4"):
        if sonic_branch in branch_with_old_sdk:
            assert '_pci_cr0_mlxtrace.trc' in output_fw_dump, 'Missing mlxtrace'
        else:
            assert re.search(r'sdk_dump_ext_.*fw_trace.txt', output_fw_dump) is not None, 'Missing FW trace'
    # Check FW core dump:
    # This should be uncommented when FW stuck event level would change to critical
    # assert 'ir_core_dump_' in output, 'Missing FW core dump'


def get_health_check_running_counter(engine):
    health_check_counter_file_path = "/sys/module/sx_core/health_check_running_counter"
    return engine.run_cmd(f"sudo cat {health_check_counter_file_path}")

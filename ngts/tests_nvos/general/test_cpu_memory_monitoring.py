import pytest
import logging
import random
import time
import re
import json
from datetime import datetime, timedelta
from retry import retry

from ngts.nvos_constants.constants_nvos import DatabaseConst
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.constants.constants import GnmiConsts
from ngts.tests_nvos.constants import MINUTE
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Fae import Fae
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.nvos_tools.infra.Tools import Tools
from ngts.tests_nvos.system.clock.ClockTools import ClockTools
from ngts.tests_nvos.conftest import devices
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


CPU_WARNING_THRESHOLD = "cpu-warning-threshold"
CPU_RESTARTS_THRESHOLD = "cpu-restart-threshold"
MEMORY_WARNING_THRESHOLD = "memory-warning-threshold"
MEMORY_RESTART_THRESHOLD = "memory-restart-threshold"
NUMBER_OF_SAMPLES = "number-of-samples"

DEFAULT_VALUES = {CPU_WARNING_THRESHOLD: 50,
                  CPU_RESTARTS_THRESHOLD: 100,
                  MEMORY_WARNING_THRESHOLD: 90,
                  MEMORY_RESTART_THRESHOLD: 95,
                  NUMBER_OF_SAMPLES: 5}

WARNING_MSG_PATTERN = r"WARNING cpu_memory_container_checker: (Memory|CPU) usage ([0-9]+(\.[0-9]+))% is above expected threshold ([0-9]+)%"
HIGH_USAGE_EVENT_MSG_PATTERN = r"NOTICE cpu_memory_container_checker: :- publish: EVENT_PUBLISHED:.*\"resource\":\"{}\".*\"text\":\"(Memory|CPU) usage ([0-9]+(\.[0-9]+))% is above expected threshold ([0-9]+)%\""
GENERATING_TECH_SUPPORT_MSG_PATTERN = r"INFO cpu_memory_container_checker: Generating techsupport"
TECH_SUPPORT_GENERATED_MSG_PATTERN = r"INFO cpu_memory_container_checker: Generated techsupport"
NO_TECH_SUPPORT_GENERATED_MSG_PATTERN = r"INFO cpu_memory_container_checker: Techsupport already generated in the last 1440 minutes"
RESTARTING_DOCKER_MSG_PATTERN = r"INFO cpu_memory_container_checker: Restarting .* '{}'"
DOCKER_RESTARTED_MSG_PATTERN = r"INFO cpu_memory_container_checker: Restarted .* '{}'"
BACK_TO_NORMAL_USAGE_MSG_PATTERN = r"INFO cpu_memory_container_checker: (Memory|CPU) usage is back to normal"
NORMAL_USAGE_EVENT_MSG_PATTERN = r"NOTICE cpu_memory_container_checker: :- publish: EVENT_PUBLISHED:.*\"resource\":\"{}\".*\"text\":\"(Memory|CPU) usage is back to normal\""


@pytest.mark.timeout(5 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_configuration_cli(engines, devices, test_api):
    """
        @summary: check 'CPU/memory monitoring' functionality

        Test flow:
        1. Verify that feature is enabled: "nv show fae system control dockers resource-limit"
        2. Disable feature: "nv set fae system control dockers resource-limit state disabled"
        3. Enable feature: "nv set fae system control dockers resource-limit state enabled"
        4. Randomize memory-threshold from list ["memory-warning-threshold", "memory-restart-threshold"]
        5. Change memory-threshold: "nv set fae system control dockers resource-limit <selected memory threshold> <new-threshold>"
        6. Randomize cpu-threshold from list ["cpu-warning-threshold", "cpu-restart-threshold"]
        7. Change cpu-threshold: "nv set fae system control dockers resource-limit <selected cpu threshold> <new-threshold>"
        8. Change sample-number: "nv set fae system control dockers resource-limit number-of-samples <new-sample-number>"
        9. Randomize a docker form monitored dockers list
        10. Change memory-warning-threshold for the selected docker in config_db and verify output
        11. Change memory-restart-threshold for the selected docker in config_db and verify output
        12. Change cpu-warning-threshold for the selected docker in config_db and verify output
        13. Change cpu-restart-threshold for the selected docker in config_db and verify output
        14. Change sample-number for the selected docker in config_db and verify output
        15. Set thresholds to default values
    """
    TestToolkit.tested_api = test_api
    fae = Fae()
    cluster = Cluster()
    changed_configurations = []

    try:
        with allure.step("Run 'nv show fae system control dockers resource-limit' command and verify feature is enabled"):
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(fae.system.resource_limit.show()).verify_result()
            assert output_dict["state"] == NvosConst.ENABLED, "CPU/memory monitoring feature is unexpectedly disabled"

        with allure.step("Disable feature and verify"):
            enable_feature_and_verify(False)

        with allure.step("Enable feature and verify"):
            enable_feature_and_verify()

        memory_thresholds = [MEMORY_WARNING_THRESHOLD, MEMORY_RESTART_THRESHOLD]
        with allure.step(f"Randomize memory threshold from list: {memory_thresholds}"):
            tested_threshold = random.choice(memory_thresholds)

        with allure.step(f"Change {tested_threshold} value and verify"):
            new_memory_threshold = randomize_new_value(limit=tested_threshold,
                                                       curr_value=output_dict[tested_threshold])
            set_value_and_verify(limit=tested_threshold, new_value=new_memory_threshold)
            changed_configurations.append(tested_threshold)

        cpu_thresholds = [CPU_WARNING_THRESHOLD, CPU_RESTARTS_THRESHOLD]
        with allure.step(f"Randomize CPU threshold from list: {cpu_thresholds}"):
            tested_threshold = random.choice(cpu_thresholds)

        with allure.step(f"Change {tested_threshold} value and verify"):
            new_cpu_threshold = randomize_new_value(limit=tested_threshold,
                                                    curr_value=output_dict[tested_threshold])
            set_value_and_verify(limit=tested_threshold, new_value=new_cpu_threshold)
            changed_configurations.append(tested_threshold)

        with allure.step(f"Change number of samples"):
            new_sample_number = randomize_new_value(limit=NUMBER_OF_SAMPLES,
                                                    curr_value=output_dict[NUMBER_OF_SAMPLES])
            set_value_and_verify(limit=NUMBER_OF_SAMPLES, new_value=new_sample_number)
            changed_configurations.append(NUMBER_OF_SAMPLES)

        with allure.step("Check if device has NMX"):
            has_nmx = getattr(devices.dut, "has_nmx", False)
            if not has_nmx:
                logger.info("Device does not have NMX")
            else:
                with allure.step("Device has NMX - Start cluster"):
                    cluster.set(op_param_name="state", op_param_value='enabled', apply=True)
                    ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled',
                                                                     nmx_c_expected_state='up')

        with allure.step("Verify monitored dockers list includes all potential dockers"):
            init_monitored_dockers_list(devices, has_nmx, output_dict)

        with allure.step(f"Randomize a docker from monitored dockers list"):
            monitored_dockers_list = [item.strip() for item in output_dict["monitored-list"].split(",")]
            docker = random.choice(monitored_dockers_list)
            logger.info(f"Selected docker: {docker}")

        for limit in DEFAULT_VALUES.keys():
            with allure.step(f"Change {limit} for {docker}"):
                set_value_for_docker_and_verify(engines, limit, docker)

    finally:
        with allure.step("Disable cluster in case device has NMX"):
            if has_nmx:
                Cluster().unset(apply=True)
                ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled',
                                                                 nmx_c_expected_state='down')
        with allure.step(f"Set thresholds to default values"):
            for limit in changed_configurations:
                set_value_and_verify(limit, DEFAULT_VALUES[limit])


@pytest.mark.timeout(15 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_high_memory_usage_simulation(engines, devices, test_api):
    """
        @summary: simulate high memory usage and test feature functionality

        Test flow:
        1. Verify that feature is enabled: run "nv show fae system control dockers resource-limit"
        2. Start cluster for NVL systems
        3. Randomize a docker form monitored dockers list
        4. Change memory-warning-threshold: "nv set fae system control dockers resource-limit memory-warning-threshold 15"
        5. Simulate high memory usage for selected docker
        6. Verify events in events table
        7. Verify there is a warning message in logs describing high memory usage
        8. Change memory-restart-threshold: "nv set fae system control dockers resource-limit memory-restart-threshold 15"
        9. Verify events in events table
        10. Verify there is a warning message in logs describing high memory usage
        11. Verify docker was restarted
        12. Verify tech-support file was generated
        13. Simulate high memory usage again
        12. Verify no new tech-support file was generated
        13. Set thresholds to default values
    """
    TestToolkit.tested_api = test_api
    fae = Fae()
    cluster = Cluster()
    changed_configurations = []

    try:
        with allure.step("Run 'nv show fae system control dockers resource-limit' command and verify feature is enabled"):
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(fae.system.resource_limit.show()).verify_result()
            assert output_dict["state"] == NvosConst.ENABLED, "CPU/memory monitoring feature is unexpectedly disabled"

        with allure.step("Check if device has NMX"):
            has_nmx = getattr(devices.dut, "has_nmx", False)
            if not has_nmx:
                logger.info("Device does not have NMX")
            else:
                with allure.step("Device has NMX - Start cluster"):
                    cluster.set(op_param_name="state", op_param_value='enabled', apply=True)
                    ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled',
                                                                     nmx_c_expected_state='up')

        with allure.step("Verify monitored dockers list includes all potential dockers"):
            init_monitored_dockers_list(devices, has_nmx, output_dict)

        with allure.step(f"Randomize a docker from monitored dockers list"):
            monitored_dockers_list = [item.strip() for item in output_dict["monitored-list"].split(",")]
            docker = random.choice(monitored_dockers_list)
            logger.info(f"Selected docker: {docker}")

        with allure.step(f"Change {MEMORY_WARNING_THRESHOLD} and start high memory usage simulation"):
            new_memory_threshold = 15
            set_value_and_verify(limit=MEMORY_WARNING_THRESHOLD, new_value=new_memory_threshold)
            changed_configurations.append(MEMORY_WARNING_THRESHOLD)
            simulate_and_verify_high_memory_usage(engines, devices, docker, warning_phase=True)

        with allure.step(f"Change {MEMORY_RESTART_THRESHOLD} and start another high memory simulation"):
            new_memory_threshold = 15
            set_value_and_verify(limit=MEMORY_RESTART_THRESHOLD, new_value=new_memory_threshold)
            changed_configurations.append(MEMORY_RESTART_THRESHOLD)
            simulate_and_verify_high_memory_usage(engines, devices, docker)

        with allure.step(f"Simulate high memory usage again and verify no new tech-support file was generated"):
            verify_no_new_tech_support_on_repeated_high_usage(engines, docker)

    finally:
        with allure.step("Disable cluster in case device has NMX"):
            if has_nmx:
                Cluster().unset(apply=True)
                ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled',
                                                                 nmx_c_expected_state='down')
        with allure.step(f"Set thresholds to default values"):
            for limit in changed_configurations:
                set_value_and_verify(limit=limit, new_value=DEFAULT_VALUES[limit])


@pytest.mark.timeout(10 * MINUTE, func_only=True)
@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_high_cpu_usage_simulation(engines, devices, test_api):
    """
        @summary: simulate high cpu usage and test feature functionality

        Test flow:
        1. Verify that feature is enabled: "nv show fae system control dockers resource-limit"
        2. Start cluster for NVL systems
        3. Randomize a docker form monitored dockers list
        4. Change cpu-threshold: "nv set fae system control dockers resource-limit cpu-warning-threshold 10"
        5. Simulate high cpu usage for selected docker
        6. Verify events in events table
        7. Verify there is a warning message in logs describing high cpu usage
    """
    TestToolkit.tested_api = test_api
    fae = Fae()
    cluster = Cluster()
    changed_configurations = []

    try:
        with allure.step("Run 'nv show fae system control dockers resource-limit' command and verify feature is enabled"):
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(fae.system.resource_limit.show()).verify_result()
            assert output_dict["state"] == NvosConst.ENABLED, "CPU/memory monitoring feature is unexpectedly disabled"

        with allure.step("Check if device has NMX"):
            has_nmx = getattr(devices.dut, "has_nmx", False)
            if not has_nmx:
                logger.info("Device does not have NMX")
            else:
                with allure.step("Device has NMX - Start cluster"):
                    cluster.set(op_param_name="state", op_param_value='enabled', apply=True)
                    ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled',
                                                                     nmx_c_expected_state='up')

        with allure.step("Check dockers in monitored dockers list"):
            init_monitored_dockers_list(devices, has_nmx, output_dict)

        with allure.step(f"Randomize a docker from monitored dockers list"):
            monitored_dockers_list = [item.strip() for item in output_dict["monitored-list"].split(",")]
            docker = random.choice(monitored_dockers_list)
            logger.info(f"Selected docker: {docker}")

        with allure.step(f"Change {CPU_WARNING_THRESHOLD}"):
            new_cpu_threshold = 10
            set_value_and_verify(limit=CPU_WARNING_THRESHOLD, new_value=new_cpu_threshold)
            changed_configurations.append(CPU_WARNING_THRESHOLD)

        with allure.step(f"Simulate high CPU usage on {docker}"):
            start_time = datetime.now()
            simulate_high_cpu_usage(engines, devices, docker)

        with allure.step("Sleeping for 1.5 min"):
            time.sleep(1.5 * MINUTE)

        with allure.step("Verify behavior after high CPU usage"):
            verify_behavior_after_simulation(engines, devices, resource="cpu", docker=docker, start_time=start_time)

    finally:
        with allure.step("Disable cluster in case device has NMX"):
            if has_nmx:
                Cluster().unset(apply=True)
                ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled',
                                                                 nmx_c_expected_state='down')
        with allure.step("Set thresholds to default value"):
            for limit in changed_configurations:
                set_value_and_verify(limit=limit, new_value=DEFAULT_VALUES[CPU_WARNING_THRESHOLD])


def randomize_new_value(limit, curr_value):
    """
        Helper function to randomize new value for resource.
    """
    if limit == "number-of-samples":
        new_value = random.choice([num for num in range(1, 21) if num != int(curr_value)])
    else:
        new_value = random.choice([num for num in range(DEFAULT_VALUES[limit], 101)])
    return new_value


def enable_feature_and_verify(status=True):
    """
        Helper function to enable/disable the CPU/memory monitoring feature.
    """
    state = NvosConst.ENABLED if status else NvosConst.DISABLED

    Fae().system.resource_limit.set(op_param_name="state", op_param_value=state, apply=True).verify_result()
    show_and_verify(attribute="state", expected_value=state)


def set_value_and_verify(limit, new_value):
    """
        Helper function to set a resource value and verify it.
    """
    with allure.step(f"Set {limit} to be {new_value} and verify threshold changed as expected"):
        Fae().system.resource_limit.set(op_param_name=limit, op_param_value=new_value, apply=True).verify_result()
        show_and_verify(attribute=limit, expected_value=str(new_value))


def show_and_verify(attribute, expected_value):
    """
        Helper function to show output of "nv show fae system control dockers resource-limit" command, and verify it.
    """
    output_dict = OutputParsingTool.parse_json_str_to_dictionary(Fae().system.resource_limit.show()).verify_result()
    curr_value = output_dict[attribute]
    assert curr_value == expected_value, f"Expected: {attribute}={expected_value}. Got: {attribute}={curr_value}"


def set_value_for_docker_and_verify(engines, limit, docker):
    """
        Helper function to set a resource value for a specific docker in config_db and verify it.
    """
    with allure.step(f"Get curr {limit}"):
        output_dict = OutputParsingTool.parse_json_str_to_dictionary(Fae().system.resource_limit.show()).verify_result()
        curr_value = output_dict[limit]

    with allure.step(f"Randomize new {limit}"):
        new_value = str(randomize_new_value(limit, curr_value))

    with allure.step(f"Set {limit} to {new_value} in config_db"):
        db_config = f"CPU_MEMORY_MONITOR|{docker}"
        Tools.DatabaseTool.sonic_db_cli_hset(engine=engines.dut, asic="", db_name=DatabaseConst.CONFIG_DB_NAME,
                                             db_config=db_config, param=limit, value=new_value)

    with allure.step(f"Verify {limit} changed only for {docker}"):
        verify_resource_value_in_db(engines, output_dict, limit, docker, new_value)

    with allure.step(f"Delete {limit} from config_db"):
        Tools.DatabaseTool.sonic_db_cli_hdel(engine=engines.dut, asic="", db_name=DatabaseConst.CONFIG_DB_NAME,
                                             db_config=db_config, param=limit)


def verify_resource_value_in_db(engines, output_dict, limit, tested_docker, new_value):
    """
        Helper function to verify a resource value for a specific docker in config_db.
    """
    monitored_dockers_list = [item.strip() for item in output_dict["monitored-list"].split(",")]
    for docker in monitored_dockers_list:
        db_config = f"CPU_MEMORY_MONITOR|{docker}"
        curr_value = Tools.DatabaseTool.sonic_db_cli_hget(engine=engines.dut, asic="",
                                                          db_name=DatabaseConst.CONFIG_DB_NAME,
                                                          db_config=db_config, param=limit)
        if docker == tested_docker:
            assert curr_value == new_value, f"{limit} didn't change for {tested_docker}"
        else:
            assert curr_value != new_value, f"{limit} changed for {docker} unexpectedly"


def simulate_high_cpu_usage(engines, devices, docker):
    """
        Helper function to simulate high CPU usage for a docker.
    """
    cmd = """
    end=$(( $(date +%s) + 120 ))
    num_cores=$(nproc)
    iterations=$((3 * {cores_num}))

    for i in $(seq 1 $iterations); do
      (
        while [ $(date +%s) -lt $end ]; do
          start=$(date +%s%3N)

          while :; do
            now=$(date +%s%3N)
            elapsed=$((now - start))
            if [ $elapsed -ge 500 ]; then break; fi
            : $(( (RANDOM * RANDOM) % 10000 ))
          done

          sleep 0.5
        done
      ) &
    done

    wait
    """

    cores_num = devices.dut.core_count
    engines.dut.run_cmd(f"docker exec -it {docker} bash -c '{cmd.strip().format(cores_num=cores_num)}'")
    execution_res = engines.dut.run_cmd("echo \"$?\"").strip().split('\n')[-1]
    assert execution_res in ['0', '137'], "High CPU usage simulation failed"  # 0=success, 137=killed
    logger.info("High CPU usage simulation was executed successfully")


def simulate_and_verify_high_memory_usage(engines, devices, docker, warning_phase=False):
    """
        Helper function to simulate high memory usage for a docker.
    """
    system = System()
    total_memory = OutputParsingTool.parse_json_str_to_dictionary(system.memory.show()).verify_result()["physical"][
        "total"]
    memory_to_use = round((0.20 * total_memory) / 1e9)  # Calculate memory to exceed 15%
    date_format = "%Y-%m-%d %H:%M:%S"
    start_time = datetime.strptime(ClockTools.get_local_time_from_show_system_date_time_output(system.datetime.show()),
                                   date_format)

    phase_desc = "memory-warning-threshold" if warning_phase else "memory-restart-threshold"
    with allure.step(f"Simulate high memory usage for {docker} - exceed 15% during {phase_desc} phase"):
        engines.dut.run_cmd(f"docker exec -it {docker} bash -c 'head -c {memory_to_use}G /dev/zero | tail | sleep 120'")
        execution_res = engines.dut.run_cmd("echo $?").strip().split('\n')[-1]
        assert execution_res in ['0', '137'], "High memory usage simulation failed"  # 0=success, 137=killed
    logger.info("High memory usage simulation was executed successfully")

    sleep_time = 1.5 * MINUTE if warning_phase else 4 * MINUTE  # generating tech-support needs 3+ mins (bug: 4445420), change to 1.5 after fix
    with allure.step(f"Sleeping for {sleep_time / MINUTE:.1f} min"):
        time.sleep(sleep_time)

    if warning_phase:
        verify_behavior_after_simulation(engines, devices, resource="memory", docker=docker, start_time=start_time)
    else:
        verify_behavior_after_simulation(engines, devices, resource="memory", docker=docker, start_time=start_time,
                                         check_tech_support=True, should_generate_tech_support=True,
                                         check_docker_restart=True)


def verify_no_new_tech_support_on_repeated_high_usage(engines, docker):
    """
        Helper function to simulate high memory usage for a second time and verify no new tech-support file was generated.
    """
    system = System()
    total_memory = OutputParsingTool.parse_json_str_to_dictionary(system.memory.show()).verify_result()["physical"][
        "total"]
    memory_to_use = round((0.20 * total_memory) / 1e9)

    with allure.step(f"Simulate high memory usage for {docker} - exceed 15%"):
        start_time = datetime.now()
        engines.dut.run_cmd(
            f"docker exec -it {docker} bash -c 'head -c {memory_to_use}G /dev/zero | tail | sleep 120'")

    with allure.step("Sleeping for 1 min"):
        time.sleep(MINUTE)

    with allure.step("Verify no new tech-support file was generated"):
        verify_tech_support_generation_time(engines, start_time)


def verify_behavior_after_simulation(engines, devices, resource, docker, start_time, check_tech_support=False,
                                     check_docker_restart=False, should_generate_tech_support=False):
    """
        Helper function to verify behavior after high usage simulation.
    """
    system = System()
    with allure.step("Verify warning message in log"):
        system.log.verify_expected_logs_by_time([WARNING_MSG_PATTERN], engines.dut, only_latest_log=False,
                                                start_time=start_time)
    with allure.step("Verify events in log"):
        verify_events_in_logs(engines, system, docker, start_time)

    events = get_events(resource)
    with allure.step("Verify events in events table"):
        verify_events_in_events_table(events, docker)
    with allure.step("Verify events were streamed by gnmi client"):
        verify_gnmic_events(engines, devices, events, docker, resource)
    if check_docker_restart:
        with allure.step("Verify docker was restarted"):
            verify_docker_restart(engines, resource, docker, start_time)
    if check_tech_support:
        with allure.step("Verify tech-support file was generated"):
            verify_tech_support_generation_time(engines, start_time, should_generate_tech_support)


def get_events(resource):
    events_dict = OutputParsingTool.parse_json_str_to_dictionary(System().events.show()).verify_result()
    high_usage_event = normal_usage_event = ""
    for event_id, event in events_dict.items():
        if isinstance(event, dict):
            if re.match(r"{} usage ([0-9]+(\.[0-9]+))% is above expected threshold ([0-9]+)%".format(resource), event['text'].lower()):
                high_usage_event = (event_id, event)
            elif re.match(r"{} usage is back to normal".format(resource), event['text'].lower()):
                normal_usage_event = (event_id, event)
    return high_usage_event, normal_usage_event


@retry(tries=5, delay=10)
def verify_events_in_logs(engines, system, docker, start_time):
    log_message_list = [HIGH_USAGE_EVENT_MSG_PATTERN.format(docker),
                        NORMAL_USAGE_EVENT_MSG_PATTERN.format(docker)]
    system.log.verify_expected_logs_by_time(log_message_list, engines.dut, only_latest_log=False,
                                            start_time=start_time)


def verify_events_in_events_table(events, docker):
    """
        Helper function to check that events were added to events table.
    """
    high_usage_event = events[0][1]
    normal_usage_event = events[1][1]
    assert high_usage_event != "" and normal_usage_event != "", "Couldn't find events in events table"

    for event in [high_usage_event, normal_usage_event]:
        with allure.independent_step(f"Check which docker caused the event: {docker}"):
            docker_in_log = event["resource"]
            docker_in_log_err_msg = f"Message in log is unexpectedly describing {docker_in_log} and not {docker}"
            assert docker_in_log == docker, docker_in_log_err_msg


def verify_gnmic_events(engines, devices, events, docker, resource):
    with allure.step("Get events-id"):
        high_usage_event_id = events[0][0]
        normal_usage_event_id = events[1][0]

    with allure.step("Get gnmi client"):
        client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT,
                            devices.dut.default_username, devices.dut.default_password,
                            verify_tools_installed=True)

    with allure.step("Run gnmi session (once) and verify events were streamed"):
        for event_id in [high_usage_event_id, normal_usage_event_id]:
            out, err, _ = client.gnmic_subscribe_system_event(event_id=event_id, skip_cert_verify=True,
                                                              keep_session_alive=False)
            json_object = json.loads(out)
            with allure.independent_step("Check which docker caused the event"):
                event_docker = get_gnmic_attribute(json_object, "resource")
                assert event_docker == docker, f"Docker caused event is {event_docker} and not {docker}"
            with allure.independent_step("Check event's message"):
                msg = get_gnmic_attribute(json_object, "text")
                if event_id == high_usage_event_id:
                    pattern = fr"{resource} usage (\d+(\.\d+)?)% is above expected threshold (\d+(\.\d+)?)%"
                    assert re.search(pattern, msg.lower()), f"Event's message is not as expected. Got: '{msg}'"
                else:
                    pattern = f"{resource} usage is back to normal"
                    assert msg.lower() == pattern, f"Event's message is not as expected. Got: '{msg}'"


def get_gnmic_attribute(gnmic_out, attribute):
    res = ""
    for update in gnmic_out["updates"]:
        if f"state/{attribute}" in update["values"].keys():
            res = update["values"][f"state/{attribute}"]
    return res


def verify_docker_restart(engines, resource, docker, start):
    """
        Helper function to check:
        1. message in log indicating docker was restarted.
        2. docker's up-time was after the simulation, meaning docker was restarted.
    """
    system = System()
    with allure.step("Look for a message in log describing that docker was restarted"):
        log_message_list = [HIGH_USAGE_EVENT_MSG_PATTERN.format(docker),
                            NORMAL_USAGE_EVENT_MSG_PATTERN.format(docker)]
        system.log.verify_expected_logs_by_time(log_message_list, engines.dut, only_latest_log=False,
                                                start_time=start)
    with allure.step(f"Verify docker started after {start}"):
        with allure.step("Get docker up-time"):
            dockers_data = engines.dut.run_cmd(f"docker ps | grep '{docker}'")
            match = re.search(r'Up (\d+) minutes', dockers_data)
            if not match:
                match = re.search(r'Up About a minute', dockers_data)
                assert match, f"{docker} in not up"
                minutes = 0
            else:
                minutes = int(match.group(1))

        current_time_str = ClockTools.get_local_time_from_show_system_date_time_output(system.datetime.show())
        current_time = datetime.strptime(current_time_str, "%Y-%m-%d %H:%M:%S")
        up_time = current_time - timedelta(minutes=minutes)
        assert start <= up_time, f"Unexpectedly, {docker} did not restart after high {resource} usage simulation"


def verify_tech_support_generation_time(engines, start_time, should_generate_tech_support=False):
    """
        Helper function to verify that a new tech-support file was generated
    """
    system = System()
    with allure.step("Look for message in log describing tech-support file was generated/was not generated"):
        if should_generate_tech_support:
            log_message_list = [GENERATING_TECH_SUPPORT_MSG_PATTERN, TECH_SUPPORT_GENERATED_MSG_PATTERN]
        else:
            log_message_list = [NO_TECH_SUPPORT_GENERATED_MSG_PATTERN]
        system.log.verify_expected_logs_by_time(log_message_list, engines.dut, only_latest_log=False,
                                                start_time=start_time)
    with allure.step(f"Verify tech-support birth time"):
        with allure.step(f"Run 'nv show system tech-support' and get the last one generated"):
            output_list = list(Tools.OutputParsingTool.parse_show_files_to_dict(
                system.techsupport.show()).get_returned_value().values())
            latest = output_list[0]
        system.techsupport.check_techsupport_file_age(engines.dut, system, latest)


def init_monitored_dockers_list(devices, has_nmx, output_dict):
    """
        Helper function to make sure all relevant docker are in monitored dockers list: [nmx-c, nmx-t, gnmi-server]
    """
    monitored_dockers = output_dict["monitored-list"]
    if len(monitored_dockers) == 0:
        System().gnmi_server.enable_gnmi_server()
    while (len(monitored_dockers) == 0) or (has_nmx and monitored_dockers == "gnmi-server"):
        with allure.step("Wait 1 min to the next poll from db and check if list is updated"):
            time.sleep(MINUTE)
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(Fae().system.resource_limit.show()).verify_result()
            monitored_dockers = output_dict["monitored-list"]
    logger.info(f"Dockers to monitor: {monitored_dockers}")

import pytest
import logging
import time
import csv
import os

from datetime import datetime, timedelta
from ngts.nvos_constants.constants_nvos import ApiType, NvosConst, StatsConsts
from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.DatabaseTool import DatabaseTool
from ngts.nvos_tools.infra.SendCommandTool import SendCommandTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_constants.constants_nvos import DatabaseConst

logger = logging.getLogger()


@pytest.mark.system
@pytest.mark.stats
@pytest.mark.simxl
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_stats_configuration(engines, devices, test_api):
    """
    validate:
    - Enable/Disable stats feature
    - Show system stats commands
    - Update stats category configuration
    - System stats actions (clear, delete)
    - Sampling interval and cache duration mechanism
    - New file (internal) is generated after clear command.

    Test flow:
    1. Disable system stats feature
    2. Disable all categories stats
    3. Clear all system stats and delete stats files
    4. Check internal and external files
    5. Select a random category and unset its configuration
    6. Update general configuration
    7. Update category configuration
    8. Wait 1 minute
    9. Check no files created when feature state is disabled
    10.	Enable feature and disable category
    11.	Wait 1 minute
    12.	Check no files created when feature state is disabled
    13.	Update general configuration
    14.	Enable category
    15.	Wait 2 minutes
    16.	Check internal and external files
    17.	Wait another 1 minute
    18.	Check internal and external files
    """

    TestToolkit.tested_api = test_api
    system = System(devices_dut=devices.dut)
    engine = engines.dut
    category_list = devices.dut.category_list
    category_disabled_dict = devices.dut.category_disabled_dict
    category_list_default = devices.dut.category_list_default_dict

    try:
        with allure.step("Set system stats feature to default"):
            system.stats.unset(apply=True).verify_result()

        with allure.step("Disable system stats feature"):
            system.stats.set(op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.DISABLED.value,
                             apply=True).verify_result()
            stats_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.show()).get_returned_value()
            assert stats_show[StatsConsts.STATE] == StatsConsts.State.DISABLED.value, \
                "stats state parameter is expected to be 'disabled'"

        with allure.step("Disable all categories stats"):
            for name in category_list:
                system.stats.category.categoryName[name].set(
                    op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.DISABLED.value).verify_result()
            SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].
                                            apply_config, TestToolkit.engines.dut, False).verify_result()
            stats_category_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.category.show()). \
                get_returned_value()
            ValidationTool.compare_dictionary_content(stats_category_show, category_disabled_dict).verify_result()

        with allure.step("Clear all system stats and delete stats files"):
            clear_all_internal_and_external_files(engine, system, category_list)

        with allure.step("Check both internal and external paths"):
            output = engine.run_cmd("ls /var/stats")
            assert not output or "No such file or directory" in output, "Category internal files were not cleared"
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()). \
                get_returned_value()
            assert not stats_files_show, "External stats files should not exist"

        with allure.step("Select a random category and unset its configuration"):
            name = RandomizationTool.select_random_value(category_list).get_returned_value()
            system.stats.category.categoryName[name].unset(apply=True).verify_result()
            stats_category_show = OutputParsingTool.parse_json_str_to_dictionary(
                system.stats.category.categoryName[name].show()).get_returned_value()
            ValidationTool.compare_dictionary_content(stats_category_show, category_list_default[name]). \
                verify_result()

        with allure.step("Update cache duration to 1 minute"):
            DatabaseTool.sonic_db_cli_hset(engine, "", db_name=DatabaseConst.CONFIG_DB_NAME,
                                           db_config="STATS_CONFIG|GENERAL", param="cache_duration", value="1")

        with allure.step("Update category configuration"):
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.HISTORY_DURATION, op_param_value=int(StatsConsts.HISTORY_DURATION_MIN)).\
                verify_result()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.INTERVAL, op_param_value=int(StatsConsts.INTERVAL_MIN), apply=True).\
                verify_result()
            stats_category_show = OutputParsingTool.parse_json_str_to_dictionary(
                system.stats.category.categoryName[name].show()).get_returned_value()
            ValidationTool.compare_dictionary_content(stats_category_show, StatsConsts.CATEGORY_MIN_DICT).\
                verify_result()

        with allure.step("Restart process..."):
            engine.run_cmd("sudo systemctl restart stats-reportd")

        with allure.step("Check no files created when feature state is disabled"):
            output = engine.run_cmd("ls /var/stats")
            assert not output or "No such file or directory" in output, "Category internal files were not cleared"
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()). \
                get_returned_value()
            assert not stats_files_show, "External stats files should not exist"

        with allure.step("Enable feature and disable category"):
            system.stats.set(op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.ENABLED.value). \
                verify_result()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.DISABLED.value, apply=True). \
                verify_result()
            stats_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.show()).get_returned_value()
            stats_category_show = OutputParsingTool.parse_json_str_to_dictionary(
                system.stats.category.categoryName[name].show()).get_returned_value()
            assert stats_show[StatsConsts.STATE] == StatsConsts.State.ENABLED.value, \
                "stats state parameter is expected to be 'enabled'"
            assert stats_category_show[StatsConsts.STATE] == StatsConsts.State.DISABLED.value, \
                "stats state parameter is expected to be 'disabled'"

        with allure.step("Wait 15 seconds..."):
            time.sleep(StatsConsts.SLEEP_15_SECONDS)

        with allure.step("Check no files created when category state is disabled"):
            output = engine.run_cmd("ls /var/stats")
            assert not output or "No such file or directory" in output, "Category internal files were not cleared"
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()). \
                get_returned_value()
            assert not stats_files_show, "External stats files should not exist"

        with allure.step("Enable category"):
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.ENABLED.value, apply=True). \
                verify_result()
            stats_category_show = OutputParsingTool.parse_json_str_to_dictionary(
                system.stats.category.categoryName[name].show()).get_returned_value()
            assert stats_category_show[StatsConsts.STATE] == StatsConsts.State.ENABLED.value, \
                "stats state parameter is expected to be 'enabled'"

        with allure.step("Wait another 1 minute..."):
            time.sleep(StatsConsts.SLEEP_1_MINUTE)

        with allure.step("Check both internal and external paths"):
            output = engine.run_cmd("ls /var/stats")
            assert output == name + '.csv', "Category internal file does not exist, or not the only one that exists"
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()). \
                get_returned_value()
            assert not stats_files_show, "External stats files should not exist"

    finally:
        set_system_stats_to_default(engine, system)


@pytest.mark.system
@pytest.mark.stats
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_stats_generation(engines, devices, test_api):
    """
    validate:
    - Enable/Disable stats feature
    - Show system stats commands
    - Update stats category configuration
    - System stats actions (generate and upload)
    - External file - name, header and content

    Test flow:
    1. Set stats feature to default
    2. Update general configuration
    3. Update all categories stats states
    4. Wait 3 minutes
    5. Generate system stats category
    6. Upload stats file to URL
    7. Delete stats file
    8. Clear system stats specific category
    9. Wait 3 minutes
    10.	Check internal and external files
    11.	Validate sample timestamps
    """

    TestToolkit.tested_api = test_api
    system = System(devices_dut=devices.dut)
    engine = engines.dut
    player = engines['sonic_mgmt']
    category_list = devices.dut.category_list
    category_list_default = devices.dut.category_list_default_dict

    try:

        with allure.step("Clear all system stats and delete stats files"):
            clear_all_internal_and_external_files(engine, system, category_list)

        with allure.step("Set Stats feature to default"):
            system.stats.unset(op_param=StatsConsts.STATE, apply=True).verify_result()
            stats_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.show()).get_returned_value()
            assert stats_show[StatsConsts.STATE] == StatsConsts.State.ENABLED.value, \
                "stats state parameter is expected to be 'enabled'"

        with allure.step("Update cache duration to 3 minutes"):
            DatabaseTool.sonic_db_cli_hset(engine, "", db_name=DatabaseConst.CONFIG_DB_NAME,
                                           db_config="STATS_CONFIG|GENERAL", param="cache_duration", value="3")

        with allure.step("Update all categories interval values to minimum and states to enable"):
            for name in category_list:
                system.stats.category.categoryName[name].set(
                    op_param_name=StatsConsts.INTERVAL, op_param_value=int(StatsConsts.INTERVAL_MIN)).verify_result()
                system.stats.category.categoryName[name].set(
                    op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.ENABLED.value).verify_result()
            SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].
                                            apply_config, TestToolkit.engines.dut, False).verify_result()

        with allure.step("Restart process and check internal path"):
            engine.run_cmd("sudo systemctl restart stats-reportd")
            check_category_internal_files_exist(engine, category_list)

        with allure.step("Generate system stats category"):
            name = RandomizationTool.select_random_value(category_list).get_returned_value()
            system.stats.category.categoryName[name].action_general(StatsConsts.GENERATE).verify_result()
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()).\
                get_returned_value()
            file_name = list(stats_files_show)[0]
            assert len(stats_files_show) == 1, "Expected only 1 file"
            assert name in file_name, "Expected category file does not exist"

        with allure.step("Upload stats file to URL"):
            validate_upload_stats_file(engines, system, file_name, True)

        with allure.step("Validate show file"):
            show_output = system.stats.files.file_name[file_name].show_file(exit_cmd='q')
            if 'NVUE' == TestToolkit.tested_api:
                assert name in show_output, "show file is missing category name"

        with allure.step("Delete stats external file"):
            system.stats.files.file_name[file_name].action_delete()
            output = engine.run_cmd("ls /var/stats")
            assert name in output, "Category internal file not exists"
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()).\
                get_returned_value()
            assert not stats_files_show, "External stats files should not exist"

        with allure.step("Clear system stats specific category"):
            clear_time = datetime.now()
            system.stats.category.categoryName[name].action_general(StatsConsts.CLEAR).verify_result()
            output = engine.run_cmd("ls /var/stats")
            assert not output or name not in output, "Category internal file was not cleared"

        with allure.step("Wait another 3 minutes..."):
            time.sleep(StatsConsts.SLEEP_3_MINUTES)

        with allure.step("Check both internal and external paths"):
            output = engine.run_cmd("ls /var/stats")
            assert name in output, "Category internal file does not exist, or not the only one that exists"
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()).\
                get_returned_value()
            assert not stats_files_show, "External stats files should not exist"

        with allure.step("Generate and upload stats file to URL"):
            system.stats.category.categoryName[name].action_general(StatsConsts.GENERATE).verify_result()
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()).\
                get_returned_value()
            file_name = list(stats_files_show)[0]
            validate_upload_stats_file(engines, system, file_name, False)

        with allure.step("Validate samples timestamps is older than clear time"):
            validate_external_file_timestamps(file_name, clear_time)

        with allure.step("Delete uploaded file"):
            player.run_cmd(cmd='rm -f {}{}'.format(NvosConst.MARS_RESULTS_FOLDER, file_name))

        with allure.step("Select a random category and set its configuration to minimum values"):
            name = RandomizationTool.select_random_value(category_list).get_returned_value()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.INTERVAL, op_param_value=int(StatsConsts.INTERVAL_MIN)).verify_result()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.DISABLED.value).verify_result()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.HISTORY_DURATION,
                op_param_value=int(StatsConsts.HISTORY_DURATION_MIN), apply=True).verify_result()
            stats_category_show = OutputParsingTool.parse_json_str_to_dictionary(
                system.stats.category.categoryName[name].show()).get_returned_value()
            ValidationTool.compare_dictionary_content(stats_category_show, StatsConsts.CATEGORY_MIN_DISABLED_DICT).\
                verify_result()

        with allure.step("Verify unset each category parameter configuration"):
            system.stats.category.categoryName[name].unset(op_param=StatsConsts.INTERVAL).verify_result()
            system.stats.category.categoryName[name].unset(op_param=StatsConsts.HISTORY_DURATION).verify_result()
            system.stats.category.categoryName[name].unset(op_param=StatsConsts.STATE, apply=True).verify_result()

            stats_category_show = OutputParsingTool.parse_json_str_to_dictionary(
                system.stats.category.categoryName[name].show()).get_returned_value()
            ValidationTool.compare_dictionary_content(stats_category_show, category_list_default[name]).\
                verify_result()

        with allure.step("Select a random category and set its configuration to minimum values"):
            name = RandomizationTool.select_random_value(category_list).get_returned_value()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.INTERVAL, op_param_value=int(StatsConsts.INTERVAL_MIN)).verify_result()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.DISABLED.value).verify_result()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.HISTORY_DURATION,
                op_param_value=int(StatsConsts.HISTORY_DURATION_MIN), apply=True).verify_result()
            stats_category_show = OutputParsingTool.parse_json_str_to_dictionary(
                system.stats.category.categoryName[name].show()).get_returned_value()
            ValidationTool.compare_dictionary_content(stats_category_show, StatsConsts.CATEGORY_MIN_DISABLED_DICT).\
                verify_result()

        with allure.step("Verify unset category configuration"):
            system.stats.category.categoryName[name].unset(apply=True).verify_result()

    finally:
        set_system_stats_to_default(engine, system)


@pytest.mark.system
@pytest.mark.stats
@pytest.mark.simx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_system_stats_performance(engines, devices, test_api):
    """
    validate:
    - Generate all system stats command
    - Time to generate "all" categories < 2 secs
    - Cleanup mechanism (after reboot)

    Test flow:
    1. Set stats feature to default
    2. Update general configuration
    3. Select a random category
    4. Update selected category stats config.
    5. Create category internal file with old samples
    6. Restart stats process
    7. Wait 1 minute
    8. Verify cleanup after reboot
    9.Update all categories stats states
    10.	Wait 1 minute
    11.	Generate all system files and verify action time
    12.	Upload stats file to URL
    13.	Validate file content
    """

    TestToolkit.tested_api = test_api
    system = System(devices_dut=devices.dut)
    engine = engines.dut
    category_list = devices.dut.category_list
    category_disabled_dict = devices.dut.category_disabled_dict
    player_engine = engines['sonic_mgmt']

    try:
        with allure.step("Set Stats feature to default"):
            system.stats.unset(apply=True).verify_result()
            stats_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.show()).get_returned_value()
            assert stats_show[StatsConsts.STATE] == StatsConsts.State.ENABLED.value, \
                "stats state parameter is expected to be 'enabled'"

        with allure.step("Clear all system stats and delete stats files"):
            clear_all_internal_and_external_files(engine, system, category_list)

        with allure.step("Update cache duration to 1 minute"):
            DatabaseTool.sonic_db_cli_hset(engine, "", db_name=DatabaseConst.CONFIG_DB_NAME,
                                           db_config="STATS_CONFIG|GENERAL", param="cache_duration", value="1")

        with allure.step("Select a random category"):
            name = RandomizationTool.select_random_value(list(category_disabled_dict.keys())). \
                get_returned_value()

        with allure.step("Update selected category stats config"):
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.INTERVAL, op_param_value=int(StatsConsts.INTERVAL_MIN)).verify_result()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.HISTORY_DURATION, op_param_value=int(StatsConsts.HISTORY_DURATION_MIN)).\
                verify_result()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.ENABLED.value, apply=True).\
                verify_result()
            SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].
                                            save_config, TestToolkit.engines.dut).verify_result()

        with allure.step("Create category internal file with old samples"):
            file_path = StatsConsts.OLD_SAMPLES_PATH + name + '.csv'
            player_engine.upload_file_using_scp(dest_username=devices.dut.default_username,
                                                dest_password=devices.dut.default_password,
                                                dest_folder=StatsConsts.INTERNAL_PATH,
                                                dest_ip=engines.dut.ip,
                                                local_file_path=file_path)
            engine.run_cmd("sudo cp /tmp/{}.csv /var/stats".format(name))

        with allure.step("Perform system reboot"):
            system.reboot.action_reboot(params='force').verify_result()

        with allure.step("Wait 15 seconds..."):
            time.sleep(StatsConsts.SLEEP_15_SECONDS)

        with allure.step("Check internal files were created"):
            check_category_internal_files_exist(engine, category_list)

        with allure.step("Clear all external files"):
            engine.run_cmd("sudo rm -f /host/stats/*.csv")

        with allure.step("Generate and upload stats file to URL"):
            system.stats.category.categoryName[name].action_general(StatsConsts.GENERATE).verify_result()
            current_time = datetime.now()
            history_time = current_time - timedelta(days=int(StatsConsts.HISTORY_DURATION_MIN))
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()).\
                get_returned_value()
            file_name = list(stats_files_show)[0]
            validate_upload_stats_file(engines, system, file_name, False)

        with allure.step("Verify cleanup after restart process"):
            validate_external_file_timestamps(file_name, history_time)

        with allure.step("Delete uploaded file"):
            player_engine.run_cmd(cmd='rm -f {}{}'.format(NvosConst.MARS_RESULTS_FOLDER, file_name))

        with allure.step("Clear all external files"):
            engine.run_cmd("sudo rm -f /host/stats/*.csv")

        with allure.step("Generate all system files and verify action time"):
            start_time = time.time()
            system.stats.action_general(StatsConsts.GENERATE).verify_result()
            end_time = time.time()
            diff_time = end_time - start_time
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()).\
                get_returned_value()
            file_name = list(stats_files_show)[0]
            assert len(stats_files_show) == 1, "Expected only 1 file"
            assert 'tar' in file_name, "tar file does not exist"
            assert diff_time < StatsConsts.GENERATE_ALL_TIME_MAX, "Generate all time is higher than allowed"

        with allure.step("Upload stats file to URL"):
            validate_upload_stats_file(engines, system, file_name, False)

        with allure.step("Extract the file and check that all categories file exist"):
            # engine.run_cmd('sudo tar -xf ' + NvosConst.MARS_RESULTS_FOLDER + file_name + ' -C /tmp')
            # folder_name = techsupport.replace('.tar.gz', "")
            # output = engine.run_cmd('ls ' + folder_name + '/stats')

            engine.run_cmd("sudo tar -xf {}{}".format(NvosConst.MARS_RESULTS_FOLDER, file_name))
            file_split = file_name.split("_")
            report_path = os.path.splitext('report_{}_{}'.format(file_split[-2], file_split[-1]))[0]
            output = engine.run_cmd("ls {}{}".format(NvosConst.MARS_RESULTS_FOLDER, report_path))
            # for name in category_list:
            #     assert name in output, f"{name} external file is missing in tar file"

        with allure.step("Delete uploaded file"):
            player_engine.run_cmd(cmd='rm -f {}{}'.format(NvosConst.MARS_RESULTS_FOLDER, file_name))

    finally:
        set_system_stats_to_default(engine, system)


@pytest.mark.system
@pytest.mark.stats
@pytest.mark.simx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_stats_reliability(engines, devices, test_api):
    """
    validate:
    - Configuration of the feature persists through upgrade and reboot
    - Configuring/return to default the feature in the loop should be stable
    - No unexpected behavior (access violation, leak etc.) when processing malformed input
        (e.g. malformed/missing config in DB)

    Test flow:
    1. Set stats feature to default
    2. Update general configuration
    3. Update all categories stats states
    4. Wait 1 minute
    5. Check internal path
    6. Perform system reboot
    7. Check feature and categories config.
    8. Check internal path
    9. Configuring the feature to default in the loop
    10.	Remove sampled data from DB
    """

    TestToolkit.tested_api = test_api
    system = System(devices_dut=devices.dut)
    engine = engines.dut
    category_list = devices.dut.category_list
    try:
        with allure.step("Set Stats feature to default"):
            system.stats.unset(apply=True).verify_result()

        with allure.step("Update cache duration to 1 minute"):
            DatabaseTool.sonic_db_cli_hset(engine, "", db_name=DatabaseConst.CONFIG_DB_NAME,
                                           db_config="STATS_CONFIG|GENERAL", param="cache_duration", value="1")

        with allure.step("Update all categories stats states"):
            for name in category_list:
                system.stats.category.categoryName[name].set(
                    op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.ENABLED.value).verify_result()
                system.stats.category.categoryName[name].set(
                    op_param_name=StatsConsts.INTERVAL, op_param_value=int(StatsConsts.INTERVAL_MIN)).verify_result()
                system.stats.category.categoryName[name].set(
                    op_param_name=StatsConsts.HISTORY_DURATION, op_param_value=int(StatsConsts.HISTORY_DURATION_MIN)).\
                    verify_result()
            SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].
                                            apply_config, TestToolkit.engines.dut, False).verify_result()
            SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].
                                            save_config, TestToolkit.engines.dut).verify_result()

        with allure.step("restart stats service and check internal path"):
            engine.run_cmd("sudo systemctl restart stats-reportd")
            with allure.step("Wait 15 seconds..."):
                time.sleep(StatsConsts.SLEEP_15_SECONDS)
            check_category_internal_files_exist(engine, category_list)

        with allure.step("Perform system reboot"):
            system.reboot.action_reboot(params='force').verify_result()

        with allure.step("Check feature and categories configurations"):
            stats_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.show()).get_returned_value()
            assert stats_show[StatsConsts.STATE] == StatsConsts.State.ENABLED.value, \
                "stats state parameter is expected to be 'enabled'"
            for name in category_list:
                stats_category_show = OutputParsingTool.parse_json_str_to_dictionary(
                    system.stats.category.categoryName[name].show()).get_returned_value()
                ValidationTool.compare_dictionary_content(stats_category_show, StatsConsts.CATEGORY_MIN_DICT).\
                    verify_result()

        with allure.step("Check internal path"):
            check_category_internal_files_exist(engine, category_list)

        with allure.step("Configuring the feature to default in the loop"):
            for x in range(10):
                system.stats.unset(op_param=StatsConsts.STATE, apply=True).verify_result()
            stats_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.show()).get_returned_value()
            assert stats_show[StatsConsts.STATE] == StatsConsts.State.ENABLED.value, \
                "stats state parameter is expected to be 'enabled'"

        with allure.step("Remove sampled data from DB"):
            # TODO: delete a sampled parameter from DB
            stats_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.show()).get_returned_value()
            assert stats_show[StatsConsts.STATE] == StatsConsts.State.ENABLED.value, \
                "stats state parameter is expected to be 'enabled'"
            system.log.rotate_logs()
            show_output = system.log.file.show_log(exit_cmd='q')
            # TODO: update StatsConsts.LOG_MSG_ERROR_DB
            # ValidationTool.verify_expected_output(show_output, StatsConsts.LOG_MSG_ERROR_DB).verify_result()

    finally:
        set_system_stats_to_default(engine, system)


@pytest.mark.system
@pytest.mark.stats
@pytest.mark.simx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_system_stats_log(engines, devices, test_api):
    """
    validate:
    - Configuring commands are logged to system log

    Test flow:
    1. Unset stats feature state and check log file
    2. Set category stats configuration and check log file
    """

    TestToolkit.tested_api = test_api
    system = System(devices_dut=devices.dut)
    category_list = devices.dut.category_list

    ssh_connection = ConnectionTool.create_ssh_conn(engines.dut.ip, engines.dut.username,
                                                    engines.dut.password).get_returned_value()

    try:
        with allure.step("Unset stats feature state and check log file"):
            system.log.rotate_logs()
            system.stats.unset(op_param=StatsConsts.STATE, apply=True).verify_result()

        with allure.step("Set category stats configuration and check log file"):
            name = RandomizationTool.select_random_value(category_list).get_returned_value()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.INTERVAL, op_param_value=int(StatsConsts.INTERVAL_MIN)).verify_result()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.HISTORY_DURATION, op_param_value=int(StatsConsts.HISTORY_DURATION_DEFAULT)).\
                verify_result()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.ENABLED.value).verify_result()
            SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].
                                            apply_config, TestToolkit.engines.dut, False).verify_result()

        with allure.step("Validate commands exist in system log"):
            log_message_list = [StatsConsts.LOG_MSG_UNSET_STATS, StatsConsts.LOG_MSG_PATCH_CATEGORY + name]
            system.log.verify_expected_logs(log_message_list, engine=ssh_connection)

        with allure.step("Validate stats files in tech support file"):
            stats_files = list(engines.dut.run_cmd("ls /var/stats").split())
            validate_stats_files_exist_in_techsupport(system, engines.dut, stats_files)

    finally:
        set_system_stats_to_default(engines.dut, system)


@pytest.mark.system
@pytest.mark.stats
@pytest.mark.simx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_validate_tech_support_with_max_size(engines, devices, test_api):
    """
    validate:
    - Validate creating tech support when all stats files are full (reached max size)

    Test flow:
    1. Disable stats feature
    2. Replace all stats categories internal files with max sized files
    3. Run tech-support and validate files.
    """

    TestToolkit.tested_api = test_api
    system = System(devices_dut=devices.dut)
    player_engine = engines['sonic_mgmt']
    category_list = devices.dut.category_list

    try:
        with allure.step("Disable system stats feature"):
            system.stats.set(op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.DISABLED.value,
                             apply=True).verify_result()

        with allure.step("Clear all internal files"):
            engines.dut.run_cmd("sudo rm -f /var/stats/*")

        with allure.step("Replace all category internal files with a max sized files"):
            for category in category_list:
                file_name = category + '.csv'
                file_path = StatsConsts.MAX_SIZE_FILE_PATH + file_name
                player_engine.upload_file_using_scp(dest_username=devices.dut.default_username,
                                                    dest_password=devices.dut.default_password,
                                                    dest_folder=StatsConsts.INTERNAL_PATH,
                                                    dest_ip=engines.dut.ip,
                                                    local_file_path=file_path)
                engines.dut.run_cmd("sudo cp /tmp/{} /var/stats".format(file_name))

        with allure.step("Validate stats files in tech support file"):
            stats_files = list(engines.dut.run_cmd("ls /var/stats").split())
            validate_stats_files_exist_in_techsupport(system, engines.dut, stats_files)

    finally:
        with allure.step("Clear all internal files and set to all default"):
            engines.dut.run_cmd("sudo rm -f /var/stats/*")
            set_system_stats_to_default(engines.dut, system)


@pytest.mark.system
@pytest.mark.stats
@pytest.mark.simx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_system_stats_invalid_values(engines, devices, test_api):
    """
    validate:
    - Check all the commands that get param with invalid values

    Test flow:
    1. nv set system stats category <invalid category-name> state <state>
    2. nv set system stats category <category-name> state <invalid state>
    3. nv set system stats category <category-name> interval <less than 1>
    4. nv set system stats category <category-name> interval <higher than 1440>
    5. nv set system stats category <category-name> history-duration <less than 1>
    6. nv set system stats category <category-name> history-duration <higher than 365>
    7. nv show system stats category <invalid category-name>
    8. nv clear system stats <invalid category-name>
    9. nv action delete system stats files <file does not exist>
    10. nv action upload system stats files <file does not exist> <remote-url>
    11. nv action upload system stats files <file-name> <invalid remote-url>
    12. nv action generate system stats <invalid category-name>
    """

    TestToolkit.tested_api = test_api
    system = System(devices_dut=devices.dut)
    engine = engines.dut
    category_list = devices.dut.category_list
    player = engines['sonic_mgmt']
    invalid_remote_url = 'scp://{}:{}{}/tmp/'.format(player.username, player.password, player.ip)
    valid_remote_url = 'scp://{}:{}@{}/tmp/'.format(player.username, player.password, player.ip)

    try:
        with allure.step("Validate set system stats unknown category"):
            system.stats.category.categoryName[StatsConsts.INVALID_CATEGORY_NAME].set(
                op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.State.DISABLED.value, apply=True).\
                verify_result(should_succeed=False)

        with allure.step("Validate set system stats category invalid state"):
            name = RandomizationTool.select_random_value(category_list).get_returned_value()
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.STATE, op_param_value=StatsConsts.INVALID_STATE).\
                verify_result(should_succeed=False)

        with allure.step("Validate set system stats category invalid low interval"):
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.INTERVAL, op_param_value=StatsConsts.INVALID_INTERVAL_LOW).\
                verify_result(should_succeed=False)

        with allure.step("Validate set system stats category invalid high interval"):
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.INTERVAL, op_param_value=StatsConsts.INVALID_INTERVAL_HIGH).\
                verify_result(should_succeed=False)

        with allure.step("Validate set system stats category invalid low history-duration"):
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.HISTORY_DURATION, op_param_value=StatsConsts.INVALID_HISTORY_DURATION_LOW).\
                verify_result(should_succeed=False)

        with allure.step("Validate set system stats category invalid high history-duration"):
            system.stats.category.categoryName[name].set(
                op_param_name=StatsConsts.HISTORY_DURATION, op_param_value=StatsConsts.INVALID_HISTORY_DURATION_HIGH).\
                verify_result(should_succeed=False)

        with allure.step("Validate show system stats invalid category"):
            system.stats.category.categoryName[StatsConsts.INVALID_CATEGORY_NAME].show(should_succeed=False)

        with allure.step("Validate clear system stats invalid category"):
            system.stats.category.categoryName[StatsConsts.INVALID_CATEGORY_NAME].action_general(StatsConsts.CLEAR).\
                verify_result(should_succeed=False)

        with allure.step("Validate delete system stats file not exists"):
            system.stats.files.file_name[StatsConsts.INVALID_FILE_NAME].action_delete(should_succeed=False)

        with allure.step("Validate upload system stats file not exists"):
            system.stats.files.file_name[StatsConsts.INVALID_FILE_NAME].action_upload(valid_remote_url,
                                                                                      should_succeed=False)

        with allure.step("Validate upload system stats file to invalid URL"):
            file_name = 'stats_cpu_gorilla-154_20230702_145940.csv'
            file_path = StatsConsts.GENERATED_FILE_PATH + file_name
            player.upload_file_using_scp(dest_username=devices.dut.default_username,
                                         dest_password=devices.dut.default_password,
                                         dest_folder=StatsConsts.INTERNAL_PATH,
                                         dest_ip=engines.dut.ip,
                                         local_file_path=file_path)
            engine.run_cmd("sudo cp /tmp/{} /host/stats".format(file_name))
            system.stats.files.file_name[file_name].action_upload(invalid_remote_url, should_succeed=False)

        with allure.step("Validate generate system stats invalid category"):
            system.stats.category.categoryName[StatsConsts.INVALID_CATEGORY_NAME].action_general(StatsConsts.GENERATE).\
                verify_result(should_succeed=False)

    finally:
        engine.run_cmd("sudo rm -f /host/stats/*")
        SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].
                                        detach_config, TestToolkit.engines.dut).verify_result()
        set_system_stats_to_default(engine, system)


@pytest.mark.system
@pytest.mark.stats
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_stats_big_files(engines, devices, test_api):
    """
    validate:
    - Append works on a big file (600K samples)
    - Clear works on a big file (600K samples)
    - Corrupted file - bigger than 600MB
    - Corrupted file - without a header

    Test flow:
    1. unset system stats feature
    2. set fan category history duration and interval to min values
    3. Update general configuration - cache_duration to min value
    4. Restart stats service to apply changes immediately
    5. Replace internal file with a big file
    6. Wait interval time and validate new samples are written to file
    7. Restart stats service and validate clear works on a big file
    8. Replace category internal file with a corrupted file (no header) and validate creation of a new file
    9. Replace category internal file with a corrupted file (over 600MB) and validate creation of a new file
    """

    TestToolkit.tested_api = test_api
    system = System(devices_dut=devices.dut)
    engine = engines.dut
    player_engine = engines['sonic_mgmt']

    try:
        with allure.step("Set system stats feature to default"):
            system.stats.unset(apply=True).verify_result()

        with allure.step("set fan category history duration and interval to min values"):
            system.stats.category.categoryName['disk'].set(
                op_param_name=StatsConsts.HISTORY_DURATION, op_param_value=int(StatsConsts.HISTORY_DURATION_MIN)).\
                verify_result()
            system.stats.category.categoryName['disk'].set(
                op_param_name=StatsConsts.INTERVAL, op_param_value=int(StatsConsts.INTERVAL_MIN), apply=True).\
                verify_result()

        with allure.step("Update cache duration to 1 minute"):
            DatabaseTool.sonic_db_cli_hset(engine, "", db_name=DatabaseConst.CONFIG_DB_NAME,
                                           db_config="STATS_CONFIG|GENERAL", param="cache_duration", value="1")

        with allure.step("Restart process..."):
            engine.run_cmd("sudo systemctl restart stats-reportd")

        with allure.step("Replace internal file with a big file"):
            file_name = 'disk.csv'
            file_path = StatsConsts.BIG_FILE_PATH + file_name
            player_engine.upload_file_using_scp(dest_username=devices.dut.default_username,
                                                dest_password=devices.dut.default_password,
                                                dest_folder=StatsConsts.INTERNAL_PATH,
                                                dest_ip=engines.dut.ip,
                                                local_file_path=file_path)
            engine.run_cmd("sudo cp /tmp/{} /var/stats".format(file_name))

        with allure.step("Wait 1 min..."):
            time.sleep(StatsConsts.SLEEP_1_MINUTE)

        with allure.step("Validate appending big file"):
            validate_number_of_lines_in_external_file(engines, system, 'disk', StatsConsts.BIG_FILE_NUM_OF_LINES,
                                                      StatsConsts.BIG_FILE_NUM_OF_LINES + 3)

        with allure.step("Delete uploaded file"):
            engine.run_cmd(cmd='rm -f {}'.format(file_path))

        with allure.step("Restart process..."):
            engine.run_cmd("sudo systemctl restart stats-reportd")

        with allure.step("Wait 15 seconds..."):
            time.sleep(StatsConsts.SLEEP_15_SECONDS)

        with allure.step("Validate clearing big file"):
            validate_number_of_lines_in_external_file(engines, system, 'disk',
                                                      devices.dut.stats_disk_header_num_of_lines,
                                                      devices.dut.stats_disk_header_num_of_lines + 30)

        with allure.step("Delete uploaded file"):
            engine.run_cmd(cmd='rm -f {}'.format(file_path))

        with allure.step("Replace internal file with file without header"):
            file_name = 'cpu.csv'
            file_path = StatsConsts.NO_HEADER_FILE_PATH + file_name
            player_engine.upload_file_using_scp(dest_username=devices.dut.default_username,
                                                dest_password=devices.dut.default_password,
                                                dest_folder=StatsConsts.INTERNAL_PATH,
                                                dest_ip=engines.dut.ip,
                                                local_file_path=file_path)
            engine.run_cmd("sudo cp /tmp/{} /var/stats".format(file_name))

        with allure.step("Restart process..."):
            engine.run_cmd("sudo systemctl restart stats-reportd")

        with allure.step("Wait 15 seconds..."):
            time.sleep(StatsConsts.SLEEP_15_SECONDS)

        with allure.step("Validate creating new category file when header is corrupted"):
            validate_number_of_lines_in_external_file(engines, system, 'cpu',
                                                      devices.dut.stats_cpu_header_num_of_lines,
                                                      devices.dut.stats_cpu_header_num_of_lines + 3)

        with allure.step("Delete uploaded file"):
            engine.run_cmd(cmd='rm -f {}'.format(file_path))

        with allure.step("Replace internal file with a huge file"):
            file_name = 'temperature.csv'
            file_path = StatsConsts.HUGE_FILE_PATH + file_name
            player_engine.upload_file_using_scp(dest_username=devices.dut.default_username,
                                                dest_password=devices.dut.default_password,
                                                dest_folder=StatsConsts.INTERNAL_PATH,
                                                dest_ip=engines.dut.ip,
                                                local_file_path=file_path)
            engine.run_cmd("sudo cp /tmp/{} /var/stats".format(file_name))

        with allure.step("Restart process..."):
            engine.run_cmd("sudo systemctl restart stats-reportd")

        with allure.step("Wait 40 seconds..."):
            time.sleep(StatsConsts.SLEEP_40_SECONDS)

        with allure.step(f"Get Temperature header number of lines"):
            temperature_header_num_of_lines = get_header_number_of_lines(engines, 'temperature')
            assert temperature_header_num_of_lines >= devices.dut.stats_temperature_header_num_of_lines, \
                (f"temperature header number of lines ({temperature_header_num_of_lines}) is lower than the "
                 f"expected minimum number of lines: {devices.dut.stats_temperature_header_num_of_lines}")

        with allure.step("Validate creating new category file when file size is over 600MB"):
            validate_number_of_lines_in_external_file(engines, system, 'temperature',
                                                      temperature_header_num_of_lines,
                                                      temperature_header_num_of_lines + 100)

        with allure.step("Delete uploaded file"):
            engine.run_cmd(cmd='rm -f /tmp/{}'.format(file_name))

    finally:
        set_system_stats_to_default(engine, system)


@pytest.mark.system
@pytest.mark.stats
@pytest.mark.simx
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_validate_category_file_values(engines, devices, test_api):
    """
    validate:
    - Category file values are within the valid range
    - Samples timestamps match the configured interval

    Test flow:
    1. unset system stats feature
    2. set random category history duration and interval to min values
    3. Update general configuration - cache_duration to min value
    4. clear all internal and external category files
    5. Restart stats service to apply changes immediately
    6. Wait 5 minutes
    7. Generate and upload the chosen category file
    8. Validate file values are within range
    9. Validate samples timestamps match the configured interval
    10. Restore default values
    """

    TestToolkit.tested_api = test_api
    system = System(devices_dut=devices.dut)
    engine = engines.dut
    player = engines['sonic_mgmt']
    category_list = devices.dut.category_list

    try:
        with allure.step("Set system stats feature to default"):
            system.stats.unset(apply=True).verify_result()

        with allure.step("Set all categories history duration and interval values to minimum"):
            for name in category_list:
                system.stats.category.categoryName[name].set(
                    op_param_name=StatsConsts.HISTORY_DURATION, op_param_value=int(StatsConsts.HISTORY_DURATION_MIN)).\
                    verify_result()
                system.stats.category.categoryName[name].set(
                    op_param_name=StatsConsts.INTERVAL, op_param_value=int(StatsConsts.INTERVAL_MIN)).\
                    verify_result()
            SendCommandTool.execute_command(TestToolkit.GeneralApi[TestToolkit.tested_api].
                                            apply_config, TestToolkit.engines.dut, False).verify_result()

        with allure.step("Update cache duration to 1 minute"):
            DatabaseTool.sonic_db_cli_hset(engine, "", db_name=DatabaseConst.CONFIG_DB_NAME,
                                           db_config="STATS_CONFIG|GENERAL", param="cache_duration", value="1")

        with allure.step("Clear all system stats and delete stats files"):
            system_show = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
            start_time = datetime.strptime(system_show['date-time'], StatsConsts.SYSTEM_TIME_FORMAT)
            hostname = system_show['hostname']
            clear_all_internal_and_external_files(engine, system, category_list)

        with allure.step("Restart process..."):
            engine.run_cmd("sudo systemctl restart stats-reportd")

        with allure.step("Wait 5 min..."):
            time.sleep(StatsConsts.SLEEP_5_MINUTES)

        with allure.step("Generate system stats category"):
            for name in category_list:
                system.stats.category.categoryName[name].action_general(StatsConsts.GENERATE).verify_result()
            stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()).\
                get_returned_value()

            for file_name in stats_files_show:
                with allure.step("Upload stats file to URL"):
                    validate_upload_stats_file(engines, system, file_name, False)

                with allure.step("Validate external file header"):
                    name = file_name.split('_')[1]
                    file_path = NvosConst.MARS_RESULTS_FOLDER + file_name
                    end_time = start_time + timedelta(minutes=6)
                    validate_external_file_header_and_data(name, file_path, hostname, start_time, end_time)

                with allure.step("Delete uploaded file"):
                    player.run_cmd(cmd='rm -f {}'.format(file_path))

    finally:
        set_system_stats_to_default(engine, system)


@pytest.mark.system
@pytest.mark.stats
@pytest.mark.simx
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_stats_on_skynet(test_api):
    """
    (Dedicated test will be added later to skynet to check some of the functionalities once a month)

    Test flow:
    1. ...
    """

    TestToolkit.tested_api = test_api


# ---------------------------------------------
def set_system_stats_to_default(engine, system):
    with allure.step("Update Stats feature to default"):
        system.stats.unset(apply=True).verify_result()

    with allure.step("Update cache general configuration to default"):
        DatabaseTool.sonic_db_cli_hset(engine, "", db_name=DatabaseConst.CONFIG_DB_NAME,
                                       db_config="STATS_CONFIG|GENERAL", param="cache_duration", value="10")
        DatabaseTool.sonic_db_cli_hset(engine, "", db_name=DatabaseConst.CONFIG_DB_NAME,
                                       db_config="STATS_CONFIG|GENERAL", param="cache_duration", value="1")


def clear_all_internal_and_external_files(engine, system, category_list):
    system.stats.action_general(StatsConsts.CLEAR).verify_result()
    stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()).get_returned_value()
    if stats_files_show != "":
        for file in stats_files_show.keys():
            system.stats.files.file_name[file].action_delete(should_succeed=True)
    # clear old files if exist
    engine.run_cmd("sudo rm -f /var/stats/*.old")


def check_category_internal_files_exist(engine, category_list):
    output = engine.run_cmd("ls /var/stats")
    output_list = list(filter(None, output.split(' ')))
    assert len(output_list) == len(category_list), "Categories number of files is not as expected"
    for cat in category_list:
        assert cat in output, f"{cat} internal file is missing"


def validate_upload_stats_file(engines, system, file, delete=True):
    """
    validate upload stats file with scp and sftp
    """
    upload_protocols = ['scp', 'sftp']
    player = engines['sonic_mgmt']
    dest_path = NvosConst.MARS_RESULTS_FOLDER

    with allure.step("Upload stats file to player {} with the next protocols : {}".format(player.ip, upload_protocols)):
        for protocol in upload_protocols:
            with allure.step("Upload stats file to player with {} protocol".format(protocol)):
                upload_path = 'scp://{}:{}@{}{}'.format(player.username, player.password, player.ip, dest_path)
                system.stats.files.file_name[file].action_upload(upload_path)

            with allure.step("Validate file was uploaded to player"):
                assert player.run_cmd(cmd='ls {} | grep {}'.format(dest_path, file)), \
                    "Did not find the file with ls cmd"

            if delete:
                with allure.step("Delete uploaded file"):
                    player.run_cmd(cmd='rm -f {}{}'.format(dest_path, file))


def validate_external_file_header_and_data(name, file_path, hostname, start_time, end_time):
    with open(file_path, 'r') as csv_file:
        reader = csv.reader(csv_file)
        next(reader)
        row = next(reader)
        assert row[0] == StatsConsts.HEADER_HOSTNAME + hostname, \
            f"unexpected hostname in file header, {row[0]} instead of {hostname}"
        row = next(reader)
        assert row[0] == StatsConsts.HEADER_GROUP + name, \
            f"unexpected group in file header, {row[0]} instead of {name}"
        row = next(reader)
        assert row[0].startswith(StatsConsts.HEADER_TIME), "unexpected started time text in file header"

        if start_time and end_time:
            export_time = datetime.strptime(row[0].replace(StatsConsts.HEADER_TIME, ''), StatsConsts.TIMESTAMP_FORMAT)
            assert start_time < export_time < end_time, \
                f"External file started sampling time: {export_time} should be between {start_time}-{end_time}"

        idx = 4
        start_data_idx = -1
        header_list = []
        for row in reader:
            if row:
                if row[0].startswith("Timestamp"):
                    start_data_idx = idx + 1
                    break
                elif row[0].startswith("# Column"):
                    header_list.append(row[0].split(': ')[-1])
            idx += 1
            if idx == StatsConsts.MAX_ROWS_TO_SCAN:
                break

        assert header_list == row, "there is a mismatch between columns in header to columns list"
        assert start_data_idx >= 0, "did not find data start line"
        assert len(row) == (start_data_idx - StatsConsts.CONST_HEADER_ROWS), \
            "there is a mismatch between columns defined number"

        prev_sample_time = export_time - timedelta(minutes=int(StatsConsts.INTERVAL_MIN))
        col_names = row
        num_of_samples = 0
        num_of_columns = len(row)

        if name == 'cpu':
            for row in reader:
                assert len(row) == num_of_columns, f"number of values ({len(row)}) are not as expected (num_of_columns)"
                num_of_samples += 1
                prev_sample_time = check_sample_timestamp(row, prev_sample_time, name)
                check_in_range_without_na(col_names[1], row[1], StatsConsts.CPU_FREE_RAM_MIN,
                                          StatsConsts.CPU_FREE_RAM_MAX, num_of_samples, name)
                check_in_range_without_na(col_names[2], row[2], StatsConsts.CPU_UTIL_MIN,
                                          StatsConsts.CPU_UTIL_MAX, num_of_samples, name)
                check_in_range_without_na(col_names[3], row[3], StatsConsts.CPU_REBOOT_CNT_MIN,
                                          StatsConsts.CPU_REBOOT_CNT_MAX, num_of_samples, name)
        elif name == 'disk':
            for row in reader:
                assert len(row) == num_of_columns, f"number of values ({len(row)}) are not as expected (num_of_columns)"
                num_of_samples += 1
                prev_sample_time = check_sample_timestamp(row, prev_sample_time, name)
                check_in_range(col_names[1], row[1], StatsConsts.DISK_FREE_SPACE_MIN,
                               StatsConsts.DISK_FREE_SPACE_MAX, num_of_samples, name)
                check_in_range(col_names[2], row[2], StatsConsts.DISK_RMN_LIFE_MIN,
                               StatsConsts.DISK_RMN_LIFE_MAX, num_of_samples, name)
                check_in_range(col_names[3], row[3], StatsConsts.DISK_FAIL_CNT_MIN,
                               StatsConsts.DISK_FAIL_CNT_MAX, num_of_samples, name)
                check_in_range(col_names[4], row[4], StatsConsts.DISK_FAIL_CNT_MIN,
                               StatsConsts.DISK_FAIL_CNT_MAX, num_of_samples, name)
                check_in_range(col_names[5], row[5], StatsConsts.DISK_FAIL_CNT_MIN,
                               StatsConsts.DISK_FAIL_CNT_MAX, num_of_samples, name)
                check_in_range(col_names[6], row[6], StatsConsts.DISK_TOTAL_LBA_RW_MIN,
                               StatsConsts.DISK_TOTAL_LBA_RW_MAX, num_of_samples, name)
                check_in_range(col_names[7], row[7], StatsConsts.DISK_TOTAL_LBA_RW_MIN,
                               StatsConsts.DISK_TOTAL_LBA_RW_MAX, num_of_samples, name)
        elif name == 'fan':
            for row in reader:
                assert len(row) == num_of_columns, f"number of values ({len(row)}) are not as expected (num_of_columns)"
                num_of_samples += 1
                prev_sample_time = check_sample_timestamp(row, prev_sample_time, name)
                for col in range(1, num_of_columns):
                    check_in_range(col_names[col], row[col], StatsConsts.FAN_MIN,
                                   StatsConsts.FAN_MAX, num_of_samples, name)
        elif name == 'temperature':
            for row in reader:
                assert len(row) == num_of_columns, f"number of values ({len(row)}) are not as expected (num_of_columns)"
                num_of_samples += 1
                prev_sample_time = check_sample_timestamp(row, prev_sample_time, name)
                for col in range(1, num_of_columns):
                    check_in_range(col_names[col], row[col], StatsConsts.TEMP_MIN,
                                   StatsConsts.TEMP_MAX, num_of_samples, name)
        elif name == 'mgmt-interface':
            for row in reader:
                assert len(row) == num_of_columns, f"number of values ({len(row)}) are not as expected (num_of_columns)"
                num_of_samples += 1
                prev_sample_time = check_sample_timestamp(row, prev_sample_time, name)
                for col in range(1, num_of_columns):
                    check_in_range(col_names[col], row[col], StatsConsts.MGMT_INT_MIN,
                                   StatsConsts.MGMT_INT_MAX, num_of_samples, name)
        elif name == 'power':
            for row in reader:
                assert len(row) == num_of_columns, f"number of values ({len(row)}) are not as expected (num_of_columns)"
                num_of_samples += 1
                prev_sample_time = check_sample_timestamp(row, prev_sample_time, name)
                check_in_range(col_names[1], row[1], StatsConsts.PWR_PSU_VOLT_MIN,
                               StatsConsts.PWR_PSU_VOLT_MAX, num_of_samples, name)
                check_in_range_without_na(col_names[2], row[2], StatsConsts.PWR_PSU_VOLT_MIN,
                                          StatsConsts.PWR_PSU_VOLT_MAX, num_of_samples, name)
                check_in_range(col_names[3], row[3], StatsConsts.PWR_PSU_CUR_MIN,
                               StatsConsts.PWR_PSU_CUR_MAX, num_of_samples, name)
                check_in_range_without_na(col_names[4], row[4], StatsConsts.PWR_PSU_CUR_MIN,
                                          StatsConsts.PWR_PSU_CUR_MAX, num_of_samples, name)
        elif name == 'voltage':
            for row in reader:
                assert len(row) == num_of_columns, f"number of values ({len(row)}) are not as expected (num_of_columns)"
                num_of_samples += 1
                prev_sample_time = check_sample_timestamp(row, prev_sample_time, name)
                for col in range(1, num_of_columns - 2):
                    check_in_range(col_names[col], row[col], StatsConsts.VOLTAGE_GENERAL_MIN,
                                   StatsConsts.VOLTAGE_GENERAL_MAX, num_of_samples, name)
                for col in range(num_of_columns - 1, num_of_columns):
                    check_in_range(col_names[col], row[col], StatsConsts.VOLTAGE_PSU_MIN,
                                   StatsConsts.VOLTAGE_PSU_MAX, num_of_samples, name)


def validate_external_file_timestamps(file_name, clear_time):
    full_path = NvosConst.MARS_RESULTS_FOLDER + file_name
    with open(full_path, 'r') as csv_file:
        reader = csv.reader(csv_file)
        idx = 0
        start_data_idx = -1
        for row in reader:
            if row:
                if row[0].startswith("Timestamp"):
                    start_data_idx = idx + 1
                    break
            idx += 1
            if idx == StatsConsts.MAX_ROWS_TO_SCAN:
                break

        assert start_data_idx >= 0, "did not find data start line"

        for row in reader:
            sample_time = datetime.strptime(row[0].replace(StatsConsts.HEADER_TIME, ''),
                                            StatsConsts.TIMESTAMP_FORMAT)
            assert sample_time > clear_time, "Samples time is earlier than clear time"


def validate_number_of_lines_in_external_file(engines, system, cat_name, min_lines, max_lines):
    player = engines['sonic_mgmt']

    with allure.step("Clear external files"):
        engines.dut.run_cmd("sudo rm -f /host/stats/*.csv")

    with allure.step("Generate system stats category"):
        system.stats.category.categoryName[cat_name].action_general(StatsConsts.GENERATE).verify_result()
        stats_files_show = OutputParsingTool.parse_json_str_to_dictionary(system.stats.files.show()). \
            get_returned_value()
        file_name = list(stats_files_show)[0]

    with allure.step("Upload stats file to URL"):
        validate_upload_stats_file(engines, system, file_name, False)

    with allure.step("Validate number of lines in file"):
        full_path = NvosConst.MARS_RESULTS_FOLDER + file_name
        file1 = open(full_path, 'r')
        num_of_lines = len(file1.readlines())
        assert min_lines < num_of_lines < max_lines, \
            f"Number of lines: {num_of_lines} is not as expected: {min_lines}-{max_lines}"

    with allure.step("Delete uploaded file"):
        player.run_cmd(cmd='rm -f {}'.format(full_path))


def validate_stats_files_exist_in_techsupport(system, engine, stats_files):
    """
    generate techsupport and validate stats files exist in the stats dir
    """
    try:
        tech_support_folder, duration = system.techsupport.action_generate(engine=engine)
        logger.info("The techsupport file name is : " + tech_support_folder)
        system.techsupport.extract_techsupport_files(engine)
        techsupport_files_list = system.techsupport.get_techsupport_files_list(engine, 'stats')
        for stat_file in stats_files:
            assert "{}.gz".format(stat_file) in techsupport_files_list, \
                "Expect to have {} file, in the tech support stats files {}".format(stat_file, techsupport_files_list)

    finally:
        system.techsupport.cleanup(engine)
        if system.techsupport.file_name:
            system.techsupport.action_delete(system.techsupport.file_name)


def check_sample_timestamp(row, prev_sample_time, category):
    sample_time = datetime.strptime(row[0].replace(StatsConsts.HEADER_TIME, ''),
                                    StatsConsts.TIMESTAMP_FORMAT)
    expected_time = prev_sample_time + timedelta(minutes=int(StatsConsts.INTERVAL_MIN))
    time_low_thresh = expected_time - timedelta(seconds=5)
    time_high_thresh = expected_time + timedelta(seconds=5)
    assert time_low_thresh < sample_time < time_high_thresh, \
        f"{category} timestamp {sample_time} is too far from expected {expected_time}"
    return sample_time


def check_in_range(col, value, min_val, max_val, sample, category):
    if value != 'N/A':
        assert min_val <= int(value) <= max_val, f"{category} {col} not in range ({value} in sample #{sample}"


def check_in_range_without_na(col, value, min_val, max_val, sample, category):
    assert min_val <= int(value) <= max_val, f"{category} {col} not in range ({value} in sample #{sample}"


def get_header_number_of_lines(engines, category):
    with allure.step(f"Get {category} header number of lines"):
        num_of_lines = int(engines.dut.run_cmd(f"grep -c '^#' /var/stats/{category}.csv")) + 2

    return num_of_lines

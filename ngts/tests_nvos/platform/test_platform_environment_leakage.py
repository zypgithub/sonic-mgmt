import logging
import pytest
import random

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import PlatformConsts, HealthConsts
from infra.tools.redmine.redmine_api import is_redmine_issue_active


logger = logging.getLogger()

OK = HealthConsts.OK
NOT_OK = HealthConsts.NOT_OK


@pytest.mark.platform
def test_platform_environment_bmc_leakage(engines, devices):
    """
    Validate BMC Leakage sensor feature.
        Test flow:
            1. Validate system health is OK by default
            2. Verify default values and fields for platform environment leakage command
            3. Simulate leakage on 1 sensor
            4. Validate output, system health
            5. Return sensor to default value and validate
            6. Simulate leakage on all sensors and validate
            7. Reboot the system and check no leakages
    """
    try:
        with allure.step("Create System object"):
            platform = Platform()
            system = System()

        with allure.step("Validate system health is OK"):
            system.validate_health_status(OK)

        with allure.step("Verify default fields and values"):
            leakage_output = OutputParsingTool.parse_json_str_to_dictionary(platform.environment.leakage.show()) \
                .get_returned_value()

            with allure.step("Verify default fields"):
                ValidationTool.verify_all_fields_value_exist_in_output_dictionary(
                    leakage_output, PlatformConsts.LEAKAGE_DEFAULT_OUTPUT_FIELDS).verify_result()

            with allure.step("Verify default values"):
                ValidationTool.validate_fields_values_in_output(PlatformConsts.LEAKAGE_DEFAULT_OUTPUT_FIELDS,
                                                                PlatformConsts.LEAKAGE_DEFAULT_OUTPUT_VALUES,
                                                                leakage_output).verify_result()

        with allure.step("Simulate leakage on random sensor and validate output"):
            random_selected_leakage = random.choice(PlatformConsts.LEAKAGE_DEFAULT_OUTPUT_FIELDS)
            _simulate_leakage(engines, random_selected_leakage, PlatformConsts.LEAK_STATUS_LEAK)

            with allure.step("Validate output"):
                leakage_output = OutputParsingTool.parse_json_str_to_dictionary(platform.environment.leakage.show()) \
                    .get_returned_value()
                ValidationTool.compare_values(leakage_output[random_selected_leakage]['state'],
                                              PlatformConsts.LEAKAGE_STATUS_LEAK).verify_result()

            with allure.step("Validate system health"):
                system.validate_health_status(NOT_OK)
                history_line = system.health.history.search_line(line_to_search=random_selected_leakage)
                ValidationTool.compare_values(leakage_output[random_selected_leakage]['state'],
                                              PlatformConsts.LEAKAGE_STATUS_LEAK).verify_result()
                health_output = OutputParsingTool.parse_json_str_to_dictionary(system.health.show())\
                    .get_returned_value()
                if not is_redmine_issue_active([3896626])[0]:
                    ValidationTool.compare_values(health_output[HealthConsts.STATUS_LED],
                                                  HealthConsts.LED_NOT_OK_STATUS).verify_result()
                assert random_selected_leakage in history_line, 'Cant find leakage in health history'

            with allure.step("Return leakage status to default"):
                _simulate_leakage(engines, random_selected_leakage, PlatformConsts.LEAK_STATUS_OK)
                leakage_output = OutputParsingTool.parse_json_str_to_dictionary(platform.environment.leakage.show()) \
                    .get_returned_value()
                ValidationTool.compare_values(leakage_output[random_selected_leakage]['state'],
                                              PlatformConsts.LEAKAGE_STATUS_OK).verify_result()

        with allure.step("Simulate leakage on all sensors and validate output"):
            _simulate_leakage(engines, PlatformConsts.LEAKAGE_DEFAULT_OUTPUT_FIELDS)

            with allure.step("Verify output of all sensors"):
                leakage_output = OutputParsingTool.parse_json_str_to_dictionary(platform.environment.leakage.show()) \
                    .get_returned_value()
                ValidationTool.validate_fields_values_in_output(PlatformConsts.LEAKAGE_DEFAULT_OUTPUT_FIELDS,
                                                                PlatformConsts.LEAKAGE_ALL_SENSOR_NOT_OK,
                                                                leakage_output).verify_result()

    finally:
        _link_back_sysfs_files(engines, PlatformConsts.LEAKAGE_DEFAULT_OUTPUT_FIELDS)
        system.validate_health_status(OK)
        leakage_output = OutputParsingTool.parse_json_str_to_dictionary(platform.environment.leakage.show()) \
            .get_returned_value()
        ValidationTool.validate_fields_values_in_output(PlatformConsts.LEAKAGE_DEFAULT_OUTPUT_FIELDS,
                                                        PlatformConsts.LEAKAGE_DEFAULT_OUTPUT_VALUES,
                                                        leakage_output).verify_result()


def _simulate_leakage(engines, leakage, leakage_status=PlatformConsts.LEAK_STATUS_LEAK):
    if isinstance(leakage, str):
        rewrite_files(engines, leakage, leakage_status)
    else:
        for name in leakage:
            rewrite_files(engines, name, leakage_status)


def rewrite_files(engines, name, leakage_status):
    leakage_file = convert_string(name)
    engines.dut.run_cmd("sudo sh -c 'unlink {0}{1} && echo {2} > {0}{1}'".format(PlatformConsts
                                                                                 .LEAKAGE_FILES_FOLDER,
                                                                                 leakage_file, leakage_status))


def _link_back_sysfs_files(engines, leakage):
    for name in leakage:
        leakage_file = convert_string(name)
        engines.dut.run_cmd("sudo sh -c 'rm {0}{1}'".format(PlatformConsts.LEAKAGE_FILES_FOLDER, leakage_file))
        engines.dut.run_cmd("sudo sh -c 'ln -s {2}{1} {0}{1}'".format(PlatformConsts.LEAKAGE_FILES_FOLDER, leakage_file,
                                                                      PlatformConsts.LEAKAGE_FILES_SYSFS_FOLDER))


def convert_string(input_string):
    parts = input_string.split('-')

    main_part = parts[0].lower() + parts[1]

    if len(parts) > 2:
        remaining_parts = '_'.join(parts[2:])
        result = f"{main_part}_{remaining_parts.lower()}"
    else:
        result = main_part.lower()

    return result

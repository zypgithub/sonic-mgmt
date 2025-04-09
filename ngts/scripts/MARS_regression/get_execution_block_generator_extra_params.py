from db_lists_for_nightly_regression import *
from datetime import datetime
import json
import argparse


def get_setup_set_and_group(setup_name):
    for set_name, topo_dict in SETUPS_GROUPS_MAP.items():
        for (_, _), setup_dict in topo_dict.items():
            if setup_name in setup_dict:
                return set_name, setup_dict[setup_name]


def get_test_group_map_by_regression_set(setup_set_name):
    return TEST_GROUP_MAP[setup_set_name]


def get_all_regression_set_tests_list(test_group_map):
    return [test_name for test_name, _ in test_group_map.items()]


def get_daily_platform_agnostic_tests_group_name(setup_group_name):
    weekdays_no_friday = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Saturday', 'Sunday']
    today_name = datetime.today().strftime('%A')
    day_index = weekdays_no_friday.index(today_name)
    is_even_day = day_index % 2 == 0
    if setup_group_name == SETUPS_GROUP_1:
        platform_agnostic_tests_group_name = PLATFORM_AGNOSTIC_GROUP1 if is_even_day else PLATFORM_AGNOSTIC_GROUP2
    else:
        platform_agnostic_tests_group_name = PLATFORM_AGNOSTIC_GROUP2 if is_even_day else PLATFORM_AGNOSTIC_GROUP1
    return platform_agnostic_tests_group_name


def get_tests_list(test_group_map, setup_platform_agnostic_tests_group_name):
    tests_list = [test_name for test_name, test_group in test_group_map.items() if test_group in [PLATFORM_DEPENDENT, setup_platform_agnostic_tests_group_name]]
    return tests_list


def filter_control_tests(tests_list, setup_name, setup_set_name):
    regression_set_name = 'community' if setup_set_name in ['community_set1', 'community_set2'] else 'canonical'
    control_plane_setups_and_tests = CONTROL_PLANE_TESTS_MAP[regression_set_name]
    control_plane_setups = control_plane_setups_and_tests['setups']
    if setup_name not in control_plane_setups:
        tests_list = [test for test in tests_list if test not in control_plane_setups_and_tests['tests']]
    return tests_list


def print_execution_block_generator_in_mars_format(db_paths):
    json_strings = []
    for db_path in db_paths:
        json_obj = {
            'entry_points': 'SONIC_MGMT',
            'tests_dbs_tarball': MARS_DBS_PATH + db_path
        }
        json_strings.append(json.dumps(json_obj))
    result = f"'[{','.join(json_strings)}]'"
    print(f"--meinfo_execution_block_generator {result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Parse input arguments')
    parser.add_argument('--setup_name', type=str, help='Mars setup name')
    parser.add_argument('--run_all_tests', type=str, default='False', help='Flag to run all tests of the setup\'s regression set (community_set1, community_set2 or canonical). Use "True" or "False".')
    args = parser.parse_args()
    setup_name = args.setup_name
    run_all_tests = args.run_all_tests.lower() == 'true'
    setup_set_name, setup_group_name = get_setup_set_and_group(setup_name)
    test_group_map = get_test_group_map_by_regression_set(setup_set_name)
    if run_all_tests:
        daily_tests_per_setup = get_all_regression_set_tests_list(test_group_map)
    else:
        platform_agnostic_tests_group_name = get_daily_platform_agnostic_tests_group_name(setup_group_name)
        daily_tests_per_setup = get_tests_list(test_group_map, platform_agnostic_tests_group_name)
    daily_tests_per_setup = filter_control_tests(daily_tests_per_setup, setup_name, setup_set_name)
    print_execution_block_generator_in_mars_format(daily_tests_per_setup)

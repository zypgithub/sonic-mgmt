from db_lists_for_nightly_regression import *
from datetime import datetime
import json
import argparse

COMMUNITY_SET1_NAME = 'community_set1'
COMMUNITY_SET2_NAME = 'community_set2'
COMMUNITY_LIST_NAMES = [COMMUNITY_SET1_NAME, COMMUNITY_SET2_NAME]
COMMUNITY_NAME = 'community'
CANONICAL_NAME = 'canonical'


def get_setup_set_and_group(setup_name):
    for set_name, topo_dict in SETUPS_GROUPS_MAP.items():
        for (_, _), setup_dict in topo_dict.items():
            if setup_name in setup_dict:
                return set_name, setup_dict[setup_name]
    return None, None


def get_test_group_map_by_regression_set(setup_set_name):
    if 'both' in setup_set_name:
        return {**TEST_GROUP_MAP[COMMUNITY_SET1_NAME], **TEST_GROUP_MAP[COMMUNITY_SET2_NAME]}
    return TEST_GROUP_MAP[setup_set_name]


def get_all_tests_per_set(set_tests_group_map):
    return [test_name for test_name, _ in set_tests_group_map.items()]


def get_daily_platform_agnostic_tests_group_name(setup_group_name, platform_agnostic_tests_group_name_input=None):
    if platform_agnostic_tests_group_name_input:
        return platform_agnostic_tests_group_name_input
    day_of_year = datetime.today().timetuple().tm_yday
    is_even_day = day_of_year % 2 == 0
    if setup_group_name == SETUPS_GROUP_1:
        platform_agnostic_tests_group_name = PLATFORM_AGNOSTIC_GROUP1 if is_even_day else PLATFORM_AGNOSTIC_GROUP2
    else:
        platform_agnostic_tests_group_name = PLATFORM_AGNOSTIC_GROUP2 if is_even_day else PLATFORM_AGNOSTIC_GROUP1
    return platform_agnostic_tests_group_name


def get_tests_list(test_group_map, setup_platform_agnostic_tests_group_name):
    tests_list = [test_name for test_name, test_group in test_group_map.items() if test_group in [PLATFORM_DEPENDENT, setup_platform_agnostic_tests_group_name]]
    return tests_list


def filter_control_tests(tests_list, setup_name, setup_set_name):
    regression_set_name = COMMUNITY_NAME if setup_set_name in COMMUNITY_LIST_NAMES else CANONICAL_NAME
    control_plane_setups_and_tests = CONTROL_PLANE_TESTS_MAP[regression_set_name]
    control_plane_setups = control_plane_setups_and_tests['setups']
    if setup_name not in control_plane_setups:
        tests_list = [test for test in tests_list if test not in control_plane_setups_and_tests['tests']]
    return tests_list


def get_all_available_tests():
    return (
        set(TEST_GROUP_MAP[COMMUNITY_SET1_NAME].keys()) |
        set(TEST_GROUP_MAP[COMMUNITY_SET2_NAME].keys()) |
        set(TEST_GROUP_MAP[CANONICAL_NAME].keys())
    )


def add_remove_dbs_by_input(tests_list, add_dbs, remove_dbs):
    all_available_tests = get_all_available_tests()
    for db in add_dbs:
        if db not in tests_list and db in all_available_tests:
            tests_list.append(db)
    for db in remove_dbs:
        if db in tests_list:
            tests_list.remove(db)
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


def is_setup_exist_in_setups_groups_map(setup_name):
    for category in SETUPS_GROUPS_MAP.values():
        for topology_dict in category.values():
            if setup_name in topology_dict:
                return True
    return False


def proccess_input_args():
    parser = argparse.ArgumentParser(description='Parse input arguments')
    parser.add_argument('--setup_name', type=str, help='Mars setup name')
    parser.add_argument('--run_all_tests', type=str, default='False', help='Flag to run all tests of the setup\'s regression set (community_set1, community_set2 or canonical). Use "True" or "False".')
    parser.add_argument('--set_name', type=str, default=None, help='update setups\'s set (canonical, set1, set2 or both). When provided, run_all_tests is set to True.')
    parser.add_argument('--platform_agnostic_group', type=str, default=None, help='override platform agnostic tests group name. Has no effect if run_all_tests is True or set_name is provided')
    parser.add_argument("--add_dbs", nargs='*', default=[], help='add dbs to the execution block generator. Example  --add_dbs "community/ip_neigh.db" "community/resources.db"')
    parser.add_argument('--remove_dbs', nargs='*', default=[], help='remove dbs from the execution block generator. Example  --remove_dbs "community/ip_neigh.db" "community/resources.db" ')

    args = parser.parse_args()
    setup_name = args.setup_name
    run_all_tests = args.run_all_tests.lower() == 'true'
    override_set_name = args.set_name
    platform_agnostic_tests_group_name = args.platform_agnostic_group
    add_dbs = args.add_dbs
    remove_dbs = args.remove_dbs
    return setup_name, run_all_tests, override_set_name, platform_agnostic_tests_group_name, add_dbs, remove_dbs


if __name__ == "__main__":
    setup_name, run_all_tests, override_set_name, platform_agnostic_tests_group_name_input, add_dbs, remove_dbs = proccess_input_args()
    setup_set_name, setup_group_name = get_setup_set_and_group(setup_name)
    if not is_setup_exist_in_setups_groups_map(setup_name) and not override_set_name:
        daily_tests_per_setup = []
    else:
        if override_set_name:
            setup_set_name = override_set_name if override_set_name == 'canonical' else 'community_' + override_set_name
            run_all_tests = True
        set_tests_group_map = get_test_group_map_by_regression_set(setup_set_name)
        if run_all_tests:
            daily_tests_per_setup = get_all_tests_per_set(set_tests_group_map)
        else:
            platform_agnostic_tests_group_name = get_daily_platform_agnostic_tests_group_name(setup_group_name, platform_agnostic_tests_group_name_input)
            daily_tests_per_setup = get_tests_list(set_tests_group_map, platform_agnostic_tests_group_name)
        daily_tests_per_setup = filter_control_tests(daily_tests_per_setup, setup_name, setup_set_name)
        daily_tests_per_setup = add_remove_dbs_by_input(daily_tests_per_setup, add_dbs, remove_dbs)
    print_execution_block_generator_in_mars_format(daily_tests_per_setup)

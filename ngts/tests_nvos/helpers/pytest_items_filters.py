import random

from ngts.nvos_constants.constants_nvos import OSType
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType


def run_nvos_pytest_items_modification(config, items):
    # Setup
    original_count = len(items)
    deselected_items = []

    # Call deselection/filtering logics
    deselect_ipv6_aaa_tests_for_cl(config, items, deselected_items)
    deselect_tests_by_max_case_instances_option(config, items, deselected_items)

    # Report & finish
    # Report deselected items
    if deselected_items:
        config.hook.pytest_deselected(items=deselected_items)

    # Update collection stats
    config.pluginmanager.set_blocked(("deselected", len(deselected_items)))


def update_selected_and_deselected_items(items, deselected_items, new_selected, new_deselect):
    # Replace the original items with the new selection
    items[:] = new_selected
    # report deselected
    deselected_items.extend(new_deselect)


def deselect_tests_by_max_case_instances_option(config, items, deselected_items):
    max_case_instances: int = config.getoption("--max_case_instances")

    if max_case_instances is not None and max_case_instances > 0:
        final_selected = []
        final_deselected = []

        # Group tests by their function name
        grouped_tests = {}
        for item in items:
            test_func = item.originalname or item.name
            if test_func not in grouped_tests:
                grouped_tests[test_func] = []
            grouped_tests[test_func].append(item)

        # Randomly select instances for each test function
        force_all_markers = ['force_all_params', 'force_all', 'use_all_params']
        for test_func, test_instances in grouped_tests.items():
            force_all = any(
                any(item.get_closest_marker(marker) for marker in force_all_markers)
                for item in test_instances
            )
            if force_all:
                final_selected.extend(test_instances)
            else:
                selected = random.sample(test_instances, min(max_case_instances, len(test_instances)))
                deselected = [instance for instance in test_instances if instance not in selected]
                final_selected.extend(selected)
                final_deselected.extend(deselected)

        # Finish
        update_selected_and_deselected_items(items, deselected_items, final_selected, final_deselected)


def deselect_ipv6_aaa_tests_for_cl(config, items, deselected_items):
    os_type: str = config.getoption("--os_type") or OSType.NVOS

    if os_type != OSType.CL:
        return

    test_param_name = 'addressing_type'

    final_deselected = []
    final_selected = []
    for item in items:
        if hasattr(item, 'callspec') and test_param_name in item.callspec.params:
            if item.callspec.params[test_param_name] == AddressingType.IPV6:
                final_deselected.append(item)
            else:
                final_selected.append(item)
        else:
            final_selected.append(item)

    # Finish
    update_selected_and_deselected_items(items, deselected_items, final_selected, final_deselected)

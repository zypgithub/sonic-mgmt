import logging
import os
import random

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.constants.constants import REGRESSION_TYPE_ENV_VAR, RegressionType

logger = logging.getLogger(__name__)

API_TYPE_PARAM_VALUES = set(ApiType.ALL_TYPES)


def run_nvos_pytest_items_modification(config, items):
    # Setup
    original_count = len(items)
    deselected_items = []

    # Call deselection/filtering logics
    deselect_duplicate_api_type_tests_in_ci(config, items, deselected_items)
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


def _is_ci_run():
    """Check if this is a CI run based on the REGRESSION_TYPE environment variable."""
    regression_type = os.environ.get(REGRESSION_TYPE_ENV_VAR)
    return regression_type is not None and regression_type in RegressionType.ci_types()


def _get_api_type_param(item):
    """Return the ApiType param value if the item is parametrized by test_api, else None."""
    for marker in item.iter_markers('parametrize'):
        param_names = marker.args[0]
        # param_names can be a comma-separated string or a list
        if isinstance(param_names, str):
            names = [n.strip() for n in param_names.split(',')]
        else:
            names = list(param_names)
        if 'test_api' in names:
            if hasattr(item, 'callspec') and 'test_api' in item.callspec.params:
                val = item.callspec.params['test_api']
                if val in API_TYPE_PARAM_VALUES:
                    return val
    return None


def _get_other_params(item):
    """Return a frozen key of all callspec params except test_api."""
    if not hasattr(item, 'callspec'):
        return ()
    return tuple(sorted((k, repr(v)) for k, v in item.callspec.params.items() if k != 'test_api'))


def deselect_duplicate_api_type_tests_in_ci(config, items, deselected_items):
    """In CI runs, keep only one random API variant for tests parametrized with ApiType.ALL_TYPES.

    Tests parametrized with both NVUE and OpenApi produce two items that exercise
    the same logic via different APIs. In CI we only need one to save time.
    For each such duplicate group, one variant is kept at random and the rest are deselected.
    """
    if not _is_ci_run():
        return

    # Group items by (module, originalname, other_params) — only for items with a test_api param.
    # other_params ensures tests that differ by non-API params (e.g. force_str, test_flow)
    # are NOT collapsed together.
    api_groups = {}
    for item in items:
        api_type = _get_api_type_param(item)
        if api_type is not None:
            key = (str(item.fspath), item.originalname, _get_other_params(item))
            api_groups.setdefault(key, []).append((api_type, item))

    if not api_groups:
        return

    # Pick one random variant per group, mark the rest for deselection
    deselect_set = set()
    for key, variants in api_groups.items():
        if len(variants) > 1:
            chosen_api, chosen_item = random.choice(variants)
            for api_type, item in variants:
                if item is not chosen_item:
                    logger.info("CI api-type filter: deselecting %s (keeping %s variant for %s)",
                                item.nodeid, chosen_api, item.originalname)
                    deselect_set.add(id(item))

    if not deselect_set:
        return

    # Preserve original ordering
    final_selected = []
    final_deselected = []
    for item in items:
        if id(item) in deselect_set:
            final_deselected.append(item)
        else:
            final_selected.append(item)

    update_selected_and_deselected_items(items, deselected_items, final_selected, final_deselected)


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

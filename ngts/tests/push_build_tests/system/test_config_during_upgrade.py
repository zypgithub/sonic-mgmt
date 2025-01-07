import logging
import pytest
import yaml
import json
import os
import allure

from deepdiff import DeepDiff


logger = logging.getLogger()
PRE_UPGRADE_CONFIG = '/tmp/config_db_{}_base.json'
POST_UPGRADE_CONFIG = '/tmp/config_db_{}_target.json'


def test_validate_config_db_json_during_upgrade(upgrade_params, testdir, engines, cli_objects,
                                                allowed_diff_file='upgrade_allowed_diff.yaml'):
    """
    This tests checking diff in config_db.json between base and target version
    Test expects that we already have config_db.json for base and target version in /tmp folder
    We getting config for base and target version during push_gate_config fixture execution(in case of upgrade)
    """
    if not upgrade_params.is_upgrade_required:
        pytest.skip('Upgrade was not ran, no need to compare configs')
    test_folder_path = testdir.request.fspath.dirname
    allowed_diff_file_path = os.path.join(test_folder_path, allowed_diff_file)

    with allure.step('Getting base and target versions'):
        base_image, target_image = cli_objects.dut.general.get_base_and_target_images()
        assert base_image, 'Only 1 installed image available'

    with allure.step('Comparing configurations before and after the upgrade'):
        upgrade_diff = compare_dut_configs(base_config=PRE_UPGRADE_CONFIG.format(engines.dut.ip),
                                           target_config=POST_UPGRADE_CONFIG.format(engines.dut.ip),
                                           base_ver=base_image,
                                           target_ver=target_image,
                                           allowed_diff_file=allowed_diff_file_path)

    with allure.step('Checking diff in config_db.json between base and target versions'):
        if upgrade_diff:
            allure.attach.file(PRE_UPGRADE_CONFIG.format(engines.dut.ip),
                               'base_config_db.json', allure.attachment_type.JSON)
            allure.attach.file(POST_UPGRADE_CONFIG.format(engines.dut.ip),
                               'target_config_db.json', allure.attachment_type.JSON)
            raise AssertionError('Found unexpected diff in config_db.json during upgrade: \n {}'.format(upgrade_diff))


def compare_dut_configs(base_config, target_config, base_ver, target_ver, allowed_diff_file):
    """
    This method compare base and target config_db.json files.
    Then it compare diff which was found with allowed_diff_file - it unallowed diff found - then return
    list with unexpected diff
    """

    unexpected_diff_list = []
    ignored_items = "ignored_items"
    with open(base_config) as base:
        base_dict = json.load(base)
    with open(target_config) as target:
        target_dict = json.load(target)

    with open(allowed_diff_file) as diff_file:
        allowed_diff_keys = yaml.load(diff_file, Loader=yaml.FullLoader)

    base_branch = None
    target_branch = None

    for base in allowed_diff_keys.keys():
        if '{}'.format(base) in base_ver:
            for target in allowed_diff_keys[base].keys():
                if '{}'.format(target) in target_ver:
                    base_branch = base
                    target_branch = target
                    break
    if not (base_branch and target_branch):
        allowed_diff_for_our_branch = {'dictionary_item_added': []}
    else:
        allowed_diff_for_our_branch = allowed_diff_keys[base_branch][target_branch]

    diff = DeepDiff(base_dict, target_dict)

    for key, value in diff.items():
        logger.info('Found next difference in config_db.json after upgrade: {} \n {}'.format(key, diff[key]))
        for diff_item in value:
            if diff_item not in allowed_diff_for_our_branch.get(key, []) and diff_item not in \
                    allowed_diff_for_our_branch.get(ignored_items, []):
                logger.error('Found unexpected diff in config_db.json after upgrade: {} \n {}'.format(key, diff_item))
                unexpected_diff_list.append({key: diff_item})

    for key, value in allowed_diff_for_our_branch.items():
        if key == ignored_items:
            continue
        for diff_item in value:
            if diff_item not in diff.get(key, []):
                logger.error('Expected diff not found in config_db.json after upgrade: {} \n {}'.format(key, diff_item))
                unexpected_diff_list.append({key: diff_item})

    return unexpected_diff_list

import allure

import ngts.helpers.acl_helper as acl_helper


def test_acl_config(cli_objects, engines, acl_base_configuration, acl_table_config_list):
    """
    Test the acl tables and rules can be added and removed correctly
    :param cli_objects: cli_objects fixture
    :param engines: engines fixture
    :param acl_base_configuration: acl_base_configuration fixture
    :param acl_table_config_list: acl_table_config_list fixture, which is a list of value returned from
    generate_acl_table
    """
    do_acl_config_test(cli_objects, engines, acl_base_configuration, acl_table_config_list)


def do_acl_config_test(cli_objects, engines, acl_base_configuration, acl_table_config_list):
    """
    Contains all logic for acl config test
    :param cli_objects: cli_objects fixture
    :param engines: engines fixture
    :param acl_base_configuration: acl_base_configuration fixture
    :param acl_table_config_list: acl_table_config_list fixture, which is a list of value returned from
    """
    cli_obj = cli_objects.dut
    engine = engines.dut
    with allure.step('Verify the acl tables are added'):
        acl_helper.verify_acl_tables_exist(cli_obj, acl_table_config_list, True)
    with allure.step('Verify the acl rules are added'):
        acl_helper.verify_acl_rules(cli_obj, acl_table_config_list, True)
    with allure.step('Remove acl rules'):
        acl_helper.clear_acl_rules(engine, cli_obj)
    with allure.step('Verify the acl rules are removed'):
        acl_helper.verify_acl_rules(cli_obj, acl_table_config_list, False)
    with allure.step('Delete acl table'):
        acl_helper.remove_acl_table(cli_obj, acl_table_config_list)
    with allure.step('Verify the acl tables are removed'):
        acl_helper.verify_acl_tables_exist(cli_obj, acl_table_config_list, False)
    with allure.step('Add acl table'):
        acl_helper.add_acl_table(cli_obj, acl_table_config_list)
    with allure.step('Add acl rules'):
        acl_helper.add_acl_rules(engine, cli_obj, acl_table_config_list)
    with allure.step('Verify the acl tables are added back'):
        acl_helper.verify_acl_tables_exist(cli_obj, acl_table_config_list, True)
    with allure.step('Verify the acl rules are added back'):
        acl_helper.verify_acl_rules(cli_obj, acl_table_config_list, True)

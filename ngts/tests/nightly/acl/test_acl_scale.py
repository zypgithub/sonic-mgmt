from test_acl import do_acl_config_test


def test_acl_config_scale(cli_objects, engines, acl_base_configuration, acl_table_config_list_scale):
    """
    Test the acl tables and rules can be added and removed correctly in scale config
    :param cli_objects: cli_objects fixture
    :param engines: engines fixture
    :param acl_base_configuration: acl_base_configuration fixture
    :param acl_table_config_list: acl_table_config_list fixture, which is a list of value returned from
    generate_acl_table
    """
    do_acl_config_test(cli_objects, engines, acl_base_configuration, acl_table_config_list_scale)

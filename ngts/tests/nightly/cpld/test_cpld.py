import allure
import logging

from ngts.cli_util.cli_parsers import generic_sonic_output_parser
from ngts.helpers.secure_boot_helper import SonicSecureBootHelper

logger = logging.getLogger()

POSSIBLE_CPLD_LIST = ['CPLD1', 'CPLD2', 'CPLD3', 'CPLD4']


def test_cpld_version_check(engines, platform_params):
    """
    This test validates that the CPLD version(s) deployed on the dut are the latest approved ones,
    as defined in the firmware.json versions file.
    :param engines: engines fixture
    :param platform_params: platform_params fixture
    """
    with allure.step('Getting info about the CPLD component from firmware.json'):
        cpld_component_data = None
        defined_cpld = None
        for cpld in POSSIBLE_CPLD_LIST:
            try:
                cpld_component_data = SonicSecureBootHelper.get_component_data(platform_params, cpld)
                defined_cpld = cpld
                break
            except Exception as e:
                logger.info(e)
                pass
        assert (defined_cpld and cpld_component_data), \
            "Failed to get the data for any CPLD from the firmware.json"

    with allure.step('Getting info about CPLD from dut'):
        component_versions_dict = get_info_about_current_components_version_dict(engines.dut)

    with allure.step(f'Checking CPLD version for: {defined_cpld}'):
        _, latest_cpld_ver = SonicSecureBootHelper.get_latest_expected_cpld(cpld_component_data, defined_cpld)
        current_cpld_ver = component_versions_dict[defined_cpld]
        assert current_cpld_ver == latest_cpld_ver, \
            f'Current {defined_cpld} version: {current_cpld_ver} is not latest: {latest_cpld_ver}'


def get_info_about_current_components_version_dict(engine):
    """
    Get dictionary with component name as key and version as value
    :param engine: dut engine
    :return: dictionary with component name as key and version as value
    """

    fwutil_show_status_output = engine.run_cmd('sudo fwutil show status')
    fwutil_show_status_dict = generic_sonic_output_parser(fwutil_show_status_output)
    component_names_list = fwutil_show_status_dict[0]['Component']
    component_versions_list = fwutil_show_status_dict[0]['Version']
    component_versions_dict = {}
    for component, version in zip(component_names_list, component_versions_list):
        component_versions_dict[component] = version

    return component_versions_dict

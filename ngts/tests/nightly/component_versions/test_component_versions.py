import os
import re
import pytest
import logging
import allure
from ngts.cli_util.cli_parsers import generic_sonic_output_parser
from ngts.tests.nightly.cpld.test_cpld import get_info_about_current_components_version_dict

logger = logging.getLogger()

COMPONENT_SCRIPT_NAME = "get_component_versions.py"
README_COVERED_COMPONENTS = ['SDK', 'FW', 'SAI', 'HW_MANAGEMENT', 'MFT', 'SIMX', 'KERNEL']
FW_DEFAULT_VERSIONS = ['ONIE', 'SSD', 'BIOS', 'CPLD']  # Expected columns of the table if the setup is SIMX
COMMANDS_FOR_ACTUAL = {
    "MFT": ["dpkg -l | grep -e 'mft '", "mft *([0-9.-]*)"],
    "HW_MANAGEMENT": ["dpkg -l | grep hw", ".*1\\.mlnx\\.([0-9.]*)"],
    "SDK": ["docker exec -it syncd bash -c 'dpkg -l | grep sdk'", ".*1\\.mlnx\\.([0-9.]*)"],
    "SAI": ["docker exec -it syncd bash -c 'dpkg -l | grep mlnx-sai'", ".*1\\.mlnx\\.([A-Za-z0-9.]*)"],
    "FW": ["sudo mlxfwmanager --query | grep -e 'FW *[0-9.]*'", "FW * [0-9]{2}\\.([0-9.]*)"],
    "KERNEL": ["uname -r", "([0-9][0-9.-]*)-.*"],
    "SIMX": ["sudo lspci -vv | grep SimX", "([0-9]+\\.[0-9]+-[0-9]+)"]
}

# non-existent versions are versions that aren't supposed to appear, like BIOS compilation versions while unexpected
# missing versions are components that aren't available on the current setup, like fw versions on simx setups.
NON_EXISTENT_VERSION = '-'
UNEXPECTED_MISSING_VERSION = 'N/A'


def parse_component_version_table(engines):
    """
    The function parses the component version table gotten as the output of get_components_version.py script

    :param engines:  engines fixture
    :return: A dictionary, stating for each component what is the compilation version and what is the actual version.
    Example - {"SDK", ("4.6.2202", "4.6.2202")}
    """
    expected_component_version_table = engines.dut.run_cmd(f"sudo {COMPONENT_SCRIPT_NAME}")
    parsed_table = generic_sonic_output_parser(expected_component_version_table)
    version_dict = dict()
    for component_info in parsed_table:
        component = component_info['COMPONENT']
        compilation_version = component_info['COMPILATION']
        actual_version = component_info['ACTUAL']
        version_dict[component] = (compilation_version, actual_version)
    logger.info(f"Parsed components from {COMPONENT_SCRIPT_NAME} are (compilation, actual): {version_dict}")
    return version_dict


def parse_readme_versions(sonic_image):
    """
    The function parses the component version table gotten as the output of get_components_version.py script
    :param sonic_image: the current sonic image deployed on the dut
    :return: A dictionary, stating for each component what is the readme version of it, example - {"SDK", "4.6.2202"}
    """
    readme_path = os.path.realpath(f"/auto/sw_system_release/sonic/{sonic_image}/dev/README")
    if not os.path.exists(readme_path):
        raise Exception(f"Sonic image path: {readme_path} doesn't include a README file")
    logger.info(f"Parsing versions according to readme file: {readme_path}")
    with open(readme_path) as f:
        image_readme_content = f.read()
    readme_versions_dict = dict()

    # First match the version with the suffix "_VERSION_SWITCH"
    # Then match the version with the suffix "_VERSION"
    patterns = [
        re.compile(r"(?P<component>\w+)_VERSION_SWITCH:\s*(?P<version>[^\s]+)"),
        re.compile(r"(?P<component>\w+)_VERSION:\s*(?P<version>[^\s]+)")
    ]

    for line in image_readme_content.strip().split('\n'):
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                component = str(match.group('component').strip())
                # Add only if the component is in the README_COVERED_COMPONENTS and not stored in readme_versions_dict
                if component in README_COVERED_COMPONENTS and component not in readme_versions_dict:
                    version = str(match.group('version').strip())
                    readme_versions_dict[component] = version
                break

    logger.info(f"Parsed components from {readme_path} are:\n {readme_versions_dict}")
    return readme_versions_dict


def get_actual_version(dut_engine, component):
    """
    The function fetches the current version of the component from the dut engine and returns it.
    :param dut_engine: the dut engine
    :param component: the component to fetch version for
    :return: The version of "component" as it appears on the dut
    """
    dut_command_ind = 0
    command_regex_ind = 1
    required_regex_group = 1
    cmd = COMMANDS_FOR_ACTUAL[component][dut_command_ind]
    version = dut_engine.run_cmd(cmd)
    parsed_version = re.search(COMMANDS_FOR_ACTUAL[component][command_regex_ind], str(version))
    return parsed_version.group(required_regex_group) if parsed_version else "N/A"


def fetch_versions_from_dut(dut_engine, is_simx):
    """
    The function fetches the versions installed on the dut in runtime
    :param dut_engine: the dut engine
    :param is_simx: is_simx fixture
    :return: A dictionary, stating for each component what is the actual version of it, example - {"SDK", "4.6.2202"}
    """
    actual_versions_dict = dict()
    for component in COMMANDS_FOR_ACTUAL:
        if component == "SIMX" and not is_simx:
            # no need to fetch simx version from dut if the dut is not simx - the test won't verify this version
            continue
        else:
            actual_versions_dict[component] = get_actual_version(dut_engine, component)
    if not is_simx:
        actual_versions_dict.update(get_info_about_current_components_version_dict(dut_engine))
    else:
        for component in FW_DEFAULT_VERSIONS:
            actual_versions_dict[component] = UNEXPECTED_MISSING_VERSION
    logger.info(f"Components fetched from the dut are {actual_versions_dict}")

    return actual_versions_dict


@pytest.fixture
def readme_versions(cli_objects):
    """
    Fixture to fetch the versions of components listed in the readme file of the image running on the dut.
    :param cli_objects: cli_objects fixture
    :return: A dictionary, stating for each component what is the readme version of it, example - {"SDK", "4.6.2202"}

    """
    _, sonic_image = cli_objects.dut.general.get_base_and_target_images()
    # The full image contains SONiC-OS-ActualImage and we want the ActualImage
    sonic_image = sonic_image.replace("SONiC-OS-", "")
    sonic_image = sonic_image.replace("_ASAN", "")
    yield parse_readme_versions(sonic_image)


@allure.title('Test Component Versions')
def test_component_versions(cli_objects, engines, readme_versions, is_simx):
    """
    Verify that the component versions printed by get_component_versions.py for each of the components listed in
    COMPONENTS_LIST are as expected. This is done by comparing the script output to expected versions, either those
    in the readme file of the image or via running commands on the dut.
    :param cli_objects: cli_objects fixture
    :param engines: pre_test_interface_data fixture
    :param is_simx: is_simx fixture
    :param readme_versions: readme_versions fixture
    """
    expected_component_versions = parse_component_version_table(engines)
    actual_versions = fetch_versions_from_dut(engines.dut, is_simx)
    assert set(actual_versions.keys()) == set(expected_component_versions.keys())
    for component in actual_versions.keys():
        compilation_version, actual_version = expected_component_versions[component]
        if component in readme_versions:
            assert compilation_version == readme_versions[component]
        else:
            assert compilation_version == NON_EXISTENT_VERSION
        assert actual_version == actual_versions[component]

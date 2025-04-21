import re

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import SystemConsts, OutputFormat
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import loganalyzer_ignore
import logging
import pytest

logger = logging.getLogger()


@pytest.mark.general
@pytest.mark.tech_support
def test_techsupport_folder_name(engines):
    """
    Test flow:
        1. get time
        2. run nv action generate system tech-support
        3. validate the tar.gz name is /host/dump/nvos_dump_<hostname>_<date>_<time>.tar.gz
    """
    with allure.step('Run nv action generate system tech-support and validate the tech-support name'):
        system = System(None)
        output_dictionary_before = list(OutputParsingTool.parse_show_files_to_dict(
            system.techsupport.show()).get_returned_value().values())
        tech_support_folder, duration = system.techsupport.action_generate()
        validate_techsupport_folder_name(system, tech_support_folder)
        output_dictionary_after = list(OutputParsingTool.parse_show_files_to_dict(
            system.techsupport.show()).get_returned_value().values())

        cleanup_techsupport(engines.dut, output_dictionary_before, output_dictionary_after)


@pytest.mark.general
@pytest.mark.tech_support
def test_techsupport_with_dockers_down(engines, dockers_list=['gnmi-server']):
    """
    Test flow:
        1. run sudo systemctl stop ib-utils
        2. run nv action generate system tech-support
        3. validate it's working as expected
    """
    try:
        with allure.step('Run nv action generate system tech-support while at least one docker is down'):
            system = System(None)
            for docker in dockers_list:
                engines.dut.run_cmd('sudo systemctl stop {docker}'.format(docker=docker))
            tech_support_folder, duration = system.techsupport.action_generate()
        with allure.step('validate commands works as expected'):
            assert 'nvos_dump' in tech_support_folder, "{err}".format(err=tech_support_folder)

        cleanup_techsupport(engines.dut, [], [tech_support_folder])

    finally:
        for docker in dockers_list:
            engines.dut.run_cmd('sudo systemctl start {docker}'.format(docker=docker))


@pytest.mark.general
@pytest.mark.tech_support
@pytest.mark.timeout(20 * MINUTE, func_only=True)
def test_techsupport_expected_files(engines, devices, test_name):
    """
    Run nv show system tech-support files command and verify the required fields are exist
    and measure how long it takes
    command: nv show system tech-support files

    Test flow:
        1. get_expected dummy files per device
        2. get new files after configurations
        3. run nv action generate system tech-support
        4. verify files' names of techsupport using expected_files_dict
        5. verify files' sizes of techsupport using expected_files_dict
    """

    system = System()
    expected_files_dict = {'dump': devices.dut.constants.dump_files,
                           'sai_sdk_dump0': devices.dut.constants.sdk_dump_files,
                           'log': devices.dut.constants.log_dump_files,
                           'log/nginx': devices.dut.constants.log_nginx_files,
                           'stats': devices.dut.constants.stats_dump_files,
                           'hw-mgmt': devices.dut.constants.hw_mgmt_files,
                           'etc': devices.dut.constants.etc_files}

    if devices.dut.has_nmx:
        cluster_files = getattr(devices.dut.constants, 'cluster_files', None)
        expected_files_dict['log/nmx/nmx-c'] = devices.dut.constants.log_nmx_files
        if cluster_files:
            expected_files_dict['cluster'] = cluster_files

    if devices.dut.has_bmc:
        bmc_dump_files = getattr(devices.dut.constants, 'bmc_dump_files', None)
        expected_files_dict['bmc'] = bmc_dump_files

    try:
        if devices.dut.has_nmx:
            cluster = Cluster()
            with allure.step("Start cluster"):
                output = OutputParsingTool.parse_show_output_to_dict(
                    cluster.show(output_format=OutputFormat.json),
                    output_format=OutputFormat.json).get_returned_value()

                if output[SystemConsts.STATE] == 'disabled':
                    cluster.set(op_param_name="state", op_param_value='enabled', apply=True)
                    ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='enabled', nmx_c_expected_state='up')

        with allure.step('Run nv action generate system tech-support and validate dump files'):
            tech_support_folder, duration = system.techsupport.action_generate(test_name=test_name)
            with allure.step("Tech-support generation takes: {} seconds".format(duration)):
                logger.info("Tech-support generation takes: {} seconds".format(duration))
            system.techsupport.extract_techsupport_files(engines.dut)
            techsupport_files_dict = system.techsupport.get_techsupport_files_names(engines.dut, expected_files_dict)
        with allure.step("validate each expected file name and size"):
            with allure.independent_step('validate files names'):
                techsupport_files_dict['sai_sdk_dump0'] = system.techsupport.clean_timestamp_techsupport_sdk_files_names(techsupport_files_dict['sai_sdk_dump0'])
                for folder, files in techsupport_files_dict.items():
                    verify_techsupport_files_names(files, expected_files_dict[folder])

            with allure.independent_step('validate files sizes'):
                for folder in expected_files_dict.keys():
                    if expected_files_dict[folder]:  # skip empty folders if files are not expected for a specific system
                        files_list = system.techsupport.get_techsupport_empty_files(engines.dut, folder)
                        verify_techsupport_files_sizes(files_list, folder)
    finally:
        if devices.dut.has_nmx:
            Cluster().unset(apply=True)
            ClusterTools.wait_for_apps_to_be_in_wanted_state(cluster, cluster_expected_state='disabled', nmx_c_expected_state='down')
        system.techsupport.cleanup(engines.dut)
        if system.techsupport.file_name:
            system.techsupport.action_delete(system.techsupport.file_name)


@pytest.mark.general
@pytest.mark.tech_support
def test_techsupport_bmc_badflow(engines, test_name):
    """
    This test verifies the behavior of the system when generating tech-support data and handling BMC failures.

    Steps:
    1. Initialize the system object.
    2. Retrieve the password for BMC from TPM.
    3. Gracefully restart the BMC via Redfish.
    4. Generate system tech-support data.
    5. Extract tech-support files.
    6. Verify that the BMC folder in the tech-support files is empty.
    7. Check for the specific error message in the system logs.
    8. Perform cleanup operations.
    """

    system = System()
    try:
        dut_engine: LinuxSshEngine = TestToolkit.engines.dut
        with loganalyzer_ignore():  # supposed to be able to ignore LA here because #4223438
            with allure.step('gracefully restart bmc via redfish'):
                BmcTool.reset(dut_engine)

            with allure.step('Run nv action generate system tech-support'):
                tech_support_folder, duration = system.techsupport.action_generate(test_name=test_name)
                with allure.step("Tech-support generation takes: {} seconds".format(duration)):
                    logger.info("Tech-support generation takes: {} seconds".format(duration))

            system.techsupport.extract_techsupport_files(engines.dut)

            with allure.step('verify bmc folder is empty'):
                files_list = system.techsupport.get_techsupport_files_list(engines.dut, 'bmc')
                assert not files_list, f'bmc folder is not empty and got: {files_list}'

            with allure.step('verify error msg in logs'):
                output = engines.dut.run_cmd("cat /var/log/syslog | grep -a 'bmc_techsupport.py'")
                assert re.search(r'Failed to (extract|collect) BMC debug log dump',
                                 output), f"Expected to find 'Failed to extract/collect BMC debug log dump' in output. Got: {output}"
    finally:
        engines.dut.run_cmd("sudo ifup usb0")
        system.techsupport.cleanup(engines.dut)
        if system.techsupport.file_name:
            system.techsupport.action_delete(system.techsupport.file_name)


def cleanup_techsupport(engine, before, after):
    new_folders = [file for file in after if file not in before]
    for dump in new_folders:
        engine.run_cmd('sudo rm -rf ' + dump)


def verify_techsupport_files_names(files_list, expected_files):
    """
    :param files: list of files
    :param expected_files: list of expected files
    :param device: Noga device info
    :return: None
    """
    files = [file for file in expected_files if file not in files_list]
    assert len(files) == 0, "the next files are missed {files}".format(files=files)
    files = [file for file in files_list if file not in expected_files]
    if len(files) != 0:
        logger.warning("the next files are in the dump folder but not in our check list {files}".format(files=files))


def verify_techsupport_files_sizes(files_list, folder):
    if folder == 'dump':
        files_list = [file for file in files_list if file not in SystemConsts.TECHSUPPORT_DUMP_EMPTY_FILES_TO_IGNORE]
    elif folder == 'etc':
        files_list = [file for file in files_list if file not in SystemConsts.TECHSUPPORT_ETC_EMPTY_FILES_TO_IGNORE]

    assert len(files_list) == 0, f"the next files are empty {files_list}"


def validate_techsupport_folder_name(system, tech_support_folder):
    """
    Test flow:
        1. run nv show system
        2. get the hostname value
        3. validate the tar.gz name is nvos_dump_<hostname>_<time_now>.tar.gz
    """
    with allure.step('Check that tech-support name is as expected :nvos_dump_<hostname>_<time_now>.tar.gz'):
        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        hostname = system_output[SystemConsts.HOSTNAME]
        assert 'nvos_dump_' + hostname in tech_support_folder, 'the tech-support should be under host dump and includes hostname'

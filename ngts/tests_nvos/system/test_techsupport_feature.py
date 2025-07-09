import re
from typing import Optional

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import IssuConsts, NtpConsts, SystemConsts, OutputFormat
from ngts.tests_nvos.cluster.cluster_tools import ClusterTools
from ngts.nvos_tools.nmx.Cluster import Cluster
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import loganalyzer_ignore
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active
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
        4. Verify obscurity of config files
        5. verify files' names of techsupport using expected_files_dict
        6. verify files' sizes of techsupport using expected_files_dict
    """

    LDAP_SECRET: str = 'ldap_pass'
    RADIUS_SECRET: str = 'radius_pass'
    TACACS_SECRET: str = 'tacacs_pass'
    password_pattern = r'password[^:]*: [\"\']*([^\"\'\s]+)'
    login_cmd_pattern = r'COMMAND=/usr/sbin/usermod --password\s([^\s]+)'

    config_file_secret_dict = {
        'ldap': {
            'secret': LDAP_SECRET,
            'pattern': r"ldap.+\s+[\"\']*secret[^:]*:\s[\"\']*([^\"\'\s]+)",
            'set_nv_cmd': lambda: system.aaa.ldap.set(op_param_name='secret', op_param_value=LDAP_SECRET).verify_result()
        },
        'radius': {
            'secret': RADIUS_SECRET,
            'pattern': r"radius.+\s+[\"\']*secret[^:]*:\s[\"\']*([^\"\'\s]+)",
            'set_nv_cmd': lambda: system.aaa.radius.set(op_param_name='secret', op_param_value=RADIUS_SECRET).verify_result()
        },
        'tacacs': {
            'secret': TACACS_SECRET,
            'pattern': r"tacacs.+\s+[\"\']*secret[^:]*:\s[\"\']*([^\"\'\s]+)",
            'set_nv_cmd': lambda: system.aaa.tacacs.set(op_param_name='secret', op_param_value=TACACS_SECRET).verify_result()
        },
        'ntp_key': {
            'secret': NtpConsts.KEY_VALUE,
            'pattern': r'key[^:]*:\s+[\"\']*([^\"\'\s]+)',
            'set_nv_cmd': lambda: (
                system.ntp.keys.set_resource(NtpConsts.KEY_1).verify_result(),
                system.ntp.keys.resources_dict[NtpConsts.KEY_1].set(op_param_name=NtpConsts.VALUE, op_param_value=NtpConsts.KEY_VALUE).verify_result()
            )
        },
        'snmp_community': {
            'secret': SystemConsts.SNMP_READONLY_COMMUNITY,
            'pattern': r'readonly\-community[^:]*:\s+[\"\']*([^\"\'\s]+)',
            'set_nv_cmd': lambda: system.snmp_server.set(SystemConsts.SNMP_READONLY_COMMUNITY, IssuConsts.SNMP_READ_ONLY_COMMUNITY).verify_result()
        }
    }

    """
    Verify that sensitive information in config files is properly obscured.
    Args: content (str): The content of the config file to verify
    """
    def verify_obscurity_in_config_file(content: str, file_name: str) -> None:
        for secret_name, secret_info in config_file_secret_dict.items():
            verify_secret_obscurity(content=content, pattern=secret_info['pattern'], file_name=file_name,
                                    secret_name=secret_name, secret=secret_info['secret'])
        verify_secret_obscurity(content=content, pattern=password_pattern, file_name=file_name, secret_name='password')

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

    for secret_info in config_file_secret_dict.values():
        secret_info['set_nv_cmd']()
    NvueGeneralCli.apply_config(engine=engines.dut)
    NvueGeneralCli.save_config(engine=engines.dut)

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
            tech_support_file, duration = system.techsupport.action_generate(test_name=test_name)
            tech_support_dir = tech_support_file.replace('.tar.gz', '')
            with allure.step("Tech-support generation takes: {} seconds".format(duration)):
                logger.info("Tech-support generation takes: {} seconds".format(duration))
            system.techsupport.extract_techsupport_files(engines.dut)
            techsupport_files_dict = system.techsupport.get_techsupport_files_names(engines.dut, expected_files_dict)

        with allure.step('validate obscurity in config files'):
            nvue_dir_path = extract_nvue_show_tech(engines.dut, tech_support_dir)
            assert not verify_file_in_folder(engines.dut, 'startup.yaml', nvue_dir_path), 'startup.yaml exist in {nvue_dir_path}'
            nvued_dir_path = nvue_dir_path + '/nvue.d'

            with allure.step('validate obscurity in startup.yaml'):
                assert verify_file_in_folder(engines.dut, 'startup.yaml', nvued_dir_path), 'startup.yaml exist in {nvued_dir_path}'
                startup_content = engines.dut.run_cmd(f'cat {nvued_dir_path}/startup.yaml')
                verify_obscurity_in_config_file(content=startup_content, file_name='startup.yaml')

            with allure.step('validate obscurity in applied_configuration'):
                assert verify_file_in_folder(engines.dut, 'applied_configuration', nvue_dir_path), 'applied_configuration exist in {nvue_dir_path}'
                applied_config = engines.dut.run_cmd(f'cat {nvue_dir_path}/applied_configuration')
                verify_obscurity_in_config_file(content=applied_config, file_name='applied_configuration')

        with allure.step("validate obscurity in auth.log"):
            auth_log_path = extract_auth_log(engines.dut, tech_support_dir)
            auth_log_content = engines.dut.run_cmd(f'cat {auth_log_path}')
            verify_secret_obscurity(content=auth_log_content, pattern=login_cmd_pattern, file_name=auth_log_path,
                                    secret_name='login cmd', expected_obscurity='***', must_exist=False)

        with allure.step("validate etc/sonic/nvue.d obscurity"):
            assert not verify_file_in_folder(engines.dut, 'startup.yaml', f'{tech_support_dir}/etc/sonic/'), 'startup.yaml exist in /etc/sonic/'
            assert not verify_file_in_folder(engines.dut, 'applied_configuration', f'{tech_support_dir}/etc/sonic/'), 'applied_configuration exist in /etc/sonic/'
            assert not verify_file_in_folder(engines.dut, 'startup.yaml', f'{tech_support_dir}/etc/sonic/nvue.d'), 'startup.yaml exist in /etc/sonic/nvue.d'
            assert not verify_file_in_folder(engines.dut, 'applied_configuration', f'{tech_support_dir}/etc/sonic/nvue.d'), 'applied_configuration exist in /etc/sonic/nvue.d'

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
    if is_bug_active(36513547):
        files.remove('hdparm')
    assert len(files) == 0, "the next files are missed {files}".format(files=files)
    files = [file for file in files_list if file not in expected_files]
    if len(files) != 0:
        logger.warning("the next files are in the dump folder but not in our check list {files}".format(files=files))


def verify_techsupport_files_sizes(files_list, folder):
    if folder == 'dump':
        files_list = [file for file in files_list if file not in SystemConsts.TECHSUPPORT_DUMP_EMPTY_FILES_TO_IGNORE]
    elif folder == 'etc':
        files_list = [file for file in files_list if file not in SystemConsts.TECHSUPPORT_ETC_EMPTY_FILES_TO_IGNORE]
    elif folder == 'cluster':
        files_list = [file for file in files_list if file not in SystemConsts.TECHSUPPORT_CLUSTER_EMPTY_FILES_TO_IGNORE]

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


def extract_nvue_show_tech(engine, dump_path: str) -> str:
    engine.run_cmd(f'sudo tar -xf {dump_path}/nvue/nvue_show_tech.tar -C {dump_path}/nvue/')
    engine.run_cmd(f'sudo chmod -R 775 {dump_path}/nvue')
    return f'{dump_path}/nvue/'


def extract_auth_log(engine, dump_path: str) -> str:
    engine.run_cmd(f'sudo chmod g=rx {dump_path}/log/auth.log.gz')
    engine.run_cmd(f'sudo gunzip -k {dump_path}/log/auth.log.gz')
    return f'{dump_path}/log/auth.log'


def verify_file_in_folder(engine, file_name: str, folder_path: str) -> bool:
    return file_name in engine.run_cmd(f'ls {folder_path}')


def verify_secret_obscurity(content: str, pattern: str, file_name: str, secret_name: str, expected_obscurity: str = 'XXX',
                            secret: Optional[str] = None, must_exist: bool = True) -> None:
    match = re.search(pattern, content)
    if must_exist:
        assert match, f'{secret_name} secret not found in {file_name}'
    if match:
        if secret:
            assert match.group(1) != secret, f'{secret_name} secret is visible'
        assert match.group(1) == expected_obscurity, f'{secret_name} secret is not obscured correctly'

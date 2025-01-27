import logging
import string

import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.constants.constants import MarsConstants
from ngts.nvos_constants.constants_nvos import NvosConst, SystemConsts
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player

logger = logging.getLogger()
YAML_FILES_PATH = MarsConstants.SONIC_MGMT_DIR + "/ngts/tests_nvos/general/config_commands/yaml_files/"
YAML_FILES_LIST = ['hostname_config.yaml', 'post_login_message_config.yaml', 'pre_login_message_config.yaml']


@pytest.mark.general
@pytest.mark.simx
def test_show_fetch_file(engines):
    """
    Test flow:
        1. Run nv show system config files
        2. verify it's empty
        3. Run nv action fetch system config <remote_url>/YAML_FILES_PATH/YAML_FILES_LIST[0]
        4. Expected success message: Fetching file: <file_name> ... File fetched successfully Action succeeded
        5. Run nv show system config files
        6. Expected output: "< file_name >": {
                                                "path": /host/config_files /<file_name> "
                                              }
        7. Run nv show system config files <file_name>
        8. Expected output: set: system: hostname: <new_hostname>
    """
    system = System(None)
    files = OutputParsingTool.parse_json_str_to_dictionary(system.config.files.show()).verify_result()
    assert 1 == len(files), "The config files list should contain only one file"

    with allure.step('get remote server engine'):
        yaml_file = YAML_FILES_LIST[0]
        remote_url = generate_scp_uri_using_player(engines.sonic_mgmt, YAML_FILES_PATH + yaml_file)

    action_expected_str = "File fetched successfully"

    expected_dict = {
        "path": '/host/config_files/{}'.format(yaml_file)
    }

    with allure.step('fetch {}'.format(yaml_file)):
        system.config.action_fetch(remote_url, base_url='')

    with allure.step('verify nv show system config files command after fetch'):
        assert expected_dict == \
            OutputParsingTool.parse_json_str_to_dictionary(system.config.files.show()).verify_result()[
                yaml_file], "the dictionary should include only {}".format(yaml_file)

    with allure.step('verify nv show system config files <file_name> command after fetch'):
        output = OutputParsingTool.parse_json_str_to_dictionary(system.config.files.show(yaml_file)).verify_result()
        assert expected_dict == output[yaml_file], "the dictionary should include only {}".format(yaml_file)


@pytest.mark.general
@pytest.mark.simx
def test_export_applied_configurations(engines):
    """
    1. Run nv action export system config <file_name>.yaml
    2. Run nv set system message pre-login “TESTING”
    3. Run nv action export system config <before_apply>.yaml
    4. Run nv config apply
    5. Run nv action export system config <after_apply>.yaml
    6. compare <file_name> with <before_apply> - should be equal
    7. compare <before_apply> with <after_apply> - should not be equal
    :param engines:
    :return:
    """
    system = System(None)
    files_path = '/host/config_files/'
    action_expected_str = "Exporting completed\nAction succeeded"
    with allure.step('export {}'.format('current_conf.yaml')):
        system.config.action_export('current_conf.yaml', action_expected_str)

    with allure.step('set system pre-login message without apply'):
        system.message.set(op_param_name=SystemConsts.PRE_LOGIN_MESSAGE, op_param_value='"EXPORT TESTS"',
                           apply=False, dut_engine=engines.dut).verify_result()

    with allure.step('export {}'.format('before_apply.yaml')):
        system.config.action_export('before_apply.yaml', action_expected_str)

    with allure.step('apply message configuration'):
        NvueGeneralCli.apply_config(engines.dut)

    with allure.step('export {}'.format('after_apply.yaml')):
        system.config.action_export('after_apply.yaml', action_expected_str)

    with allure.step('verify current_conf.yaml equals to before_apply.yaml'):
        assert not engines.dut.run_cmd('diff {} {}'.format(files_path + 'current_conf.yaml',
                                                           files_path + 'before_apply.yaml')), "the two files should be equal"

    with allure.step('verify before_apply.yaml not equals to after_apply.yaml'):
        assert engines.dut.run_cmd('diff {} {}'.format(files_path + 'before_apply.yaml',
                                                       files_path + 'after_apply.yaml')), "the two files should not be equal"


@pytest.mark.general
@pytest.mark.simx
def test_rename_and_upload(engines):
    """
    1. Run nv action fetch system config <remote_url>/YAML_FILES_PATH/YAML_FILES_LIST[0]
    2. Run nv action rename system config files <file_name> <new_file_name>
    3. Expected message :
                    config file <file_name> renamed to <new_file_name>
                    Action succeeded
    4. nv action upload system config files <new_file_name> <remote_url>
    5. Action succeeded
    6. compare the file in target and the config file
    :param engines:
    :return:
    """
    system = System(None)
    with allure.step('get remote server engine'):
        remote_server_engine = engines[NvosConst.SONIC_MGMT]

    yaml_file = YAML_FILES_LIST[0]
    logger.info('the yaml file name is {}'.format(yaml_file))

    with allure.step('get the remote url'):
        remote_url = generate_scp_uri_using_player(engines.sonic_mgmt, YAML_FILES_PATH + yaml_file)

    with allure.step('fetch {}'.format(yaml_file)):
        system.config.action_fetch(remote_url, base_url='')

    with allure.step('Rename image and verify'):
        new_name = RandomizationTool.get_random_string(20, ascii_letters=string.ascii_letters + string.digits) + '.yaml'
        expected_str = "config file {} renamed to {}".format(yaml_file, new_name)
        fetched_config_file = system.config.files.file_name[yaml_file]
        fetched_config_file.rename_and_verify(new_name, expected_str)

    with allure.step('upload file'):
        upload_path = generate_scp_uri_using_player(engines.sonic_mgmt, '/tmp/')

        fetched_config_file.action_upload(upload_path)
        with allure.step("Validate file was uploaded"):
            with allure.step("file exist under upload path"):
                assert remote_server_engine.run_cmd(
                    cmd='ls /tmp/ | grep {}'.format(new_name)), "Did not find the file with ls cmd"
            remote_server_cmd = "stat -c %s /tmp/{}".format(new_name)
            dut_cmd = "stat -c %s /host/config_files/{}".format(new_name)
            with allure.step("file size is equal to the size of the original file"):
                assert engines.dut.run_cmd(dut_cmd) == remote_server_engine.run_cmd(
                    remote_server_cmd), "files are not equal, the upload is not working as expected"


@pytest.mark.general
@pytest.mark.simx
def test_patch_replace_delete(engines):
    """
    1. run nv config fetch system config files <3 yaml files>
    2. nv config replace <file1>
    3. run nv config diff and save as output_after_replace
    4. verify output_after_replace = file1
    4. run nv config patch <file2>
    5. nv config diff save as output_after_patch
    6. verify output_after_patch contains file1 + file2
    7. run nv action delete system config files <file2>
    8. run nv show system config files
    9. verify only 2 files are exist
    10. run nv action delete system config files
    11. run nv show system config files
    12. verify the show output is empty
    :param engines:
    :return:
    """
    system = System(None)

    with allure.step('delete all files'):
        delete_all = system.config.files.file_name['']
        delete_all.action_delete()

    with allure.step('fetch 3 yaml files'):
        for file in YAML_FILES_LIST:
            with allure.step('get the remote url'):
                remote_url = generate_scp_uri_using_player(engines.sonic_mgmt, YAML_FILES_PATH + file)
            with allure.step('fetch {}'.format(file)):
                system.config.action_fetch(remote_url, base_url='')

    with allure.step('run nv config replace'):
        output = TestToolkit.GeneralApi[TestToolkit.tested_api].replace_config(engines.dut, YAML_FILES_LIST[0])
        with allure.step('verify the replace command output'):
            assert "Loading config file: {} from configuration files directory.".format(
                YAML_FILES_LIST[0]) in output, "the message after replace is not as expected"

        diff_output_after_replace = NvueGeneralCli.diff_config(engines.dut)
        with allure.step('verify the diff command after replace'):
            assert "hostname" in diff_output_after_replace, ""

    with allure.step('run nv config patch'):
        output = TestToolkit.GeneralApi[TestToolkit.tested_api].patch_config(engines.dut, YAML_FILES_LIST[2])
        with allure.step('verify the replace command output'):
            assert "Loading config file: {} from configuration files directory.".format(
                YAML_FILES_LIST[2]) in output, "the message after replace is not as expected"

        diff_output_after_patch = NvueGeneralCli.diff_config(engines.dut)
        with allure.step('verify the diff command after patch'):
            assert "pre-login" in diff_output_after_patch, ""

    with allure.step('delete one of the config files'):
        file_to_delete = system.config.files.file_name[YAML_FILES_LIST[1]]
        file_to_delete.action_delete("Action succeeded")

        with allure.step('verify show command output after delete'):
            show_output = OutputParsingTool.parse_json_str_to_dictionary(system.config.files.show()).verify_result()
            assert len(
                show_output.keys()) == 2, "after deleting 1 config file out of 3 files we expect to see only two files"
            assert YAML_FILES_LIST[1] not in show_output.keys(), "deleted file still exist"

    with allure.step('delete all files'):
        delete_all = system.config.files.file_name['']
        delete_all.action_delete()

        with allure.step('verify after delete all'):
            show_output = system.config.files.show(output_format='auto')
            assert "No Data" in show_output, "after delete all at least one file still exist"
            show_output = system.config.files.show()
            assert show_output == '{}', "after delete all at least one file still exist"


@pytest.mark.general
@pytest.mark.simx
def test_config_bad_flow(engines):
    """
    1. trying to upload non exist file
    2. trying to rename non exist file
    3. trying to delete non exist file
    :param engines:
    :return:
    """
    system = System(None)
    fetched_config_file = system.config.files.file_name["NO_FILE"]

    with allure.step('trying to upload non exist file'):
        with allure.step('get remote server engine'):
            upload_path = generate_scp_uri_using_player(engines.sonic_mgmt, '/tmp/')
        fetched_config_file.action_upload(upload_path, "File not found")

    with allure.step('trying to rename non exist file'):
        fetched_config_file.action_rename("Not_file", "File not found")

    with allure.step('trying to delete non exist file'):
        fetched_config_file.action_delete("File not found")

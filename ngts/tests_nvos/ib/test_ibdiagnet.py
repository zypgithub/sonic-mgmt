import pytest
from ngts.tools.test_utils import allure_utils as allure
import json
import logging
import time
from ngts.nvos_tools.ib.Ib import Ib
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.nvos_constants.constants_nvos import IbConsts
from ngts.tests_nvos.helpers.redmine_helpers import is_bug_active

logger = logging.getLogger()


@pytest.mark.ib
def test_ibdiagnet_run(engines):
    """
    Test flow:
            1. run nv show ibdiagnet
            2. verify file not exist message
            3. run cd /host/ibdiagnet/ibdiagnet2
            4. verify "no such file or directory" message
            5. nv action run ib cmd ”ibdiagnet --get_phy_info“
            6. verify the  "message about action success"
            7. nv show ib ibdiagnet
            8. Verify it’s not empty and check file size (use splitlines and constant min_lines)
            9. run ls /host/ibdiagnet
            11. Check if ibdiagnet_output.tgz exist
            12. verify all expected files in ibdiagnet_output.tgz
            13. run nv action reboot system
            14. run ls /host/ibdiagnet
            15. Check if ibdiagnet_output.tgz still exist
            15. run nv action delete ib ibdiagnet ibdiagnet_output.tgz
    :param engines:
    :return:
    """
    ib = Ib(None)
    with allure.step('Validate ibdiagnet files does not exist by default'):
        assert '{}' == ib.ibdiagnet.show(), "ibdiagnet dump files should be deleted"

    with allure.step('Validate ibdiagnet directory does not exist'):
        output = engines.dut.run_cmd('ls {path}'.format(path=IbConsts.IBDIAGNET_ZIPPED_FOLDER_PATH))
        error_message = "No such file or directory"
        assert error_message in output, "ibdiagnet temp directory should be deleted"

    ib.ibdiagnet.action_run(command=IbConsts.IBDIAGNET_COMMAND, option=IbConsts.IBDIAGNET_PHY_INFO, expected_str=IbConsts.IBDIAGNET_EXPECTED_MESSAGE)

    with allure.step('Make sure the files are created under the right expected path'):
        with allure.step('validate the ibdiagnet path'):
            output = engines.dut.run_cmd('ls {path}'.format(path=IbConsts.IBDIAGNET_ZIPPED_FOLDER_PATH))
            assert IbConsts.IBDIAGNET_FILE_NAME in output.split(), "the ibdiagnet file is missing"

        with allure.step('verify all expected files in ibdiagnet_output.tgz'):
            ValidationTool.verify_all_files_in_compressed_folder(engines.dut, IbConsts.IBDIAGNET_FILE_NAME, IbConsts.IBDIAGNET_EXPECTED_FILES_LIST, IbConsts.IBDIAGNET_ZIPPED_FOLDER_PATH, IbConsts.IBDIAGNET_PATH).verify_result()

    with allure.step('Make sure all ibdiagnet files still available after reboot'):
        system = System(None)
        system.reboot.action_reboot()
        with allure.step('check the {} still exist'.format(IbConsts.IBDIAGNET_FILE_NAME)):
            output = engines.dut.run_cmd('ls {path}'.format(path=IbConsts.IBDIAGNET_ZIPPED_FOLDER_PATH))
            assert IbConsts.IBDIAGNET_FILE_NAME in output.split(), "the ibdiagnet file is missing"

    with allure.step('Delete the ibdiagnet file'):
        ib.ibdiagnet.action_delete(file_name=IbConsts.IBDIAGNET_FILE_NAME)


@pytest.mark.ib
def test_ibdiagnet_run_multiple_times(engines):
    """
    Validate only one ibdiagnet file will be exist after generating it many times
    :param engines:
    :return:
    """
    ib = Ib(None)
    tries_number = 5
    if is_bug_active(3482696):
        time.sleep(40)

    with allure.step('try to generate ibdiagnet file {tries} times'.format(tries=tries_number)):
        for i in range(0, tries_number):
            ib.ibdiagnet.action_run(command=IbConsts.IBDIAGNET_COMMAND, option=IbConsts.IBDIAGNET_PHY_INFO, expected_str=IbConsts.IBDIAGNET_EXPECTED_MESSAGE)

    with allure.step('Validate only one ibdiagnet file will be exist after generating it {tries} times'.format(tries=tries_number)):
        output = engines.dut.run_cmd('ls {path}'.format(path=IbConsts.IBDIAGNET_ZIPPED_FOLDER_PATH))
        assert len(output.split()) == 2, "more than ibdiagnet files are exist"

    ib.ibdiagnet.action_delete(file_name=IbConsts.IBDIAGNET_FILE_NAME)


@pytest.mark.ib
def test_ibdiagnet_negative(engines):
    """
    Will validate the two invalid cases to run the ibdiagnet generating command "nv action run ib cmd"
    case1: using string != ibdiagnet
    case2: using invalid option, for now the valid options = [get_phy_info, get_ cable_info]
    Test flow:
            1. generate invalid command
            2. run nv action run ib cmd <invalid_cmd>
            3. verify error message
            4. generate <invalid_opt>
            5. run nv action run ib cmd "ibdiagnet --<invalid_opt>"
            6. verify error message
    :param engines:
    :return:
    """
    ib = Ib(None)
    invalid_cmd = "ibdiagnetfile"
    invalid_opt = "--ibdiagnetfile"
    invalid_cmd_error_message = "Failed to run ib command: unsupported command " + invalid_cmd
    opt_error_message = "Failed to run ibdiagnet command: invalid command ["
    with allure.step('try to generate ibdiagnet using invalid commands'):

        with allure.step('try to use ibdiagnet generating command with invalid string {invalid_cmd} and verify error message'.format(invalid_cmd=invalid_cmd)):
            ib.ibdiagnet.action_run(command=invalid_cmd, expected_str=invalid_cmd_error_message)

        with allure.step('try to use ibdiagnet generating command with invalid option {invalid_opt} and verify error message'.format(
                invalid_opt=invalid_opt)):
            ib.ibdiagnet.action_run(command=IbConsts.IBDIAGNET_COMMAND, option=invalid_opt, expected_str=opt_error_message)


@pytest.mark.ib
def test_ibdiagnet_upload(engines):
    """
    Test flow:
        1. upload non exist ibdiagnet file
        2. verify the error message
        3. generate ibdiagnet
        4. upload to valid_url
        5. verify the success message
        6. check the size of tgz in target path
        7. run nv show ib ibdiagnet and verify the log file len
        8. invalid_url_1 : using invalid format nv action upload ib ibdiagnet ibdiagnet_output.tgz <invalid_url1>
        9. invalid_url_2 : using invalid opt nv action upload ib ibdiagnet ibdiagnet_output.tgz <invalid_url2>
        10. run nv action upload ib ibdiagnet with invalid1 and verify error message
        11. run nv action upload ib ibdiagnet with invalid1 and verify error message
    :param engines:
    :return:
    """
    ib = Ib(None)
    expected_msg_upload = "File upload successfully"
    player = engines['sonic_mgmt']
    invalid_url_1 = 'scp://{}:{}{}/tmp/'.format(player.username, player.password, player.ip)
    invalid_url_2 = 'ffff://{}:{}@{}/tmp/'.format(player.username, player.password, player.ip)
    upload_path = 'scp://{}:{}@{}/tmp/'.format(player.username, player.password, player.ip)
    with allure.step('pre cleanup: delete ibdiagnet file if it exists'):
        try:
            ib.ibdiagnet.action_delete(file_name=IbConsts.IBDIAGNET_FILE_NAME).verify_result()
        except AssertionError as e:
            if 'File not found' in str(e):
                pass
            else:
                raise

    with allure.step('try to upload non exist ibdiagnet file'):
        output = ib.ibdiagnet.action_upload(upload_path=upload_path).verify_result(
            False, f"File not found: {IbConsts.IBDIAGNET_FILE_NAME}")
        ib.ibdiagnet.action_run(command=IbConsts.IBDIAGNET_COMMAND, option=IbConsts.IBDIAGNET_PHY_INFO,
                                expected_str=IbConsts.IBDIAGNET_EXPECTED_MESSAGE)

    with allure.step('try to upload ibdiagnet to - Positive Flow'):
        output = ib.ibdiagnet.action_upload(upload_path=upload_path).verify_result(True, expected_msg_upload)

        with allure.step('verify files still exist'):
            ValidationTool.verify_all_files_in_compressed_folder(engines.dut, IbConsts.IBDIAGNET_FILE_NAME, IbConsts.IBDIAGNET_EXPECTED_FILES_LIST, IbConsts.IBDIAGNET_ZIPPED_FOLDER_PATH, IbConsts.IBDIAGNET_PATH).verify_result()

        with allure.step('verify files in the target directory'):
            ValidationTool.verify_all_files_in_compressed_folder(player, IbConsts.IBDIAGNET_FILE_NAME, IbConsts.IBDIAGNET_EXPECTED_FILES_LIST, '/tmp', IbConsts.IBDIAGNET_PATH).verify_result()

    with allure.step('try to upload ibdiagnet to invalid url - url is not in the right format'):
        output = ib.ibdiagnet.action_upload(upload_path=invalid_url_1).verify_result(False, 'is not a')

    with allure.step('try to upload ibdiagnet to invalid url - using non supported transfer protocol'):
        output = ib.ibdiagnet.action_upload(upload_path=invalid_url_2).verify_result(False, 'is not a')


@pytest.mark.ib
def test_ibdiagnet_delete(engines):
    """
    Test flow:
            1. run nv action run ib cmd ”ibdiagnet --get_cable_info“
            2. verify “message about action success” message
            3. try to delete with invalid file name
            4. verify error message and files still exist
            5. run nv action delete ib ibdiagnet ibdiagnet_output.tgz
            6. nv show ib ibdiagnet
            7. verify file not exists
            8. run cd /var/tmp/ibdiagnet2
            9. verify “no such file or directory”  message
            9. try to delete non exist ibdiagnet files
            10. verify error message
    :param engines:
    :return:
    """
    ib = Ib(None)
    ib.ibdiagnet.action_run(command=IbConsts.IBDIAGNET_COMMAND, option='--get_cable_info', expected_str=IbConsts.IBDIAGNET_EXPECTED_MESSAGE)

    with allure.step('Try to delete with invalid file name'):
        invalid_file = 'ibdiagnetfile'
        output = ib.ibdiagnet.action_delete(file_name=invalid_file)
        assert "File not found: {}".format(invalid_file) in output.get_info(False), (
            "ibdiagnet name should be {file_name}".format(file_name=IbConsts.IBDIAGNET_FILE_NAME))

    with allure.step('Validate we can delete ibdiagnet files'):
        output = ib.ibdiagnet.action_delete(file_name=IbConsts.IBDIAGNET_FILE_NAME)
        assert 'File delete successfully' in output.returned_value, "ibdiagnet delete action failed"

        with allure.step('verify ibdiagnet file does not exist using show command'):
            paths_keys = json.loads(ib.ibdiagnet.show())['files'].keys()
            assert 'ibdiagnet2.log' in paths_keys and len(list(paths_keys)) == 1, "the ibdiagnet file should not be deleted"

        with allure.step('Validate ibdiagnet directory does not exist anymore'):
            output = engines.dut.run_cmd('ls {path}'.format(path=IbConsts.IBDIAGNET_ZIPPED_FOLDER_PATH))
            assert len(output.split()) == 1, "more than ibdiagnet files are exist"

    with allure.step('Try to delete non exist ibdiagnet file'):
        output = ib.ibdiagnet.action_delete(file_name=IbConsts.IBDIAGNET_FILE_NAME)
        assert "File not found: {}".format(IbConsts.IBDIAGNET_FILE_NAME) in output.get_info(False), (
            "can not delete non exist ibdiagnet file".format(file_name=IbConsts.IBDIAGNET_FILE_NAME))

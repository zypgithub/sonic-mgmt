import datetime

import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import SystemConsts
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.system
@pytest.mark.tech_support
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_techsupport_show(engines, test_name, test_api, devices):
    """
    Run nv show system tech-support files command and verify the required fields are exist
    command: nv show system tech-support files

    Test flow:
        1. run nv show system tech-support files
        2. run nv action generate system tech-support
        3. run nv action generate system tech-support
        4. validate new tar.gz files exist and first output < second output
        5. run nv show system tech-support files
        6. validate the output format
    """
    system = System(None)
    operation = devices.dut.generate_tech_support
    TestToolkit.tested_api = test_api
    duration = 0
    with allure.step('Run show/action system tech-support and verify that each results updated as expected'):
        output_dictionary_before_actions = list(Tools.OutputParsingTool.parse_show_files_to_dict(
            system.techsupport.show()).get_returned_value().values())
        folder, duration = system.techsupport.action_generate(test_name=test_name)

        OperationTime.verify_operation_time(duration, operation).verify_result()
        file1 = system.techsupport.file_name
        folder, duration = system.techsupport.action_generate()
        OperationTime.verify_operation_time(duration, operation).verify_result()
        file2 = system.techsupport.file_name
        output_dictionary_after_actions = list(Tools.OutputParsingTool.parse_show_files_to_dict(
            system.techsupport.show()).get_returned_value().values())
        validate_techsupport_output(output_dictionary_before_actions, output_dictionary_after_actions, 2)

    with allure.step('Validate show tech-support command format'):
        show_output = system.techsupport.show()
        output_dict = Tools.OutputParsingTool.parse_json_str_to_dictionary(show_output).get_returned_value()
        assert SystemConsts.LATEST_KEY in output_dict, \
            f"Output of show tech-support is missing key '{SystemConsts.LATEST_KEY}'. Existing keys: {output_dict.keys()}"
        latest_file = output_dict.pop(SystemConsts.LATEST_KEY)[SystemConsts.PATH_KEY]
        output_dict = {key: value[SystemConsts.PATH_KEY] for key, value in output_dict.items()}
        assert latest_file == max(*output_dict.values()), (
            f"Output of show tech-support contains a file marked 'latest', but that file either doesn't exist or is not"
            f" really the latest file. File is {latest_file}."
        )
        assert list(output_dict.keys()) == [full_path.replace(SystemConsts.TECHSUPPORT_FILES_PATH, '')
                                            for full_path in output_dict.values()], \
            f"Output of show tech-support has mismatch between keys (file names) and full-paths: {output_dict.items()}"

    system.techsupport.action_delete(file1)
    system.techsupport.action_delete(file2)


@pytest.mark.system
@pytest.mark.tech_support
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_techsupport_since(engines, test_name, test_api):
    """
    Run nv show system tech-support files command and verify the required fields are exist
    command: nv show system tech-support files

    Test flow:
        1. run nv action generate system tech-support since <today_time>
        2. run nv show system tech-support files
        3. validate new tar.gz file exist
    """
    system = System(None)
    operation = devices.dut.generate_tech_support
    TestToolkit.tested_api = test_api
    with allure.step('Run show/action system tech-support and verify that each results updated as expected'):
        yesterday = datetime.datetime.today() - datetime.timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y%m%d")
        tech_support_folder, duration = system.techsupport.action_generate(engines.dut, SystemConsts.ACTIONS_GENERATE_SINCE,
                                                                           yesterday_str, test_name=test_name)
        output_dictionary = list(Tools.OutputParsingTool.parse_show_files_to_dict(
            system.techsupport.show()).get_returned_value().values())
        validate_techsupport_since(output_dictionary, tech_support_folder)
        OperationTime.verify_operation_time(duration, operation).verify_result()
        system.techsupport.action_delete(system.techsupport.file_name)


@pytest.mark.system
@pytest.mark.tech_support
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_techsupport_since_invalid_date(engines, test_api):
    """
    Run nv show system tech-support files command and verify the required fields are exist
    command: nv show system tech-support files

    Test flow:
        1. run nv action generate system tech-support since <syntax_error>
        2. validate Invalid date in the output
    """
    system = System(None)
    TestToolkit.tested_api = test_api
    invalid_date_syntax = '20206610'
    with allure.step('Validating the generate command failed because '
                     'of Invalid date {invalid_date_syntax}'.format(invalid_date_syntax=invalid_date_syntax)):
        output_dictionary, duration = system.techsupport.action_generate(option=SystemConsts.ACTIONS_GENERATE_SINCE,
                                                                         since_time=invalid_date_syntax)
        assert 'Command failed with the following output' in output_dictionary, ""

    invalid_date_syntax = 'aabbccdd'
    with allure.step('Validating the generate command failed because '
                     'of Invalid date {invalid_date_syntax}'.format(invalid_date_syntax=invalid_date_syntax)):
        output_dictionary, duration = system.techsupport.action_generate(option=SystemConsts.ACTIONS_GENERATE_SINCE,
                                                                         since_time=invalid_date_syntax)
        assert 'Command failed with the following output' in output_dictionary, ""


@pytest.mark.system
@pytest.mark.tech_support
def test_techsupport_delete(engines):
    """
    Run nv show system tech-support files command and verify the required fields are exist
    command: nv show system tech-support files

    Test flow:
        1. run nv action generate system tech-support save as <first_file>
        2. run nv action generate system tech-support save as <second_file>
        3. run nv action delete system techsupport file <first_file>
        4. verify "File delete successfully" message
        5. run nv show system techsupport files
        6. verify <second_file> still exist and <first_file> has been deleted
        7. run nv action delete system techsupport file <first_file>
        8. File not found: <first_file>
    """
    system = System(None)
    success_message = 'File delete successfully'
    with allure.step('Run action delete system tech-support and verify that each results updated as expected'):

        with allure.step('Generate two tech-support files'):
            first_file, duration = system.techsupport.action_generate()
            system.techsupport.show()
            second_file, duration = system.techsupport.action_generate()
            system.techsupport.show()

        with allure.step('Delete the first created tech-support file'):
            output = system.techsupport.action_delete(first_file.replace('/host/dump/', '')).get_returned_value()

        assert success_message in output, 'failed to delete'
        output_dictionary_after_delete = list(Tools.OutputParsingTool.parse_show_files_to_dict(
            system.techsupport.show()).get_returned_value().values())

        with allure.step('Check {} has been deleted and {} still exist'.format(first_file, second_file)):
            assert first_file not in output_dictionary_after_delete, "{} still exist even after deleting it".format(first_file)
            assert second_file in output_dictionary_after_delete, "{} does not exist".format(second_file)

        with allure.step('Delete non exist tech-support file {}'.format(first_file)):
            res_obj = system.techsupport.action_delete(first_file.replace('/host/dump/', ''))
            res_obj.verify_result(should_succeed=False)
            assert 'Action failed with the following issue:' in res_obj.info, "Can not delete non exist file!"


@pytest.mark.system
@pytest.mark.tech_support
def test_techsupport_upload(engines):
    """
    Test flow:
        1. upload non exist tech-support file
        2. verify the error message
        3. generate tech-support file save as tech_file
        4. upload to valid_url
        5. verify the success message
        6. check the size of tgz in target path
        7. invalid_url_1 : using invalid format nv action upload system techsupport files <tech_file> <invalid_url1>
        8. invalid_url_2 : using invalid opt nv action upload system techsupport files <tech_file> <invalid_url2>
        9. run nv action upload system techsupport files  <tech_file> <invalid_url1> and verify error message
        10. run nv action upload system techsupport files  <tech_file> <invalid_url2> and verify error message
    :param engines:
    :return:
    """
    system = System(None)
    with allure.step('generate valid and invalid urls'):
        player = engines['sonic_mgmt']
        invalid_url_1 = 'scp://{}:{}{}/tmp/'.format(player.username, player.password, player.ip)
        invalid_url_2 = 'ffff://{}:{}@{}/tmp/'.format(player.username, player.password, player.ip)
        upload_path = 'scp://{}:{}@{}/tmp/'.format(player.username, player.password, player.ip)

    with allure.step('Try to upload non exist tech-support file'):
        output = system.techsupport.action_upload(file_name='nonexist', upload_path=upload_path)
        assert "File not found: nonexist" in output.info, "we can not upload a non exist file!"

    with allure.step('Generate tech-support file'):
        tech_file, duration = system.techsupport.action_generate()
        tech_file = tech_file.replace('/host/dump/', '')

    with allure.step('try to upload techsupport {} to {} - Positive Flow'.format(tech_file, upload_path)):
        output = system.techsupport.action_upload(upload_path, tech_file).verify_result()
        with allure.step('verify the upload message'):
            assert "File upload successfully" in output, "Failed to upload the techsupport file"

        with allure.step('verify the uploaded file exist in target path'):
            output = player.run_cmd('ls /tmp/')
            assert tech_file in output

    with allure.step('try to upload techsupport to invalid url - url is not in the right format'):
        output = system.techsupport.action_upload(file_name='nonexist', upload_path=invalid_url_1)
        assert "is not a" in output.info, "URL was not in the right format"

    with allure.step('try to upload ibdiagnet to invalid url - using non supported transfer protocol'):
        output = system.techsupport.action_upload(file_name='nonexist', upload_path=invalid_url_2)
        assert "is not a" in output.info, "URL used non supported transfer protocol"

    system.techsupport.action_delete(system.techsupport.file_name)


@pytest.mark.system
@pytest.mark.tech_support
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_techsupport_multiple_times(engines, test_name, test_api):
    """
    Run nv show system tech-support files command and verify the required fields are exist
    command: nv show system tech-support files

    Test flow:
        1. run nv action generate system tech-support 4 times in a row
    """
    system = System(None)
    operation = devices.dut.generate_tech_support
    TestToolkit.tested_api = test_api
    files_names = []
    with allure.step('Run show/action system tech-support 4 times in a row'):
        for i in range(0, 4):
            with allure.step("Generate Tech-Support for the {} time".format(i)):
                folder, duration = system.techsupport.action_generate(test_name=test_name)
                OperationTime.verify_operation_time(duration, operation).verify_result()
                files_names.append(system.techsupport.file_name)

    for file_name in files_names:
        system.techsupport.action_delete(file_name)


@pytest.mark.system
@pytest.mark.tech_support
def test_techsupport_size(engines, test_name):
    """
    Run nv action generate system tech-support and verify output file size
    command: nv action generate system tech-support

    Test flow:
        1. run nv action generate system tech-support
        2. check file size by du -sm
        3. assert if size > 50 MB
    """
    engine = engines.dut
    system = System(None)
    with allure.step('Run generate tech-support'):
        tech_support_folder, duration = system.techsupport.action_generate()
        # Round output to MB by -m flag and trim white spaces with column to receive int like output
        output = engine.run_cmd(f"sudo du -sm {tech_support_folder} | column -t")
        size_in_MB = int(output.split(" ")[0])
        assert size_in_MB < 50, f"{tech_support_folder} size ({size_in_MB}MB) should be less than 50MB"

        system.techsupport.action_delete(system.techsupport.file_name)


def validate_techsupport_output(output_dictionary_before, output_dictionary_after, number_of_expected_files):
    """
    Asserts that our actions caused the correct number of files to be created.
    :param output_dictionary_before: Output of the `nv show tech-support` command.
    :param output_dictionary_after: Output of the same command after some actions were taken.
    :param number_of_expected_files: The number of dump files that we expect to be created after the actions.
    """
    with allure.step('Validating the generate command and show command working as expected'):
        assert len(set(output_dictionary_after) - set(output_dictionary_before)) == number_of_expected_files, \
            "at least one of the new tech-support folders not found"


def validate_techsupport_since(output_dictionary, substring):
    with allure.step('Validating the generate command and show command working as expected'):
        assert substring in output_dictionary, \
            "at least one of the new tech-support folders not found, expected folders"

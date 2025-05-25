import pytest

from ngts.nvos_constants.constants_nvos import ApiType, ImageConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.FilesTool import FilesTool, EngineFile
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='session', autouse=True)
def clear_debug_info_files():
    fae = Fae(None)
    debug_image = fae.platform.debug.info.debug_image
    with allure.step('delete fetched firmware image files'):
        files = debug_image.files.get_files()
        debug_image.files.delete_files(files_to_delete=files).verify_result()


@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_debug_token_upload_good_flow(engines, test_name, test_api):
    """
    Test the successful upload of a debug token file.

    Steps:
    1. Set the tested API.
    2. Initialize the Fae and DebugImage objects.
    3. Generate a valid URL for file upload.
    4. Generate and verify the debug token file.
    5. Upload the debug token file and verify the upload message.
    6. Validate the file upload on the server and delete it.
    7. Delete the debug token file from the system.
    8. Verify that no debug token files remain.
    """
    TestToolkit.tested_api = test_api
    fae = Fae(None)
    debug_image = fae.platform.debug.info.debug_image
    with allure.step('generate valid url'):
        player = engines['sonic_mgmt']
        upload_path = ImageConsts.SCP_PATH_SERVER.format(username=player.username, password=player.password, ip=player.ip, path='/tmp/')

    filename = generate_and_verify_debug_token(debug_image, test_name)
    path = f"/etc/platform_debug/info/debug_image/{filename}"
    engine_file = EngineFile(engines.dut, path)
    file_size = FilesTool.get_file_size_in_bytes(engines.dut, path)
    assert file_size > 10000, f"debug token file is missing data\n{engine_file.get_content()}"

    with allure.step('try to upload debug info {} to {} - Positive Flow'.format(filename, upload_path)):
        fae.platform.debug.info.debug_image.files.file_name[filename].action_upload(upload_path=upload_path
                                                                                    ).verify_result()

        with allure.step("Validate file was uploaded to player and delete it"):
            assert player.run_cmd(cmd='ls /tmp/ | grep {}'.format(filename)), "Did not find the file with ls cmd"
            player.run_cmd(cmd='rm -f /tmp/{}'.format(filename))

    with allure.step(f'try to delete debug info {filename}'):
        debug_image.files.file_name[filename].action_delete().verify_result()
        debug_image.files.verify_show_files_output()


@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_debug_token_upload_bad_flow(engines, test_name, test_api):
    """
    Test the unsuccessful upload of a debug token file with invalid URLs and non-existent files.

    Steps:
    1. Set the tested API.
    2. Initialize the Fae and DebugImage objects.
    3. Generate valid and invalid URLs for file upload.
    4. Attempt to upload a non-existent debug token file and expect failure.
    5. Generate and verify the debug token file.
    6. Attempt to upload the debug token file to an invalid URL format and expect failure.
    7. Attempt to upload the debug token file using an unsupported transfer protocol and expect failure.
    8. Delete the debug token file from the system.
    9. Verify that no debug token files remain.
    """
    TestToolkit.tested_api = test_api
    fae = Fae(None)
    debug_image = fae.platform.debug.info.debug_image
    with allure.step('generate valid and invalid urls'):
        player = engines['sonic_mgmt']
        invalid_url_1 = 'scp://{}:{}{}/tmp/'.format(player.username, player.password, player.ip)
        invalid_url_2 = 'ffff://{}:{}@{}/tmp/'.format(player.username, player.password, player.ip)
        upload_path = ImageConsts.SCP_PATH_SERVER.format(username=player.username, password=player.password, ip=player.ip, path='/tmp/')

    with allure.step('Try to upload non exist debug info file'):
        fae.platform.debug.info.debug_image.files.file_name['nonexist'].action_upload(upload_path=upload_path
                                                                                      ).verify_result(should_succeed=False)
    filename = generate_and_verify_debug_token(debug_image, test_name)

    with allure.step('try to upload debug info to invalid url - url is not in the right format'):
        fae.platform.debug.info.debug_image.files.file_name['nonexist'].action_upload(
            upload_path=invalid_url_1).verify_result(should_succeed=False, expected_value="is not a")

    with allure.step('try to upload debug info to invalid url - using non supported transfer protocol'):
        fae.platform.debug.info.debug_image.files.file_name['nonexist'].action_upload(
            upload_path=invalid_url_2).verify_result(should_succeed=False, expected_value="is not a")

    with allure.step(f'try to delete debug info {filename}'):
        debug_image.files.file_name[filename].action_delete().verify_result()
        debug_image.files.verify_show_files_output()


@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_debug_info_generate_mulitple(engines, test_name, test_api):
    """
    Test generating multiple debug info files sequentially.

    Steps:
    1. Set the tested API.
    2. Initialize the Fae and DebugImage objects.
    3. Generate debug info files three times in a row.
    4. Verify the presence of each generated file.
    5. Delete all generated debug info files.
    6. Verify that no debug info files remain.
    """
    TestToolkit.tested_api = test_api
    fae = Fae(None)
    debug_image = fae.platform.debug.info.debug_image

    files_names = []
    with allure.step('Run show/action debug-image 3 times in a row'):
        for i in range(1, 4):
            with allure.step(f"Generate debug image for the {i} time"):
                filename = RandomizationTool.get_random_string(8) + '.bin'
                files_names.append(filename)
                debug_image.action_generate(name=filename, test_name=test_name)
                debug_image.files.verify_show_files_output(expected_files=files_names)

    with allure.step(f'try to all delete debug info files'):
        debug_image.action_delete_all()
        debug_image.files.verify_show_files_output()


@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_debug_info_rename_good_flow(engines, test_name, test_api):
    """
    Test renaming a debug info file successfully.

    Steps:
    1. Set the tested API.
    2. Initialize the Fae and DebugImage objects.
    3. Generate and verify the debug token file.
    4. Rename the debug token file to a new name.
    5. Verify the presence of the renamed file and absence of the old file.
    6. Delete the renamed debug token file.
    7. Verify that no debug token files remain.
    """
    TestToolkit.tested_api = test_api
    fae = Fae(None)
    debug_image = fae.platform.debug.info.debug_image
    filename = generate_and_verify_debug_token(debug_image, test_name)
    new_filename = RandomizationTool.get_random_string(9) + '.bin'

    with allure.step('try to rename debug info {} to {} - Positive Flow'.format(filename, new_filename)):
        fae.platform.debug.info.debug_image.files.file_name[filename].action_rename(
            new_name=new_filename).verify_result()

    with allure.step('verify the renamed file exist in target path'):
        debug_image.files.verify_show_files_output(expected_files=[new_filename], unexpected_files=[filename])

    with allure.step(f'try to delete debug info {new_filename}'):
        debug_image.files.file_name[new_filename].action_delete().verify_result()
        debug_image.files.verify_show_files_output()


@pytest.mark.fae
@pytest.mark.debug_token
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_debug_info_rename_bad_flow(engines, test_name, test_api):
    """
    Test renaming a debug info file unsuccessfully with invalid names and non-existent files.

    Steps:
    1. Set the tested API.
    2. Initialize the Fae and DebugImage objects.
    3. Attempt to rename a non-existent debug token file and expect failure.
    4. Attempt to generate a debug token file with an invalid name and expect failure.
    5. Generate and verify the debug token file.
    6. Rename the debug token file to a new name.
    7. Attempt to delete the renamed file.
    8. Attempt to delete the old non-existing file and expect failure.
    9. Attempt to delete the renamed file again and expect failure.
    10. Verify that no debug token files remain.
    """
    TestToolkit.tested_api = test_api
    fae = Fae(None)
    debug_image = fae.platform.debug.info.debug_image

    with allure.step('Try to rename non exist debug info file'):
        fae.platform.debug.info.debug_image.files.file_name['non_exist'].action_rename(
            new_name='new_name').verify_result(False, expected_value='not in a bin format')

    with allure.step('Try to generate debug info file with invalid name not_with_bin'):
        debug_image.action_generate(name='not_with_bin', test_name=test_name, should_succeed=False)
        debug_image.files.verify_show_files_output()

    filename = generate_and_verify_debug_token(debug_image, test_name)
    new_filename = RandomizationTool.get_random_string(9) + '.bin'

    with allure.step('try to rename debug info {} to {}'.format(filename, new_filename)):
        fae.platform.debug.info.debug_image.files.file_name[filename].action_rename(
            new_name=new_filename).verify_result()

    with allure.step(f'delete the renamed file {new_filename}'):
        debug_image.files.file_name[new_filename].action_delete().verify_result()

    with allure.step(f'bad flow - delete the old non-existing file {filename} - expected fail'):
        debug_image.files.file_name[filename].action_delete.verify_result(should_succeed=False)

    with allure.step(f'bad flow - delete the renamed file {new_filename} - expected fail'):
        debug_image.files.file_name[new_filename].action_delete.verify_result(should_succeed=False)

    debug_image.files.verify_show_files_output()


def generate_and_verify_debug_token(debug_image, test_name):
    with allure.step('Generate debug info file'):
        filename = RandomizationTool.get_random_string(8) + '.bin'
        debug_image.action_generate(name=filename, test_name=test_name)
        debug_image.files.verify_show_files_output(expected_files=[filename])
        return filename

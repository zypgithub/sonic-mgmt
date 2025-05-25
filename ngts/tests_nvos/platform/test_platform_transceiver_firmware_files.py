import logging
import pytest
import string

from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_constants.constants_nvos import ApiType, SystemConsts
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool

logger = logging.getLogger()


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_transceiver_files_actions_positive(engines, test_api):
    """
    The test will check the positive flow of fetching and deleting transceiver firmware.

    flow:
    0. Run nv show platform transceiver firmware files and verify no files exist
    1. Generate new URLs save as <remote-URL1>, <remote-URL2>
    2. Run nv action fetch platform firmware transceiver <remote-URL1>
    3. Run nv action fetch platform firmware transceiver <remote-URL2>
    4. Run nv show platform transceiver firmware files save output as <show_output_second_fetch>
    5. Verify all expected values in <show_output_second_fetch>
    6. Run nv action rename platform firmware transceiver files <file_name_1> <new_file_name>
    7. Run nv show platform transceiver firmware files save output as <show_output_after_rename>
    8. Verify all expected values in <show_output_after_rename> - Only the name of the first file has been changed
    9. Run nv action upload platform firmware transceiver files <file-name> <remote-url>
    10. Validate file was uploaded to player and delete it
    11. Run nv action delete platform firmware transceiver files <file_name>
    12. Run nv show platform transceiver firmware files save output as <show_output_after_delete>
    13. Verify all expected values in <show_output_after_delete>
    """
    new_fw_file1 = "sec_issu_46_120_10011_dev_signed.bin"
    new_fw_file2 = "sec_issu_46_120_10010_dev_signed.bin"
    upload_protocols = ['scp', 'sftp']
    fw_path_1 = f"{SystemConsts.GENERAL_TRANSCEIVER_FIRMWARE_FILES}/{new_fw_file1}"
    fw_path_2 = f"{SystemConsts.GENERAL_TRANSCEIVER_FIRMWARE_FILES}/{new_fw_file2}"

    with allure.step("Create platform object"):
        platform = Platform()

    try:
        with allure.step("fetch firmware transceiver files {} and {} to switch".format(new_fw_file1, new_fw_file2)):
            player_engine = engines['sonic_mgmt']
            scp_path = 'scp://{}:{}@{}'.format(player_engine.username, player_engine.password, player_engine.ip)
            platform.firmware.transceiver.action_fetch(fw_path_1, base_url=scp_path).verify_result()
            platform.firmware.transceiver.action_fetch(fw_path_2, base_url=scp_path).verify_result()

        with allure.step("Run the show command and verify that all expected files are correct"):
            platform.firmware.transceiver.files.verify_show_files_output(expected_files=[new_fw_file1, new_fw_file2])

        with allure.step("Rename firmware transceiver file and verify"):
            renamed_file = platform.firmware.transceiver.files.file_name[new_fw_file1]
            new_fw_file_name = RandomizationTool.get_random_string(20, ascii_letters=string.ascii_letters + string.digits) + '.bin'
            renamed_file.rename_and_verify(new_fw_file_name)

            with allure.step("Run the show command and verify that all expected files are correct"):
                platform.firmware.transceiver.files.verify_show_files_output(expected_files=[new_fw_file_name, new_fw_file2],
                                                                             unexpected_files=[new_fw_file1])

            with allure.step("Run the show command and verify that all expected files are correct"):
                renamed_file.rename_and_verify(new_fw_file1)

        with allure.step("Upload firmware transceiver to player {} with the next protocols : {}".format(
                player_engine.ip, upload_protocols)):
            for protocol in upload_protocols:
                with allure.step("Upload firmware transceiver to player with {} protocol".format(protocol)):
                    upload_path = '{}://{}:{}@{}/tmp/{}'.format(protocol, player_engine.username,
                                                                player_engine.password,
                                                                player_engine.ip, new_fw_file1)
                    renamed_file.action_upload(upload_path).verify_result(True, 'File upload successfully')

                with allure.step("Validate file was uploaded to player and delete it"):
                    assert player_engine.run_cmd(
                        cmd='ls /tmp/ | grep {}'.format(new_fw_file1)), "Did not find the file with ls cmd"
                    player_engine.run_cmd(cmd='rm -f /tmp/{}'.format(new_fw_file1))

        with allure.step("delete one of firmware transceiver files - {}".format(new_fw_file2)):
            file_to_delete = platform.firmware.transceiver.files.file_name[new_fw_file2]
            file_to_delete.action_delete().verify_result()

        with allure.step("Run the show command and verify that all expected files are correct"):
            platform.firmware.transceiver.files.verify_show_files_output(expected_files=[new_fw_file1],
                                                                         unexpected_files=[new_fw_file2])
    finally:
        with allure.step("Delete all files"):
            engines.dut.run_cmd(f"sudo rm -f /host/fw-images/module/*")


@pytest.mark.platform
@pytest.mark.transceiver
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_transceiver_files_negative(engines, test_api):
    """
    The test will check the negative flow of fetching, deleting, renaming and uploading transceiver firmware.

    flow:
    0. Generate URL save as <remote-URL1>
    1. Generate invalid URLs save as <Invalid_remote-URL1>, <Invalid_remote-URL2>, <Invalid_remote-URL3>
    2. Generate invalid file_name save as <Invalid_file_name>
    3. Run nv action fetch platform transceiver firmware <Invalid_remote-URL1> save err message as <error_message1>
    4. Run nv action fetch platform transceiver firmware <Invalid_remote-URL2> save err message as <error_message2>
    6. Run nv action delete platform transceiver firmware files <non_exist_file> save err message as <error_message3>
    7. Run nv action fetch platform transceiver firmware <remote-URL1>
    8. Run nv action rename platform transceiver firmware files <file_name> <Invalid_file_name> save err message as <error_message4>
    9. Run nv action upload platform firmware transceiver files <file-name> <Invalid_remote-URL1> save err message as <error_message5>
    10. Validate file was not uploaded to player
    11. Run nv show platform transceiver firmware files
    12. Validate only one file exist and the name of the first file has not been changed
    13. Validate all error messages
    """
    with allure.step('generate valid, invalid urls and invalid file name'):
        player_engine = engines['sonic_mgmt']
        fw_file_name1 = "sec_issu_46_120_10011_dev_signed.bin"
        invalid_url_1 = 'scp://{}:{}{}/tmp/'.format(player_engine.username, player_engine.password, player_engine.ip)
        invalid_url_2 = 'ffff://{}:{}@{}/tmp/'.format(player_engine.username, player_engine.password, player_engine.ip)
        fw_path_1 = f"{SystemConsts.GENERAL_TRANSCEIVER_FIRMWARE_FILES}/{fw_file_name1}"
        invalid_url_expected_message = "is not a 'remote-url-fetch'"
        invalid_file_expected_message = "File not found"
        non_exist_file_name = "NO_FILE.bin"

    with allure.step("Create platform object"):
        platform = Platform()

    with (allure.step("try to fetch using invalid URLs {}, {}".format(invalid_url_1, invalid_url_2))):
        assert (invalid_url_expected_message in
                platform.firmware.transceiver.action_fetch(fw_path_1, base_url=invalid_url_1)
                .get_returned_value(False)), (
            f"Test failed: trying to fetch using invalid url = {invalid_url_1} the expected error message = {invalid_url_expected_message}")
        assert (invalid_url_expected_message in
                platform.firmware.transceiver.action_fetch(fw_path_1, base_url=invalid_url_2)
                .get_returned_value(False)), (
            f"Test failed: trying to fetch using  invalid url = {invalid_url_2} the expected error message = {invalid_url_expected_message}")

    with allure.step("trying to upload non exist transceiver firmware file"):
        upload_path = '{}://{}:{}@{}/tmp/{}'.format('scp', player_engine.username, player_engine.password,
                                                    player_engine.ip, fw_file_name1)
        fetched_file = platform.firmware.transceiver.files.file_name[non_exist_file_name]
        fetched_file.action_upload(upload_path=upload_path).verify_result(False, invalid_file_expected_message)

    with allure.step('trying to rename non exist transceiver firmware file'):
        fetched_file.action_rename(new_name="Not_file.bin").verify_result(False, invalid_file_expected_message)

    with allure.step('trying to delete non exist file'):
        fetched_file.action_delete().verify_result(False, invalid_file_expected_message)

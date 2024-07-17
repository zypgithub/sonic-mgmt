import string
import time

import pytest

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.general_constants.constants import DefaultConnectionValues
from infra.tools.redmine.redmine_api import *
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_constants.constants_nvos import ImageConsts
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst
from ngts.nvos_tools.Devices.BaseDevice import BaseDevice
from ngts.nvos_tools.actions.Actions import Action
from ngts.nvos_tools.cli_coverage.operation_time import OperationTime
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.conftest import create_ssh_login_engine
from ngts.tools.test_utils import allure_utils as allure
from ngts.tools.test_utils.nvos_general_utils import check_partitions_capacity

logger = logging.getLogger()

PATH_TO_IMAGED_DIRECTORY = "/auto/sw_system_release/nos/nvos/"
PATH_TO_IMAGE_TEMPLATE = "{}/amd64/"

# To be uncommented when release is moved to next release - 25.01.4000
# BASE_IMAGE_VERSION_TO_INSTALL = "nvos-amd64-{pre_release_name}-001.bin"
# BASE_IMAGE_VERSION_TO_INSTALL_PATH = "/auto/sw_system_release/nos/nvos/{pre_release_name}-001/amd64/{base_image}"

# will be removed ones merged to develop
base_version = "/auto/sw_system_release/nos/nvos/25.01.4000/amd64/dev/nvos-amd64-25.01.4000.bin"
xdr_base_version = "/auto/sw_system_release/nos/nvos/25.02.0916-032/amd64/dev/nvos-amd64-25.02.0916-032.bin"
nvl5_base_version = "/auto/sw_system_release/nos/nvos/25.02.0506/amd64/dev/nvos-amd64-25.02.0506.bin"
BASE_IMAGE_VERSION_TO_INSTALL = "nvos-amd64-{pre_release_name}.bin"
BASE_IMAGE_VERSION_TO_INSTALL_PATH = "/auto/sw_system_release/nos/nvos/{pre_release_name}/amd64/{base_image}"

# will be removed ones merged to develop
base_versions = {'QTM3': xdr_base_version,
                 'NVLink-5 switch': nvl5_base_version}


@pytest.mark.checklist
@pytest.mark.nvos_ci
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.system
@pytest.mark.nvos_build
def test_show_system_image(original_version):
    """
    Show system image test

    Test flow:
    1. Run show system image
    2. Compare the current image value to the output from 'show system image current'
    3. Compare the output of 'show system image current' to 'show system version'
    4. Compare the output of 'show system image' to 'show system image installed'
    5. Compare the output of 'show system image' to 'show system image next'
    """
    system = System()
    with allure.step("Run show command to view system image"):
        show_output = system.image.show()
        output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(show_output).get_returned_value()

        with allure.step("Validate all expected fields in show output"):
            ValidationTool.verify_field_exist_in_json_output(output_dictionary,
                                                             [ImageConsts.CURRENT_IMG, ImageConsts.PARTITION1_IMG,
                                                              ImageConsts.NEXT_IMG]).verify_result()
            logger.info("All expected fields were found")

        with allure.step("Validate the values exist"):
            assert output_dictionary[ImageConsts.CURRENT_IMG] == original_version, f"Current image is invalid. Expected {original_version}"
            assert output_dictionary[ImageConsts.PARTITION1_IMG] == original_version, f"Partition1 image is invalid. Expected {original_version}"
            assert output_dictionary[ImageConsts.NEXT_IMG] == original_version, f"Next image is invalid. Expected {original_version}"

    with allure.step("Run show command to view system image files"):
        output_dictionary = system.image.files.get_files()
        if output_dictionary:
            for image_file, path_dict in output_dictionary.items():
                assert image_file in path_dict['path'], "The image file {} has the wrong path {}".format(image_file,
                                                                                                         path_dict[
                                                                                                             'path'])


@pytest.mark.checklist
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_downgrade_upgrade(release_name, test_api, original_version, devices):
    """
    Check the image rename cmd.
    Validate that install and delete commands will success with the new name
    and will fail with the old name.
    1. Fetch random image
    2. Rename image
    3. Install original image name, should fail
    4. Delete the original image name , should fail
    5. Install new image name , success
    6. Uninstall image
    7. Delete the new image name , success
    """
    TestToolkit.tested_api = test_api
    system = System()

    verify_current_version(original_version, system, devices.dut)

    original_images, _, original_image_partition, partition_id_for_new_image, fetched_image = \
        get_image_data_and_fetch_base_image(system, base_version)
    fetched_image_file = system.image.files.file_name[fetched_image]

    with allure.step("Rename image and verify"):
        new_name = RandomizationTool.get_random_string(20, ascii_letters=string.ascii_letters + string.digits)
        fetched_image_file.rename_and_verify(new_name)

    with allure.step("Install original image name, should fail"):
        logger.info("Install original image name: {}, should fail".format(fetched_image))
        system.image.files.file_name[fetched_image].action_file_install("Failed").verify_result()

    with allure.step("Delete original image name, should fail"):
        system.image.files.delete_files([fetched_image], "File not found")

    try:
        orig_engine: LinuxSshEngine = TestToolkit.engines.dut
        fetched_image_file.action_rename(fetched_image)
        install_image_and_verify(orig_engine=orig_engine, image_name=fetched_image, partition_id=partition_id_for_new_image,
                                 original_images=original_images, system=system, release_name=release_name,
                                 test_name='test_downgrade_upgrade')
    finally:
        # cleanup - boot back with orig image, uninstall new image, and restore to orig engine
        cleanup_test(system, original_images, original_image_partition, [fetched_image], orig_engine=orig_engine)


@pytest.mark.checklist
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_image_upload(engines, release_name, test_api, original_version, devices):
    """
    Uploading image file to player and validate.
    1. Fetch random image
    2. Upload image to player
    3. Validate image uploaded to player
    4. Delete image file from player
    5. Delete image file from dut
    """
    TestToolkit.tested_api = test_api
    system = System()

    verify_current_version(original_version, system, devices.dut)

    _, _, _, _, image_names = get_image_data_and_fetch_random_image_files(release_name, system)
    image_name = image_names[0]
    upload_protocols = ['scp', 'sftp']
    player = engines['sonic_mgmt']
    image_file = system.image.files.file_name[image_name]

    try:
        with allure.step("Upload image to player {} with the next protocols : {}".format(player.ip, upload_protocols)):
            for protocol in upload_protocols:

                with allure.step("Upload image to player with {} protocol".format(protocol)):
                    upload_path = '{}://{}:{}@{}/tmp/{}'.format(protocol, player.username, player.password, player.ip, image_name)
                    image_file.action_upload(upload_path)

                with allure.step("Validate file was uploaded to player and delete it"):
                    assert player.run_cmd(cmd='ls /tmp/ | grep {}'.format(image_name)), "Did not find the file with ls cmd"
                    player.run_cmd(cmd='rm -f /tmp/{}'.format(image_name))
    finally:
        with allure.step("Delete file from player"):
            system.image.files.delete_files([image_name])
            system.image.files.verify_show_files_output(unexpected_files=[image_name])


@pytest.mark.checklist
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_image_uninstall(release_name, test_api, original_version, test_name, devices):
    """
     Will check the uninstall commands

    Test flow:
    1. Validate that uninstall with 1 image only will fail
    2. Fetch and install an images
    3. Validate that uninstall will fail (because one is the current and the other is next-boot)
    4. Set the original image to be booted next
    5. Validate that uninstall will success
    """
    TestToolkit.tested_api = test_api
    image_uninstall_test(release_name, original_version, devices, uninstall_force="", test_name=test_name)


@pytest.mark.checklist
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.system
def test_image_uninstall_force(release_name, original_version, test_name, devices):
    """
     Will check the uninstall force commands

    Test flow:
    1. Validate that uninstall force with 1 image only will fail
    2. Fetch and install force an images
    3. Validate that uninstall force success
    4. Set the original image to be booted next
    5. Validate that uninstall force will success
    """
    image_uninstall_test(release_name, original_version, devices, uninstall_force="force", test_name=test_name)


@pytest.mark.checklist
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_image_bad_flow(engines, release_name, test_api, original_version):
    """
    Check bad flow scenarios:
    -	Fetch something that doesn’t / already exist
    -	Delete something that doesn’t exist
    -	Install something that doesn’t exist
    -	Install the same current image
    -	Boot next something that doesn’t / already exist
    -	Rename something that doesn’t exist
    -	Upload image that doesn’t / already exist

    """
    TestToolkit.tested_api = test_api
    system = System()
    original_images, original_image, original_image_partition, partition_id_for_new_image = get_image_data(system)
    rand_name = RandomizationTool.get_random_string(10, ascii_letters=string.ascii_letters)
    file_rand_name = system.image.files.file_name[rand_name]

    with allure.step("Get an available image file"):
        image_name, image_path = get_images_to_fetch(release_name, original_image)[0]
        images_name = []
        image_file = system.image.files.file_name[image_name]

    with allure.step("Fetch bad flows"):
        with allure.step("Fetch an image"):
            player = engines['sonic_mgmt']
            scp_path = 'scp://{}:{}@{}'.format(player.username, player.password, player.ip)
            system.image.action_fetch(scp_path + image_path)
            images_name.append(image_name)
        with allure.step("Fetch the same image again"):
            system.image.action_fetch(scp_path + image_path)
        with allure.step("Fetch an image that does not exist"):
            system.image.action_fetch(scp_path + image_path + rand_name, "Failed")

    with allure.step("Delete bad flows"):
        with allure.step("Delete file that does not exist"):
            system.image.files.delete_files([rand_name], "File not found")

    with allure.step("Install bad flows"):
        with allure.step("Install image file that does not exist"):
            file_rand_name.action_file_install("Image does not exist").verify_result()

    with allure.step("Boot-next bad flows"):
        if not original_images[ImageConsts.PARTITION2_IMG]:
            with allure.step("Boot-next {}, even tough we have no image there".format(ImageConsts.PARTITION2_IMG)):
                system.image.action_boot_next(ImageConsts.PARTITION2_IMG, 'Failed')
        with allure.step("Boot-next random string"):
            system.image.action_boot_next(ImageConsts.PARTITION2_IMG, "Failed")
        with allure.step("Boot-next the same partition"):
            system.image.action_boot_next(original_image_partition)

    with allure.step("Rename bad flows"):
        with allure.step("Rename image file that does not exist"):
            file_rand_name.action_rename(rand_name, "File not found")

    with allure.step("Upload bad flows"):
        player = engines['sonic_mgmt']
        upload_path = 'scp://{}:{}@{}/tmp/'.format(player.username, player.password, player.ip)
        with allure.step("Upload image file that does not exist"):
            file_rand_name.action_upload(upload_path, "File not found")
        with allure.step("Upload the same image twice"):
            with allure.step("First upload"):
                image_file.action_upload(upload_path)
                with allure.step("Validate file was uploaded"):
                    assert player.run_cmd(
                        cmd='ls /tmp/ | grep {}'.format(image_name)), "Did not find the file with ls cmd"
            with allure.step("Second upload"):
                image_file.action_upload(upload_path)
                with allure.step("Delete the file from the player"):
                    player.run_cmd(cmd='rm -f /tmp/{}'.format(image_name))

    with allure.step("Delete all images that have been fetch during the test"):
        system.image.files.delete_files(images_name)


@pytest.mark.checklist
@pytest.mark.image
@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_install_multiple_images(release_name, test_name, test_api, original_version, devices):
    """
    Install system image test

    1. Fetch 2 random images, Verify fetched images are listed in the show image files output
    5. Install image <img_1>, Verify installed images are listed in the show images
    6. Check available partitions capacity
    7. Set the original image to boot next
    8. Reboot dut and make sure it boots with original image
    9. Uninstall all images that have been installed during the test
    10. Delete all images that have been fetched during the test
    """
    TestToolkit.tested_api = test_api
    with allure.step(f"Update path with provided release name: {release_name}"):
        global BASE_IMAGE_VERSION_TO_INSTALL
        BASE_IMAGE_VERSION_TO_INSTALL = BASE_IMAGE_VERSION_TO_INSTALL.format(pre_release_name=release_name)
        logger.info(f"base image name: {BASE_IMAGE_VERSION_TO_INSTALL}")

        global BASE_IMAGE_VERSION_TO_INSTALL_PATH
        BASE_IMAGE_VERSION_TO_INSTALL_PATH = BASE_IMAGE_VERSION_TO_INSTALL_PATH.format(pre_release_name=release_name,
                                                                                       base_image=BASE_IMAGE_VERSION_TO_INSTALL)
        logger.info(f"base image path: {BASE_IMAGE_VERSION_TO_INSTALL_PATH}")

    system = System()

    verify_current_version(original_version, system, devices.dut)

    original_images, original_image, original_image_partition, partition_id_for_new_image, image_files = \
        get_image_data_and_fetch_random_image_files(release_name, system, 1)

    with allure.step("Verify fetched images are shown in the show command"):
        system.image.files.verify_show_files_output(expected_files=image_files)

    with allure.step("Verify show images output didn't change after the fetch command"):
        system.image.verify_show_images_output(original_images)

    with allure.step("Fetch the second image"):
        player = TestToolkit.engines['sonic_mgmt']
        scp_path = 'scp://{}:{}@{}'.format(player.username, player.password, player.ip)

        with allure.step("Fetch an image {}".format(scp_path + BASE_IMAGE_VERSION_TO_INSTALL_PATH)):
            system.image.action_fetch(scp_path + BASE_IMAGE_VERSION_TO_INSTALL_PATH)
            image_files.append(
                BASE_IMAGE_VERSION_TO_INSTALL) if BASE_IMAGE_VERSION_TO_INSTALL not in image_files else image_files

    try:
        with allure.step("Install the first image"):
            orig_engine: LinuxSshEngine = TestToolkit.engines.dut
            install_image_and_verify(orig_engine, BASE_IMAGE_VERSION_TO_INSTALL, partition_id_for_new_image,
                                     original_images, system, test_name)
        with allure.step("Test partitions available capacity"):
            check_partitions_capacity(allowed_limit=60)

    finally:
        cleanup_test(system, original_images, original_image_partition, image_files, orig_engine)


def image_uninstall_test(release_name, original_version, devices, uninstall_force="", test_name=""):
    """
     Will check the uninstall commands
     for uninstall force command , the uninstall_force param need to get "force"

    Test flow:
    1. Validate that uninstall [force] with 1 image only will fail
    2. Fetch and install an images
    3. Validate that uninstall will fail (because one is the current and the other is next-boot),
        but uninstall force success
        3.1. if we check the force command so we will install the new image again
    4. Set the original image to be booted next
    5. Validate that uninstall [force] will success
    """
    system = System()

    verify_current_version(original_version, system, devices.dut)

    original_images, _, original_image_partition, partition_id_for_new_image, fetched_image = \
        get_image_data_and_fetch_base_image(system, base_version)

    if original_images[partition_id_for_new_image]:
        with allure.step("uninstall image, while there are 2 images- should success"):
            system.image.action_uninstall(params="force")
    else:
        with allure.step("{} uninstall image, while there is just 1 image- should fail".format(uninstall_force)):
            system.image.action_uninstall(params=uninstall_force, expected_str="Nothing to uninstall")
            system.image.verify_show_images_output(original_images)

    try:
        with allure.step("Install image and verify"):
            orig_engine: LinuxSshEngine = TestToolkit.engines.dut
            installed_images_output = install_image_and_verify(orig_engine, fetched_image, partition_id_for_new_image,
                                                               original_images, system, release_name, test_name)

            with allure.step("Set the original image to be booted next and verify"):
                system.image.boot_next_and_verify(original_image_partition)

        if not uninstall_force:
            system.image.action_uninstall(expected_str="Failed to uninstall. Image set to boot-next")
            expected_show_images_output = create_images_output_dictionary(installed_images_output,
                                                                          installed_images_output[original_image_partition],
                                                                          "", "")
            system.image.verify_show_images_output(expected_show_images_output)

    finally:
        cleanup_test(system, original_images, original_image_partition, [fetched_image], orig_engine)


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_image_install_reject_with_smallcase_n(engines, test_api, original_version, devices):
    """
    Check the image install cmd by rejecting the prompt with 'n'
    Validate that install image command will be aborted when the prompt is rejected.
    1. Extract original image name
    2. Attempt image install command, reject the prompt with 'n'
    3. Check the image is the original one
    """
    TestToolkit.tested_api = test_api
    system = System()
    prompt_response = 'n'
    system_image_install_reject_with_prompt(engines, system, prompt_response, original_version, devices)


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_image_install_reject_with_uppercase_n(engines, test_api, original_version, devices):
    """
    Check the image install cmd by rejecting the prompt with 'N'
    Validate that install image command will be aborted when the prompt is rejected.
    1. Extract original image name
    2. Attempt image install command, reject the prompt with 'N'
    3. Check the image is the original one
    """
    TestToolkit.tested_api = test_api
    system = System()
    prompt_response = 'N'
    system_image_install_reject_with_prompt(engines, system, prompt_response, original_version, devices)


@pytest.mark.system
@pytest.mark.simx
@pytest.mark.image
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_system_image_install_reject_with_random_char(engines, test_api, original_version, devices):
    """
    Check the image install cmd by rejecting the prompt with random character
    Validate that install image command will be aborted when the prompt is rejected.
    1. Extract original image name
    2. Attempt image install command, reject the prompt with random character
    3. Check the image is the original one
    """
    TestToolkit.tested_api = test_api
    system = System()
    prompt_response = 't'
    system_image_install_reject_with_prompt(engines, system, prompt_response, original_version, devices)


def system_image_install_reject_with_prompt(engines, system, prompt_response, original_version, devices):

    verify_current_version(original_version, system, devices.dut)

    action_job_id = 0
    try:
        with allure.step("Create SSH Engine to login to the switch"):
            child = create_ssh_login_engine(engines.dut.ip, SystemConsts.DEFAULT_USER_ADMIN)
            assert isinstance(child.pid, int), "SSH login process failed to be spawned"
            respond = child.expect([DefaultConnectionValues.PASSWORD_REGEX, '~'])
            assert respond == 0, "SSH Connection to switch failed"
            child.sendline(engines.dut.password)
            respond = child.expect(DefaultConnectionValues.DEFAULT_PROMPTS[0])
            output = child.after.decode('utf-8')
            assert respond == 0, "Password prompt did not come up {out}".format(out=output)

        with allure.step("Extract Image name before attempting installing new image"):
            version_output = OutputParsingTool.parse_json_str_to_dictionary(system.version.show()).get_returned_value()
            image_name = version_output['image']

        with allure.step("Attempt install image and reject the prompt"):
            # Get the last action-job-id
            action = Action()
            output = OutputParsingTool.parse_json_str_to_dictionary(action.show()).get_returned_value()
            if output:
                action_job_id = max([int(id_no) for id_no in list(output)])
            # Since the install is to be aborted, using a dummy image name nvos.bin
            child.sendline('nv action install system image files nvos.bin')
            respond = child.expect('.*continue.*')
            assert respond == 0, "Install image confirmation prompt did not come up"
            child.sendline(prompt_response)
            respond = child.expect('.*abort.*')
            assert respond == 0, "Image install abort message did not appear"

        with allure.step("Verify install command was executed successfully"):
            # Increment action-job-id for latest command status
            action_job_id_str = str(action_job_id + 1)
            # extract last command execution status
            output = OutputParsingTool.parse_json_str_to_dictionary(action.show(action_job_id_str)).\
                get_returned_value()
            assert output['detail'] == 'Image install aborted by user' and \
                output['http_status'] == 200 and \
                output['state'] == 'action_success', "Image install command failed:{out}".format(out=output)

        with allure.step("Verify image is unchanged"):
            version_output = OutputParsingTool.parse_json_str_to_dictionary(system.version.show()).get_returned_value()
            image_name_post = version_output['image']
            assert image_name == image_name_post, "Image name changed even though image install command was aborted"

    finally:
        # close connection
        child.close()


def normalize_image_name(image_name):
    return image_name.replace("-amd64", "").replace(".bin", "")


def install_image_and_verify(orig_engine, image_name, partition_id, original_images, system, release_name,
                             test_name=''):
    with allure.step("Installing image {}".format(image_name)):
        device: BaseDevice = TestToolkit.devices.dut
        new_engine = LinuxSshEngine(orig_engine.ip, orig_engine.username,
                                    device.get_default_password_by_version(release_name))
        OperationTime.save_duration('image install', '', test_name,
                                    system.image.files.file_name[image_name].action_file_install_with_reboot,
                                    "", True, None, None, new_engine)

    with allure.step('replace dut engine'):
        TestToolkit.engines.dut = new_engine  # if install succeeded, need to replace dut engine

    with allure.step("Verify installed image"):
        time.sleep(5)
        expected_show_images_output = create_images_output_dictionary(original_images, image_name, image_name, partition_id)
        system.image.verify_show_images_output(expected_show_images_output)
        return expected_show_images_output


def get_list_of_directories(current_installed_img, starts_with=None):
    def mtime(f): return os.stat(os.path.join(PATH_TO_IMAGED_DIRECTORY, f)).st_mtime
    temp_directories = [dev for dev in os.listdir(PATH_TO_IMAGED_DIRECTORY) if "lastrc" not in str(dev)]
    temp_directories = list(sorted(temp_directories, key=mtime))

    all_directories = list(directory for directory in temp_directories if directory.startswith(starts_with))
    # above line will be replaced with below line once merged to develop
    # all_directories = list(directory for directory in temp_directories if directory.startswith(starts_with + "-"))

    all_directories.reverse()
    return_directories = {}
    for directory in all_directories:
        temp_dir = PATH_TO_IMAGED_DIRECTORY + PATH_TO_IMAGE_TEMPLATE.format(directory)
        if os.path.isdir(temp_dir) and "-001" not in temp_dir:
            logger.info("Searching for images in path: " + temp_dir)
            relevant_images = [f for f in os.listdir(temp_dir) if f.startswith("nvos-amd64-25.") and
                               current_installed_img.replace("nvos-25", "nvos-amd64-25") not in f]
            if relevant_images:
                return_directories[temp_dir] = relevant_images
        if len(return_directories) == 2:
            break
    return return_directories


def get_images_to_fetch(release_name, current_installed_img, images_amount=1):
    images_to_fetch = []
    with allure.step("Get list of images"):
        relevant_directories = get_list_of_directories(current_installed_img, release_name)
        for directory, images_list in relevant_directories.items():
            if len(images_to_fetch) == images_amount:
                break
            images_to_fetch.append((images_list[0], directory + images_list[0]))
            logger.info("Selected image: " + directory + images_list[0])

    return images_to_fetch


def get_next_partition_id(partition_id):
    return ImageConsts.PARTITION2_IMG if partition_id == ImageConsts.PARTITION1_IMG else ImageConsts.PARTITION1_IMG


def cleanup_test(system, original_images, original_image_partition, fetched_image_files, orig_engine=None):
    with allure.step("Cleanup step"):
        with allure.step("Set the original image to be booted next and verify"):
            system.image.boot_next_and_verify(original_image_partition)

        with allure.step("Reboot the system"):
            system.reboot.action_reboot(recovery_engine=orig_engine)

        with allure.step('restore original dut engine'):
            TestToolkit.engines.dut = orig_engine or TestToolkit.engines.dut

        with allure.step("Uninstall unused images and verify"):
            system.image.action_uninstall(params='force')
            system.image.verify_show_images_output(original_images)

        with allure.step("Delete all images that have been fetch during the test and verify"):
            system.image.files.delete_files(fetched_image_files)
            system.image.files.verify_show_files_output(unexpected_files=fetched_image_files)


def get_image_data(system):
    with allure.step("Save original installed image name"):
        original_images = system.image.get_image_field_values()
        original_image = original_images[ImageConsts.CURRENT_IMG]
        original_image_partition = system.image.get_image_partition(original_image, original_images)
        partition_id_for_new_image = get_next_partition_id(original_image_partition)
        logger.info("Original image: {}, partition: {}".format(original_image, original_image_partition))
        return original_images, original_image, original_image_partition, partition_id_for_new_image


def get_image_data_and_fetch_random_image_files(release_name, system, images_amount_to_fetch=1):
    original_images, original_image, original_image_partition, partition_id_for_new_image = get_image_data(system)

    with allure.step("Get {} available image files".format(images_amount_to_fetch)):
        images_to_fetch = get_images_to_fetch(release_name, original_image, images_amount_to_fetch)
        images_name = []
        for image_name, image_path in images_to_fetch:
            player = TestToolkit.engines['sonic_mgmt']
            scp_path = 'scp://{}:{}@{}'.format(player.username, player.password, player.ip)
            with allure.step("Fetch an image {}".format(scp_path + image_path)):
                system.image.action_fetch(scp_path + image_path)
                images_name.append(image_name)
    return original_images, original_image, original_image_partition, partition_id_for_new_image, images_name


def get_image_data_and_fetch_base_image(system, base_version):
    original_images, original_image, original_image_partition, partition_id_for_new_image = get_image_data(system)

    with allure.step(f"Fetch image {base_version}"):
        player = TestToolkit.engines['sonic_mgmt']
        system.image.action_fetch(ImageConsts.SCP_PATH_SERVER.format(username=player.username, password=player.password,
                                                                     ip=player.ip, path=base_version))
    image_name = base_version.split("/")[-1]
    return original_images, original_image, original_image_partition, partition_id_for_new_image, image_name


def verify_current_version(original_version, system, device):
    with allure.step(f"Verify that current image is {original_version}"):
        current_version = OutputParsingTool.parse_json_str_to_dictionary(system.version.show()).get_returned_value()['image']
        assert current_version == original_version, f"Current version is invalid: {current_version}, expected: {original_version}"

    # this allure step will be deleted ones the first XDR GA will be released
    global base_version
    with allure.step("Set base image according to device type"):
        logging.info(f"Device type: {device.asic_type}")
        base_version = base_versions.get(device.asic_type, base_version)


def create_images_output_dictionary(original_images, next_image, current_image, partition_id):
    expected_show_images_output = original_images.copy()
    if next_image:
        expected_show_images_output[ImageConsts.NEXT_IMG] = normalize_image_name(next_image)
    if current_image:
        expected_show_images_output[ImageConsts.CURRENT_IMG] = normalize_image_name(current_image)
    if partition_id:
        expected_show_images_output[partition_id] = expected_show_images_output[ImageConsts.NEXT_IMG]
    return expected_show_images_output

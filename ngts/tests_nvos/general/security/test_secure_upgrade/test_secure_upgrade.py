"""
This test checks secure upgrade feature. If we have a secure system with secured image installed
on it, the system is expected to install only secured images on it. So trying to install non-secure image
will cause fail and a print of failure message to console indicating it is not a secured image.
This test case validates the error flow mentioned above.

In order to run this test, you need to specify the following argument:

    --target_image_list (to contain one non-secure image path e.g. /tmp/images/my_non_secure_img.bin)
"""
import logging

import pytest

from ngts.nvos_constants.constants_nvos import ImageConsts
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.infra.SecureBootTool import SecureBootTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.test_secure_upgrade.constants import TEST_DIR, BAD_SIGNATURE_IMG, PROD_IMG, \
    DEV_IMG, PROD_IMG_FILE, DEV_IMG_FILE
from ngts.tests_nvos.general.security.test_secure_upgrade.helpers import mess_image_signature
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='session')
def keep_same_version_installed(engines):
    '''
    @summary: extract the current version installed as shown in the "show boot" output
    and restore original image installed after the test run
    :param duthost: device under test
    '''
    yield

    logging.info("Restoring original image by setting the boot-next to partition1, in case the non-signed "
                 "image was installed")
    engines.dut.run_cmd("nv action boot-next system image partition1")


@pytest.fixture(scope='session')
def non_secure_image_path(target_version_realpath):
    '''
    @summary: will extract the non secure image path from --target_image_list parameter
    :return: given non secure image path
    '''
    assert target_version_realpath is not None, "No target image is specified"
    cmd_runner = CmdRunner()
    image_filename = target_version_realpath.split('/')[-1]
    orig_image_path = f'{TEST_DIR}/{image_filename}'
    non_signed_bin_file = f'{TEST_DIR}/{BAD_SIGNATURE_IMG}.bin'
    with allure.step(f'copy target version image to test dir: {image_filename}'):
        cmd_runner.run_cmd(f'cp {target_version_realpath} {orig_image_path}')
    with allure.step('mess with the bin file to make it unsigned'):
        mess_image_signature(orig_image_path, non_signed_bin_file)
    yield non_signed_bin_file
    with allure.step(f'remove test images: {non_signed_bin_file}'):
        cmd_runner.run_cmd(f'rm -f {orig_image_path}')
        cmd_runner.run_cmd(f'rm -f {non_signed_bin_file}')


@pytest.fixture(scope='session')
def non_secure_images(target_version_realpath):
    '''
    @summary: will extract the non secure image path from --target_image_list parameter
    :return: given non secure image path
    '''
    assert target_version_realpath is not None, "No target image is specified"
    target_image_filename = target_version_realpath.split('/')[-1]
    cmd_runner = CmdRunner()
    orig_image = f'{TEST_DIR}/{target_image_filename}'

    images = {
        PROD_IMG: PROD_IMG_FILE,
        DEV_IMG: DEV_IMG_FILE
    }

    # with allure.step(f'copy target version image to test dir: {target_image_filename}'):
    #     cmd_runner.run_cmd_in_process(f'cp {target_version_realpath} {orig_image}')
    # with allure.step('create image with text injected to the last line (after signature)'):
    #     dst_path = f'{TEST_DIR}/{LAST_LINE_INJECTED_TEXT_IMG}.bin'
    #     cmd_runner.run_cmd_in_process(f'cp {orig_image} {dst_path}')
    #     cmd_runner.run_cmd_in_process(f'echo "{TEXT_TO_INJECT}" >> {dst_path}')
    #     images[LAST_LINE_INJECTED_TEXT_IMG] = dst_path
    # with allure.step('create bad signature image'):
    #     dst_path = f'{TEST_DIR}/{BAD_SIGNATURE_IMG}.bin'
    #     num_lines_from_bottom_of_signature_start = mess_image_signature(orig_image, dst_path)
    #     images[BAD_SIGNATURE_IMG] = dst_path
    # with allure.step('create bad payload image'):
    #     dst_path = f'{TEST_DIR}/{BAD_PAYLOAD_IMG}.bin'
    #     k = random.randint(6, 16) + num_lines_from_bottom_of_signature_start
    #     inject_string_to_image_k_lines_from_bottom(orig_image, k, dst_path)
    #     images[BAD_PAYLOAD_IMG] = dst_path
    # with allure.step('chmod 777 on test images'):
    #     cmd_runner.run_cmd_in_process(f'chmod 777 {TEST_DIR}/*.bin')

    yield images

    # with allure.step(f'delete created image files from: {TEST_DIR}'):
    #     with allure.step(f'delete {orig_image}'):
    #         cmd_runner.run_cmd_in_process(f'rm -f {orig_image}')
    #     with allure.step(f'delete {LAST_LINE_INJECTED_TEXT_IMG}'):
    #         cmd_runner.run_cmd_in_process(f'rm -f {images[LAST_LINE_INJECTED_TEXT_IMG]}')
    #     with allure.step(f'delete {BAD_SIGNATURE_IMG}'):
    #         cmd_runner.run_cmd_in_process(f'rm -f {images[BAD_SIGNATURE_IMG]}')
    #     with allure.step(f'delete {BAD_PAYLOAD_IMG}'):
    #         cmd_runner.run_cmd_in_process(f'rm -f {images[BAD_PAYLOAD_IMG]}')


@pytest.fixture(scope='session')
def non_secure_image_name(non_secure_image_path):
    '''
    @summary: will extract the non secure image name from target_version
    :return: given non secure image path
    '''
    img_name = non_secure_image_path.split('/')[-1]
    return img_name


@pytest.fixture(scope='session')
def delete_fetched_image(non_secure_image_name):
    '''
    @summary: delete the fetched image
    :param non_secure_image_name:
    :return:
    '''
    yield

    logging.info("Deleting fetched image")
    system = System()
    system.image.files.file_name[non_secure_image_name].action_delete().verify_result()


@pytest.mark.secure_boot
@pytest.mark.checklist
def test_non_secure_boot_upgrade_failure(keep_same_version_installed, is_secure_boot_enabled, non_secure_images, engines):
    """
    @summary: This test case validates non successful upgrade of a given non secure image
    """
    # system will be used for nv fetch/install
    system = System()
    img = non_secure_images[DEV_IMG] if SecureBootTool.is_prod_system(engines.dut) else non_secure_images[PROD_IMG]
    img_name = img.split('/')[-1]
    # install non secure image
    with allure.step(f"install non secure image - expect fail, image path = {img}"):
        with allure.step("Fetching the image"):
            system.image.action_fetch(img)

        try:
            with allure.step("Attempting installing non secure image"):
                system.image.files.file_name[img_name].action_file_install(expected_str="Failed to verify image signature").verify_result()
        finally:
            with allure.step(f'delete img file: {img_name}'):
                system.image.files.file_name[img_name].action_delete().verify_result()

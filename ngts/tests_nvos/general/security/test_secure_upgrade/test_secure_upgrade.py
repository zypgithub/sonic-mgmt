"""
This test checks secure upgrade feature. If we have a secure system with secured image installed
on it, the system is expected to install only secured images on it. So trying to install non-secure image
will cause fail and a print of failure message to console indicating it is not a secured image.
This test case validates the error flow mentioned above.

In order to run this test, you need to specify the following argument:

    --target_image_list (to contain one non-secure image path e.g. /tmp/images/my_non_secure_img.bin)
"""
import logging
import random

import pytest

from ngts.nvos_constants.constants_nvos import ImageConsts
from ngts.nvos_tools.infra.CmdRunner import CmdRunner
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.test_secure_upgrade.constants import TEST_DIR, BAD_SIGNATURE_IMG, BAD_PAYLOAD_IMG, \
    PROD_IMG, DEV_IMG, BEGIN_CMS, LAST_LINE_INJECTED_TEXT_IMG, PROD_IMG_FILE, DEV_IMG_FILE
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger(__name__)


@pytest.fixture(scope='session')
def keep_same_version_installed(engines):
    '''
    @summary: extract the current version installed as shown in the "show boot" output
    and restore original image installed after the test run
    :param duthost: device under test
    '''
    yield

    logger.info("Restoring original image by setting the boot-next to partition1, in case the non-signed "
                "image was installed")
    engines.dut.run_cmd("nv action boot-next system image partition1")


@pytest.fixture(scope='session')
def non_secure_image_path(target_version):
    '''
    @summary: will extract the non secure image path from --target_image_list parameter
    :return: given non secure image path
    '''
    assert target_version is not None, "No target image is specified"
    image_filename = target_version.split('/')[-1]
    non_signed_bin_file = f'{TEST_DIR}/{image_filename}'
    with allure.step(f'copy target version image to test dir: {image_filename}'):
        cmd_runner = CmdRunner()
        cmd_runner.run_cmd_in_process(f'cp {target_version} {non_signed_bin_file}')
    with allure.step('mess with the bin file to make it unsigned'):
        x = random.randint(6, 60)
        s = 'alon da king'
        cmd = f'sed -i "$(($(wc -l < {non_signed_bin_file}) - {x - 1}))i {s}" {non_signed_bin_file}'
        # cmd_runner.run_cmd_in_process(f'echo "alon da king" >> {non_signed_bin_file}')
        cmd_runner.run_cmd_in_process(cmd)
    yield non_signed_bin_file
    with allure.step(f'remove unsigned image: {non_signed_bin_file}'):
        cmd_runner.run_cmd_in_process(f'rm -f {non_signed_bin_file}')


@pytest.fixture(scope='session')
def non_secure_images(target_version):
    '''
    @summary: will extract the non secure image path from --target_image_list parameter
    :return: given non secure image path
    '''
    assert target_version is not None, "No target image is specified"
    target_image_filename = target_version.split('/')[-1]
    cmd_runner = CmdRunner()
    orig_image = f'{TEST_DIR}/{target_image_filename}'
    text = 'alon da king'

    images = {
        PROD_IMG: PROD_IMG_FILE,
        DEV_IMG: DEV_IMG_FILE
    }

    def inject_string_to_image_k_lines_from_bottom(file, k, dst_file=None):
        dst_file = dst_file or file
        with allure.step(f'inject string {k} lines from the bottom: {dst_file}'):
            cmd = f'sed "$(($(wc -l < {file}) - {k - 1}))i {text}" {file} > {dst_file}'
            cmd_runner.run_cmd_in_process(cmd)

    with allure.step(f'copy target version image to test dir: {target_image_filename}'):
        cmd_runner.run_cmd_in_process(f'cp {target_version} {orig_image}')
    with allure.step('create image with text injected to the last line (after signature)'):
        path = f'{TEST_DIR}/{LAST_LINE_INJECTED_TEXT_IMG}.bin'
        cmd_runner.run_cmd_in_process(f'cp {orig_image} {path}')
        cmd_runner.run_cmd_in_process(f'echo "{text}" >> {path}')
        images[LAST_LINE_INJECTED_TEXT_IMG] = path
    with allure.step('create bad signature image'):
        cmd = "tac " + orig_image + " | awk '/" + BEGIN_CMS + "/ {print NR}'"
        out, _, _ = cmd_runner.run_cmd_in_process(cmd)
        num_lines_from_bottom_of_signature_start = int(str(out).strip())
        logging.info(f'**** num_lines_from_bottom_of_signature_start - {num_lines_from_bottom_of_signature_start}')
        path = f'{TEST_DIR}/{BAD_SIGNATURE_IMG}.bin'
        k = random.randint(1, num_lines_from_bottom_of_signature_start - 1)
        inject_string_to_image_k_lines_from_bottom(orig_image, k, path)
        images[BAD_SIGNATURE_IMG] = path
    with allure.step('create bad payload image'):
        path = f'{TEST_DIR}/{BAD_PAYLOAD_IMG}.bin'
        k = random.randint(6, 16) + num_lines_from_bottom_of_signature_start
        inject_string_to_image_k_lines_from_bottom(orig_image, k, path)
        images[BAD_PAYLOAD_IMG] = path
    with allure.step('chmod 777 on test images'):
        cmd_runner.run_cmd_in_process(f'chmod 777 {TEST_DIR}/*.bin')

    yield images

    with allure.step(f'delete created image files from: {TEST_DIR}'):
        with allure.step(f'delete {orig_image}'):
            cmd_runner.run_cmd_in_process(f'rm -f {orig_image}')
        with allure.step(f'delete {LAST_LINE_INJECTED_TEXT_IMG}'):
            cmd_runner.run_cmd_in_process(f'rm -f {images[LAST_LINE_INJECTED_TEXT_IMG]}')
        with allure.step(f'delete {BAD_SIGNATURE_IMG}'):
            cmd_runner.run_cmd_in_process(f'rm -f {images[BAD_SIGNATURE_IMG]}')
        with allure.step(f'delete {BAD_PAYLOAD_IMG}'):
            cmd_runner.run_cmd_in_process(f'rm -f {images[BAD_PAYLOAD_IMG]}')


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

    logger.info("Deleting fetched image")
    system = System()
    system.image.files.file_name[non_secure_image_name].action_delete("Action succeeded")


@pytest.mark.secure_boot
@pytest.mark.checklist
def test_non_secure_boot_upgrade_failure(non_secure_image_path, keep_same_version_installed, non_secure_image_name,
                                         delete_fetched_image, is_secure_boot_enabled):
    """
    @summary: This test case validates non successful upgrade of a given non secure image
    """
    # system will be used for nv fetch/install
    system = System()

    # install non secure image
    with allure.step("install non secure image - expect fail, image path = {}".format(non_secure_image_path)):
        logger.info("install non secure image - expect fail, image path = {}".format(non_secure_image_path))

    with allure.step("Fetching the image"):
        logger.info("Fetching the image")
        remote_image_path = ImageConsts.SCP_PATH + non_secure_image_path
        system.image.action_fetch(remote_image_path)

    with allure.step("Attempting installing non secure image"):
        logger.info("Attempting installing non secure image")
        system.image.files.file_name[non_secure_image_name].action_file_install(
            "Failed to verify image signature").verify_result()

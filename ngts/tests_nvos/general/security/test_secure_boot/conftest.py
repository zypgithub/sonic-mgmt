import logging
import re

import pytest

from ngts.tests_nvos.general.security.test_secure_boot.constants import SecureBootConsts

logger = logging.getLogger(__name__)


@pytest.fixture(scope='function')
def restore_image_path(request, target_version_realpath):
    '''
    @summary: return the path to restore image
    '''
    return target_version_realpath
    # restore_to_image = request.config.getoption('restore_to_image')
    # assert restore_to_image is not None, "Please specify restore image path"
    # restore_to_image = get_real_file_path(restore_to_image)
    # logger.info(f'After test will recover to image: {restore_to_image}')
    # return restore_to_image


@pytest.fixture(scope='function')
def mount_uefi_disk_partition(engines, serial_engine):
    '''
    @summary: will load the uefi disk partition
    :param serial_engine: serial connection
    '''
    logger.info(f"mounting UEFI disk partition at {SecureBootConsts.MOUNT_FOLDER}")
    engines.dut.run_cmd(f'sudo mkdir -p {SecureBootConsts.MOUNT_FOLDER}', validate=True)
    output = engines.dut.run_cmd(f'sudo {SecureBootConsts.EFI_PARTITION_CMD}')
    partitions = re.findall(r'/dev/sda\d', output)
    if not partitions:
        partitions = re.findall(r'/dev/nvme.*', output)
    uefi_partition = partitions[0]
    engines.dut.run_cmd(f"sudo mount -o rw,auto,user,fmask=0022,dmask=0000 {uefi_partition} {SecureBootConsts.MOUNT_FOLDER}", validate=True)

import allure
import logging
import pytest

from ngts.tests.nightly.secure.constants import SonicSecureBootConsts


logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
@allure.title('Verify secure boot is enabled')
def test_verify_secure_is_enabled(topology_obj):
    """
    This script will verify secure boot is enabled on the dut.
    :param topology_obj: topology object fixture
    :return: raise assertion error in case of script failure
    """

    logger.info("Check the secure boot status")
    engine = topology_obj.players['dut']['engine']
    secure_boot_state = engine.run_cmd('mokutil --sb-state')
    assert 'enabled' in secure_boot_state, "Secure boot not enabled as expected"

    logger.info("Check the secure boot is dev or prod")
    device = engine.run_cmd('ls /dev/mst/ | egrep mt.*_pciconf0')
    if not device:
        pytest.fail(f"The mst device is not found.")
    mst_info = engine.run_cmd(f'sudo flint -d /dev/mst/{device} q full')
    assert SonicSecureBootConsts.SECURE_FW_MSG in mst_info, "Secure fw is not enabled"
    if SonicSecureBootConsts.SECURE_FW_DEV_MSG in mst_info:
        logger.info("The system is dev secured")
    else:
        logger.info("The system is prod secured")

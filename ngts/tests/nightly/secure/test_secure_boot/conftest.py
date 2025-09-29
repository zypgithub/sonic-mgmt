import pytest
import logging

from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from ngts.tests.nightly.secure.constants import SecureBootConsts
from ngts.scripts.sonic_deploy.deploy_helper_methods import DeployTopologyHelper
from ngts.scripts.sonic_deploy.sonic_only_methods import SonicInstallationSteps
from ngts.tests.nightly.secure.constants import SonicSecureBootConsts

logger = logging.getLogger()
allure.logger = logger


@pytest.fixture(scope='module', autouse=True)
def post_secure_boot_steps(secure_boot_helper, topology_obj, setup_name, platform_params, chip_type, is_performance,
                           is_air):
    """
    This function will invoke function post_installation_steps
    It would recover exactly the same environment as ngts/scripts/sonic_deploy/test_sonic_deploy_image.py does
    after secure boot test
    """
    setup_info = DeployTopologyHelper.get_info_from_topology(topology_obj, SecureBootConsts.WORKSPACE_PATH)

    yield

    dut = setup_info['duts'][0]
    secure_boot_helper.restore_basic_config(topology_obj, setup_name, platform_params, is_air)
    SonicInstallationSteps.post_installation_steps(
        topology_obj=topology_obj, sonic_topo='ptf-any', recover_by_reboot=True, setup_name=setup_name,
        platform_params=platform_params, apply_base_config=True, target_version="",
        is_shutdown_bgp=False, reboot_after_install=False, deploy_only_target=False, fw_pkg_path="",
        reboot="no", additional_apps="", setup_info=setup_info, dut_alias=dut['dut_alias'], chip_type=chip_type,
        is_performance=is_performance, xml_rpc=False, is_air=is_air)


@pytest.fixture(scope="function")
def update_onie_timeout(platform_params):
    logger.info(f"Updating ONIE timeout for {platform_params.platform}")
    original_onie_timeout = SonicSecureBootConsts.ONIE_TIMEOUT
    if 'sn5640' in platform_params.platform:
        SonicSecureBootConsts.ONIE_TIMEOUT *= SonicSecureBootConsts.BISON_ONIE_TIMEOUT_FACTOR

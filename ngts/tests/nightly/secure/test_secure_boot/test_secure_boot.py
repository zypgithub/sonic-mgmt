"""
Secure Boot Suite case:

In this test file we introduce different cases for secure boot feature.
Secure Boot is a feature that validates secure boot and only signed modules are running.

In order to run this test, you need to specify the following argument: kernel_module_path

Secure Boot and Upgrade Test Cases

https://confluence.nvidia.com/pages/viewpage.action?spaceKey=SW&title=SONiC+NGTS+SECURE+BOOT+AND+UPGRADE+Documentation
"""
import logging
import pytest

from retry.api import retry_call
from tests.common.plugins.allure_wrapper import allure_step_wrapper as allure
from ngts.tests.nightly.secure.constants import SecureBootConsts, SonicSecureBootConsts
pytestmark = pytest.mark.skip_config_check

logger = logging.getLogger()
allure.logger = logger


@pytest.mark.disable_loganalyzer
def test_unsigned_shim_secure_boot(secure_boot_helper, secure_boot_consts, mount_uefi_disk_partition,
                                   test_server_engine, recover_switch_after_secure_boot_violation_message):
    """
    In this test case we want to simulate broken signature of shim
    by manually changing it and then do reboot/fast-reboot and see that it doesn't boot successfully
    """
    with allure.step("Test secure boot of shim validation"):
        secure_boot_helper.unsigned_file_secure_boot(secure_boot_consts.SHIM_FILEPATH,
                                                     test_server_engine,
                                                     secure_boot_consts.SHIM)


@pytest.mark.disable_loganalyzer
def test_unsigned_grub_secure_boot(secure_boot_helper, secure_boot_consts, mount_uefi_disk_partition,
                                   test_server_engine, recover_switch_after_secure_boot_violation_message):
    """
    In this test case we want to simulate broken signature of grub
    by manually changing it and then do reboot/fast-reboot and see that it doesn't boot successfully
    """
    with allure.step("Test secure boot of grub validation"):
        secure_boot_helper.unsigned_file_secure_boot(secure_boot_consts.GRUB_FILEPATH,
                                                     test_server_engine,
                                                     secure_boot_consts.GRUB)


@pytest.mark.disable_loganalyzer
def test_unsgined_vmlinuz_secure_boot(secure_boot_helper, secure_boot_consts, test_server_engine,
                                      vmiluz_filepath, recover_switch_after_secure_boot_violation_message):
    """
    In this test case we want to simulate broken signature of vmlinuz component
    by manually changing it and then do reboot/fast-reboot/warm-reboot and see that it doesn't boot successfully
    """
    with allure.step("Test secure boot of vmlinuz validation"):
        secure_boot_helper.unsigned_file_secure_boot(vmiluz_filepath, test_server_engine, secure_boot_consts.VMLINUZ)


@pytest.mark.disable_loganalyzer
def test_signed_kernel_module_load(secure_boot_helper):
    """
    In this test case we want to validate successful
    load of secured kernel module
    """
    with allure.step("Test secure boot of signed kernel module"):
        secure_boot_helper.signed_kernel_module_secure_boot()


@pytest.mark.disable_loganalyzer
def test_non_signed_kernel_module_load(secure_boot_helper, restore_kernel_module):
    """
    In this test case we want to validate unsuccessful load
    of unsigned kernel module
    """
    with allure.step("Test secure boot of unsigned kernel module"):
        secure_boot_helper.un_signed_kernel_module_secure_boot()


@pytest.mark.disable_loganalyzer
@pytest.mark.parametrize("image_path", SecureBootConsts.IMAGE_PATH)
def test_sonic_secure_boot_from_onie(secure_boot_helper, request, image_path, topology_obj, restore_to_sonic):
    """
    In this test case we want to validate unsuccessful load of unsigned image from onie
    """
    with allure.step("Test secure boot in onie mode"):
        secure_boot_helper.onie_secure_boot(request, image_path, topology_obj)


@pytest.mark.disable_loganalyzer
@pytest.mark.parametrize("signed_type", [SonicSecureBootConsts.FWUTIL_KEY_MISMATCHED_SIGNED])
def test_fwutil_install_onie_key_check_fail(secure_boot_helper, platform_params, signed_type, dut_secure_type,
                                            recover_switch_after_secure_boot_violation_message):
    """
    In this test case we want to validate unsuccessful upgrade of unsigned onie by fwutil
    """
    with allure.step("Test secure boot of fwutil - onie upgrade"):
        secure_boot_helper.fwutil_install_secure_boot_negative(
            SonicSecureBootConsts.ONIE_COMPONENT, signed_type, dut_secure_type, platform_params,
            SonicSecureBootConsts.INVALID_SIGNATURE_EXPECTED_MESSAGE[SonicSecureBootConsts.ONIE_COMPONENT],
            SonicSecureBootConsts.SWITCH_RECOVER_TIMEOUT)


@pytest.mark.disable_loganalyzer
@pytest.mark.parametrize("signed_type", [SonicSecureBootConsts.FWUTIL_KEY_MISMATCHED_SIGNED])
def test_fwutil_install_bios_key_check_fail(secure_boot_helper, platform_params, signed_type, dut_secure_type):
    """
    In this test case we want to validate unsuccessful upgrade of key mismatched bios by fwutil
    """
    with allure.step("Test secure boot of fwutil - bios upgrade"):
        secure_boot_helper.fwutil_install_secure_boot_negative(
            SonicSecureBootConsts.BIOS_COMPONENT, signed_type, dut_secure_type, platform_params,
            SonicSecureBootConsts.INVALID_SIGNATURE_EXPECTED_MESSAGE[SonicSecureBootConsts.BIOS_COMPONENT],
            SonicSecureBootConsts.SWITCH_RECOVER_TIMEOUT)
    with allure.step("Wait for the switch auto boot to SONiC"):
        retry_call(secure_boot_helper.is_sonic_mode, tries=5, delay=10, logger=logger)

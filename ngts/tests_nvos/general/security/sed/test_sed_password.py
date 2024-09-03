import random
import string

import allure
import pytest

from ngts.nvos_tools.infra.TpmTool import TpmTool
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.system.System import *


@pytest.mark.system
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_change_sed_password(engines, devices, sed_default_password, test_api):
    """
    @summary:
        Verify that change SED password works via nv action both for NVUE and OpenAPI

        Steps:
        1. Set a new SED password via nv action
        2. Verify the password is working via sed util.
        3. Check that tpm primary and secondary bank have this password.
        4. Reboot the system and verify nvos works.
        5. Check that tpm primary and secondary bank have this password.
    """
    TestToolkit.tested_api = test_api
    switch: LinuxSshEngine = engines.dut
    tpm_tool = TpmTool(switch)
    system = System()
    new_sed_password = "test_sed_password"

    _verify_tpm_banks_password(tpm_tool, sed_default_password)

    with allure.step(f"Set new SED password via nv action change system security sed-password {new_sed_password}"):
        system.security.action_change_sed_password(new_sed_password)

    with allure.step("Get disk name for current device"):
        disk_name_output = switch.run_cmd("sudo sedutil-cli --scan")
        if (start := disk_name_output.find("/dev/")) != -1 and (end := disk_name_output.find(" ", start)) != -1:
            disk_name = disk_name_output[start:end]
        else:
            assert False, "Can't find correct disk name for this device"

    _verify_sed_password_works(switch, new_sed_password, disk_name)

    _verify_tpm_banks_password(tpm_tool, new_sed_password)

    with allure.step("Reboot the system"):
        system.reboot.action_reboot(engine=switch, device=devices.dut)

    _verify_tpm_banks_password(tpm_tool, new_sed_password)


@pytest.mark.system
@pytest.mark.security
def test_back_old_pass(engines, devices, sed_default_password):
    """
    @summary:
        Verify that change SED password works when flow was broken during the action flow
        The tpm primary bank password was changed, but SED password didn't change

        Steps:
        1. Set a new SED password in primary tpm bank
        2. Change primary TPM bank to new wrong password.
        3. Reboot the system and verify nvos works.
        4. Check that tpm primary and secondary bank have old SED password.
    """
    switch: LinuxSshEngine = engines.dut
    tpm_tool = TpmTool(switch)
    system = System()
    new_sed_password = "old_password"

    _verify_tpm_banks_password(tpm_tool, sed_default_password)

    with allure.step("Set primary tpm bank to new password"):
        tpm_tool.set_sed_password_primary_bank(new_sed_password)

    with allure.step("Reboot the system"):
        system.reboot.action_reboot(engine=switch, device=devices.dut)

    _verify_tpm_banks_password(tpm_tool, sed_default_password)


@pytest.mark.system
@pytest.mark.security
def test_back_new_pass(engines, devices, sed_default_password):
    """
    @summary:
        Verify that change SED password works with new password when banks don't match

        Steps:
        1. Set a new SED password via nv action
        2. Change secondary TPM bank to wrong password.
        3. Reboot the system and verify nvos works.
        4. Check that tpm primary and secondary bank have new SED password.
    """
    TestToolkit.tested_api = ApiType.OPENAPI

    switch: LinuxSshEngine = engines.dut
    tpm_tool = TpmTool(switch)
    system = System()
    new_sed_password = "Another_pass"

    _verify_tpm_banks_password(tpm_tool, sed_default_password)

    with allure.step(f"Set new SED password via nv action change system security sed-password {new_sed_password}"):
        system.security.action_change_sed_password(new_sed_password)

    with allure.step("Set secondary tpm bank to wrong password"):
        wrong_password = "i_am_wrong_password"
        tpm_tool.set_sed_password_secondary_bank(wrong_password)

    with allure.step("Reboot the system"):
        system.reboot.action_reboot(engine=switch, device=devices.dut)

    _verify_tpm_banks_password(tpm_tool, new_sed_password)


@pytest.mark.system
@pytest.mark.security
def test_password_length_negative(engines, devices, sed_default_password):
    """
    @summary:
        Verify that change SED password works only with passwords from 8 to 250 chars

        Steps:
        1. Try to set a new SED password via nv action
        2. See it fails
    """
    switch: LinuxSshEngine = engines.dut
    tpm_tool = TpmTool(switch)
    system = System()
    long_pass = generate_random_string_with_length(251, 502)
    small_pass = generate_random_string_with_length(1, 7)

    _verify_tpm_banks_password(tpm_tool, sed_default_password)

    with allure.step(f"Try to set SED password via nv action {long_pass}"):
        # Should check for error the action itself
        system.security.action_change_sed_password(long_pass)

    _verify_tpm_banks_password(tpm_tool, sed_default_password)

    with allure.step(f"Try to set SED password via nv action {small_pass}"):
        system.security.action_change_sed_password(small_pass)

    _verify_tpm_banks_password(tpm_tool, sed_default_password)


def _verify_tpm_banks_password(tpm_tool, expected_password):
    with allure.step("Verify tpm banks have old password"):
        with allure.independent_step("Verify primary bank has correct password"):
            password_primary = tpm_tool.get_sed_password_primary_bank()
            assert password_primary == expected_password, f"The password from tpm primary bank should match {expected_password}"
        with allure.independent_step("Verify secondary bank has correct password"):
            password_secondary = tpm_tool.get_sed_password_secondary_bank()
            assert password_secondary == expected_password, f"The password from tpm secondary bank should match {expected_password}"


def _verify_sed_password_works(switch: LinuxSshEngine, password: str, disk_name: str):
    with allure.step("Verify SED is working with provided password"):
        cmd = f"sudo sedutil-cli --listLockingRanges '{password}' '{disk_name}'"
        output = switch.run_cmd(cmd)
        exit_code = int(switch.run_cmd('echo $?').split('\n')[-1])
        assert exit_code == 0, "The sed list locking ranges should be successful"


def _change_sed_password_manually(engine, old_pass: str, new_pass: str, disk_name: str):
    engine.run_cmd(f"sudo sedutil-cli --setadmin1pwd '{old_pass}' '{new_pass}' '{disk_name}'")


def generate_random_string_with_length(minimal: int, maximum: int):
    with allure.step(f"Generate random string with specified range length {minimal}-{maximum}"):
        length = random.randint(minimal, maximum)
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

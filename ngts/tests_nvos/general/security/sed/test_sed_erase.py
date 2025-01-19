import pytest

from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.system
@pytest.mark.security
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_sed_erase(engines, devices, serial_engine, test_api):
    """
    @summary:
        Verify that SED erase performs full disk wipe via NVUE and OpenAPI

        Steps:
        1. Run nv action run system security sed-erase
        2. Disconnect engine
        3. Verify ssh stills works correctly
        4. Verify serial connection is working
        5. Reboot system
        6. Verify disk was fully wiped
    """
    system = System()
    engine = engines.dut

    with allure.step("Run sed erase action"):
        system.security.action_sed_erase(engine, devices.dut)

    engine.disconnect()
    with allure.step("Verify ssh connection works"):
        OutputParsingTool.parse_json_str_to_dictionary(system.show()).verify_result()
    with allure.step("Verify serial connection works"):
        OutputParsingTool.parse_json_str_to_dictionary(system.show(dut_engine=serial_engine)).verify_result()

    with allure.step("Reboot the system"):
        engine.run_cmd("sudo reboot now")

    #  Manually verify disk was fully wiped from EFI shell. Need to disable Secure boot first.
    #  Run dblk BLK0 1 1000 and verify all block are zeroed.


@pytest.mark.system
@pytest.mark.security
def test_sed_high_ram(engines, devices):
    """
    @summary:
        Verify that SED erase does not work if less than 3 gb of ram left

        Steps:
        1. Leave less than 3GB in RAM
        2. Run nv action run system security sed-erase
        mkdir /mnt/ramdisk
        sudo mount -t tmpfs -o size=5G tmpfs /mnt/ramdisk
        sudo mount -t ramfs ramfs /mnt/ramdisk
        dd if=/dev/zero of=/mnt/ramdisk/file bs=1M count=5000
    """
    system = System()
    engine = engines.dut

    twelve_gb = 12288
    dir_name = "/mnt/ramspace"
    _mount_ram_space(dir_name, engine, twelve_gb)

    with allure.step("Run sed erase action"):
        system.security.action_sed_erase(engine, devices.dut)

    engine.run_cmd(f"sudo umount {dir_name}")


def _mount_ram_space(mount_point, engine, count):
    engine.run_cmd(f"sudo mkdir {mount_point}")
    engine.run_cmd(f"sudo mount -t ramfs ramfs {mount_point}")
    engine.run_cmd(f"dd if=/dev/zero of={mount_point}/file bs=1M count={count}")

import allure
import logging

from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.OnieTool import OnieTool
from ngts.nvos_tools.infra.PxeTool import PxeTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.general.ONIE.constants import OnieConsts

logger = logging.getLogger()


def test_update_onie_via_grub_menu(topology_obj, engines, devices):
    """
     @summary: Verify that the device can update its ONIE firmware via the GRUB menu.

     Steps:
       1. Determine which ONIE updater image to fetch (based on OPN/IPN).
       2. Open a serial connection to the DUT.
       3. Reboot into the ONIE update entry in the GRUB menu.
       4. Download the ONIE updater via wget.
       5. Run the onie‑self‑update tool and confirm success.
       6. Wait for the NOS to come back online.
       7. Verify that the last firmware update entry shows Success and today’s date.

     @param topology_obj: testbed topology (players, attributes, etc.)
     @param engines:     CLI/serial engine handles (engines.dut, etc.)
     @param devices:     device objects (devices.dut, etc.)
     @raises AssertionError: if any step fails (will reboot DUT in finally)
     """
    TestToolkit.tested_api = 'NVUE'
    nvue_cli_obj = NvueGeneralCli(engine=engines.dut, device=devices.dut)
    with allure.step("Get ONIE updater url path"):
        url = OnieTool.get_onie_updater_path(topology_obj)

    with allure.step("Initializing serial connection to device"):
        serial_engine = nvue_cli_obj.enter_serial_connection_context(topology_obj)

    try:
        with allure.step('Prepare for ONIE update: enter ONIE'):
            nvue_cli_obj.enter_onie(topology_obj, OnieConsts.UPDATE_ONIE_MENU_ENTRY)

        with allure.step('Fetch ONIE updater file using wget'):
            OnieTool.fetch_onie_updater(serial_engine, url)

        with allure.step('Update ONIE via onie-updater'):
            OnieTool.run_onie_updater(serial_engine)

        with allure.step("Complete ONIE update"):
            nvue_cli_obj._wait_nos_to_become_functional(engines.dut, serial_engine=serial_engine)

        with allure.step("Verify successful installation"):
            OnieTool.verify_onie_update(engines.dut)

    except Exception as err:
        logger.info("ONIE update failed on error and will now remote reboot machine:\n{}".format(err))
        nvue_cli_obj.remote_reboot_nvue(topology_obj)
        raise AssertionError(err)


def test_install_onie_via_pxe_boot(topology_obj, engines, devices, target_version_realpath):
    """
    @summary: Verify that the device can install ONIE via PXE boot menu.

    Steps:
      1. Determine PXE‑bootable ONIE image name for this DUT.
      2. Open a serial connection and reboot.
      3. Enter the PXE menu (ESC+8).
      4. Navigate to and select the desired ONIE image.
      5. Wait for the ONIE installer GRUB menu to appear.
      6. At the ONIE prompt, send “onie‑stop” to pause installer.
      7. From the ONIE shell, install the target NOS image.
      8. Wait for the NOS to come back online.

    @param topology_obj: testbed topology (players, attributes, etc.)
    @param engines:     CLI/serial engine handles (engines.dut, etc.)
    @param devices:     device objects (devices.dut, etc.)
    @param target_version_realpath: full path to NOS image to install
    @raises AssertionError: if any step fails (will reboot DUT in finally)
    """
    TestToolkit.tested_api = 'NVUE'
    nvue_cli_obj = NvueGeneralCli(engine=engines.dut, device=devices.dut)
    with allure.step("Get ONIE image name for PXE"):
        name = OnieTool.get_onie_version_name_for_pxe(topology_obj)

    with allure.step("Initializing serial connection to device"):
        serial_engine = nvue_cli_obj.enter_serial_connection_context(topology_obj)

    with allure.step('Executing remote reboot'):
        nvue_cli_obj.remote_reboot_nvue(topology_obj)

    try:
        with allure.step("Entering PXE boot menu"):
            PxeTool.enter_pxe(serial_engine)

        with allure.step(f"Select and install ONIE version: {name}"):
            PxeTool.pxe_find_and_select(serial_engine, name)

        with allure.step("Wait for grub menu after installation"):
            PxeTool.wait_for_grub_menu(serial_engine)

        with allure.step("Waiting for onie prompt"):
            nvue_cli_obj.wait_for_onie_prompt(serial_engine)

        with allure.step("Send 'onie-stop'"):
            nvue_cli_obj.send_onie_stop(serial_engine)

        with allure.step('Install image onie - NVOS'):
            nvue_cli_obj.install_nos_using_onie_in_serial(target_version_realpath, engines.dut, topology_obj, 'dut', serial_engine)

        with allure.step("Complete PXE flow"):
            engines.dut.disconnect()
            DutUtilsTool.wait_for_nvos_to_become_functional(engines.dut)

    except Exception as err:
        logger.info("ONIE install via PXE failed on error and will now remote reboot machine:\n{}".format(err))
        nvue_cli_obj.remote_reboot_nvue(topology_obj)
        raise AssertionError(err)

import logging

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.general_constants.constants import DefaultConnectionValues
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.OnieTool import OnieTool
from ngts.nvos_tools.infra.PxeTool import PxeTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.general.ONIE.constants import OnieConsts
from ngts.nvos_constants.constants_nvos import ApiType

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
       7. Verify that the last firmware update entry shows Success and today's date.

     @param topology_obj: testbed topology (players, attributes, etc.)
     @param engines:     CLI/serial engine handles (engines.dut, etc.)
     @param devices:     device objects (devices.dut, etc.)
     @raises AssertionError: if any step fails (will reboot DUT in finally)
     """
    TestToolkit.tested_api = ApiType.NVUE
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

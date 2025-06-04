import logging

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.general_constants.constants import DefaultConnectionValues, DefaultVMCred
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.OnieTool import OnieTool
from ngts.nvos_tools.infra.PxeTool import PxeTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.general.ONIE.constants import OnieConsts
from ngts.nvos_tools.infra.SshCmdBuilder import ScpPassCmdBuilder
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_constants.constants_nvos import ApiType, NvosConst

logger = logging.getLogger()


def test_full_disk_wipe_system_recovery(engines, devices, topology_obj, serial_engine, target_version_realpath):
    """
    @summary:
        Verify that SED (Self-Encrypting Drive) erase performs a full disk wipe
        and that the system can successfully be re provisioned via PXE and ONIE
        following the erase.

    @steps:
        1. Run the SED erase action via NVUE.
        2. Disconnect the main SSH engine.
        3. Verify SSH connection is restored.
        4. Verify serial connection is operational.
        5. Remotely reboot the system.
        6. Automatically enter PXE boot menu via serial.
        7. Select and install the specified ONIE version.
        8. Wait for GRUB menu after ONIE installation.
        9. Enter ONIE rescue mode.
       10. Wait for ONIE prompt.
       11. Download provisioning tarball on external system.
       12. SCP the provisioning tarball to the switch.
       13. Extract and run provisioning script in ONIE.
       14. Wait for GRUB menu after provisioning.
       15. Wait for ONIE prompt again.
       16. Stop ONIE with 'onie-stop'.
       17. Install NVOS image via ONIE using serial connection.
       18. Disconnect DUT and wait for NVOS to become functional.
       19. Clean up temporary files (provisioning tarball) on external system.

    @raises:
        AssertionError if any provisioning or verification step fails.
    """
    system = System()
    TestToolkit.tested_api = ApiType.NVUE
    nvue_cli_obj = NvueGeneralCli(engine=engines.dut, device=devices.dut)
    engine = engines.dut
    scp_engine = LinuxSshEngine(NvosConst.FIT70, DefaultVMCred.DEFAULT_USERNAME, DefaultVMCred.DEFAULT_PASS)
    with allure.step("Get PXE menu step count based on device OPN/IPN type"):
        step_count = PxeTool.get_pxe_menu_step_count(topology_obj)

    with allure.step("Run disk erase action"):
        system.disk.action_erase(engine, devices.dut, force=True).verify_result()

    with allure.step("Disconnect engine"):
        engine.disconnect()

    with allure.step("Verify ssh connection works"):
        system.show()

    with allure.step("Verify serial connection works"):
        serial_engine.run_cmd('nv show system', ['System is ready'], timeout=30)

    with allure.step('Executing remote reboot'):
        nvue_cli_obj.remote_reboot_nvue(topology_obj)

    try:
        with allure.step("Automatically entering PXE boot menu"):
            PxeTool.enter_pxe(serial_engine, True)

        with allure.step(f"Select ONIE version entry by stepping {step_count} times"):
            PxeTool.pxe_select_by_steps(serial_engine, step_count)

        with allure.step("Wait for grub menu after installation"):
            PxeTool.wait_for_grub_menu(serial_engine)

        with allure.step('Prepare for provisioning: enter ONIE Rescue'):
            nvue_cli_obj.enter_onie(topology_obj, OnieConsts.RESCUE_MENU_ENTRY)

        with allure.step("Waiting for onie prompt"):
            nvue_cli_obj.wait_for_onie_prompt(serial_engine)

        with allure.step("Get provisioning URL"):
            provisioning_url = OnieTool.get_provisioning_url(topology_obj)
            filename = provisioning_url.split('/')[-1]

        with allure.step(f"Download provisioning tarball to {NvosConst.FIT70}"):
            output = scp_engine.run_cmd(f"wget {provisioning_url}")
            assert "saved" in output.lower(), "couldn't download file"

        with allure.step(f"Copy provisioning tarball from {NvosConst.FIT70} to switch"):
            sshpass_cmd = ScpPassCmdBuilder(user=DefaultConnectionValues.ONIE_USERNAME, password=DefaultConnectionValues.ONIE_PASSWORD, host=engine.ip,
                                            src=filename, dest="/tmp/").NoStrictHostKeyChecking().NoUserKnownHostsFile().build()
            scp_engine.run_cmd(sshpass_cmd)

        with allure.step("Extract and execute provisioning script in ONIE"):
            OnieTool.run_provisioning(serial_engine, filename)

        with allure.step("Wait for grub menu after provisioning"):
            PxeTool.wait_for_grub_menu(serial_engine)

        with allure.step("Waiting for onie prompt"):
            nvue_cli_obj.wait_for_onie_prompt(serial_engine)

        with allure.step("Send 'onie-stop'"):
            nvue_cli_obj.send_onie_stop(serial_engine)

        with allure.step('Install NVOS image'):
            nvue_cli_obj.install_nos_using_onie_in_serial(target_version_realpath, engines.dut, topology_obj, 'dut', serial_engine)

        with allure.step("Complete PXE flow"):
            engines.dut.disconnect()
            DutUtilsTool.wait_for_nvos_to_become_functional(engines.dut)

    except Exception as err:
        logger.info("test failed on error and will now remote reboot machine:\n{}".format(err))
        nvue_cli_obj.remote_reboot_nvue(topology_obj)
        raise AssertionError(err)

    finally:
        if filename:
            try:
                with allure.step(f"Clean up provisioning tarball from {NvosConst.FIT70}"):
                    scp_engine.run_cmd(f"rm -f {filename}")
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up file {filename} from {NvosConst.FIT70}: {cleanup_err}")

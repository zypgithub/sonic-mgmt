import pytest
import logging


logger = logging.getLogger()


@pytest.mark.disable_loganalyzer
def test_boot_into_onie(cli_objects, topology_obj, is_simx, platform_params):
    hwsku = platform_params['hwsku']
    if is_simx or cli_objects.dut.general.is_bluefield(hwsku):
        pytest.skip('No need to reboot into ONIE for SIMX/DPU setups')

    if cli_objects.dut.general.check_dut_is_alive():
        logger.info("Dut connection is ok.")
        try:
            cli_objects.dut.general.prepare_onie_reboot_script_on_dut()
            onie_reboot_script_cmd = '/tmp/onie_reboot.sh install'
            topology_obj.players['dut']['engine'].send_config_set([onie_reboot_script_cmd],
                                                                  exit_config_mode=False,
                                                                  cmd_verify=False)
        except Exception as err:
            logger.info(f"Failed to switch into onie by onie_reboot.sh.{err}. "
                        f"\n\n It might be a bad image, try recover it ")
            cli_objects.dut.general.prepare_for_installation(topology_obj)

    else:
        cli_objects.dut.general.prepare_for_installation(topology_obj)

    logger.info("DUT is in onie status")

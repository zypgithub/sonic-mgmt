import allure
import logging

from ngts.constants.constants import PlayersAliases
from ngts.nvos_constants.constants_nvos import BiosConsts
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.BiosTool import BiosTool
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive

logger = logging.getLogger()


@allure.title('Configure Switch BIOS')
def configure_bios(topology_obj):
    """
        Deploy SONiC/NVOS testing topology and configure BIOS on switch devices
        Flow:
            1. Get relevant setup info from topology object
            on each DUT:
            2. Perform remote reboot and enter BIOS
            3. in BIOS, disable BIOS password if there's one
            4. in BIOS, enable network stack if its disabled
            5. Save and exit BIOS

        :param topology_obj: topology object fixture.
    """
    dut_engine = None
    try:
        for host in topology_obj.players:
            if host in PlayersAliases.duts_list:
                dut_ip = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Specific'].get(
                    'ip address', '')
                dut_engine = topology_obj.players[host]['engine']
                sub_type = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Specific'].get(
                    'Sub-Type', '').lower()
                menu = BiosConsts.NVLINK_BIOS_MENU_PAGES if sub_type == 'juliet' else BiosConsts.BIOS_MENU_PAGES

                bios_obj = BiosTool()
                # dummy class init just to be able to access non-static inner methods
                nvue_cli_obj = NvueGeneralCli(engine=None, device=None)

                with allure.step('Entering BIOS on: {}'.format(dut_ip)):
                    bios_obj.enter_bios(topology_obj, nvue_cli_obj)

                serial_engine = nvue_cli_obj.enter_serial_connection_context(topology_obj)
                with allure.step('Configuring empty BIOS password'):
                    bios_obj.go_to_bios_page(serial_engine, "Main", "Security", menu)
                    bios_obj.bios_find_and_select(serial_engine, "Administrator Password")
                    bios_obj.disable_bios_password(serial_engine)

                with allure.step('Enabling network stack configuration'):
                    bios_obj.go_to_bios_page(serial_engine, "Security", "Advanced", menu)
                    bios_obj.bios_find_and_select(serial_engine, "Network Stack Configuration")
                    bios_obj.enable_network_stack(serial_engine)

                with allure.step('Done configuring network stack and BIOS password, Save and exit the BIOS'):
                    bios_obj.go_to_bios_page(serial_engine, "Advanced", "Save & Exit", menu)
                    bios_obj.bios_find_and_select(serial_engine, "Save Changes and Exit")
                    serial_engine.run_cmd(BiosConsts.ENTER, '.*', timeout=3, send_without_enter=True)

                logger.info("BIOS configuration script finished running, will now wait for machine to come up")

    except Exception as err:
        logger.info("BIOS configuration failed on error and will now remote reboot machine:\n{}".format(err))
        TestToolkit.GeneralApi[TestToolkit.tested_api].remote_reboot(None, topology_obj)
        raise AssertionError(err)
    finally:
        if dut_engine:
            dut_engine.disconnect()
            check_port_status_till_alive(True, dut_engine.ip, dut_engine.ssh_port)
            DutUtilsTool.wait_for_nvos_to_become_functional(dut_engine).verify_result()

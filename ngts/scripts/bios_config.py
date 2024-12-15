import allure
import logging

from ngts.constants.constants import PlayersAliases
from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_tools.infra.BiosTools.BiosFactory import BiosFactory
from ngts.nvos_tools.infra.DutUtilsTool import DutUtilsTool
from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tools.test_utils.switch_recovery import remote_reboot_dut
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
    TestToolkit.tested_api = 'NVUE'
    dut_engine = None
    nvue_cli_obj = NvueGeneralCli(engine=None, device=None)
    try:
        for host in topology_obj.players:
            if host in PlayersAliases.duts_list:
                dut_ip = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Specific'].get(
                    'ip address', '')
                switch_type = topology_obj.players[host]['attributes'].noga_query_data['attributes']['Specific'].get(
                    'switch type', '')
                dut_engine = topology_obj.players[host]['engine']
                bios_obj = BiosFactory.create_bios(switch_type, topology_obj, dut_engine, nvue_cli_obj, dut_ip)
                remote_reboot_dut(topology_obj)
                bios_obj.config_flow()

    except Exception as err:
        logger.info("BIOS configuration failed on error and will now remote reboot machine:\n{}".format(err))
        remote_reboot_dut(topology_obj)
        raise AssertionError(err)
    finally:
        if dut_engine:
            dut_engine.disconnect()
            check_port_status_till_alive(True, dut_engine.ip, dut_engine.ssh_port)
            DutUtilsTool.wait_for_nvos_to_become_functional(dut_engine).verify_result()

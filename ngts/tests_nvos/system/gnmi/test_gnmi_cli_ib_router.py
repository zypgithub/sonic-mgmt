import pytest
import logging
import time

from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts
from ngts.nvos_tools.ib.Ib import Ib
from ngts.tests_nvos.system.gnmi.helpers import verify_msg_not_in_out_or_err, parse_gnmi_output
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import GnmiMode, GnmicErr
from ngts.constants.constants import GnmiConsts
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.ib_router.constants import IbRouterConsts
from ngts.nvos_tools.infra.IbRouterTool import IbRouterTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool

logger = logging.getLogger()


@pytest.mark.gnmi
@pytest.mark.skip_clear_config
def test_gnmi_ib_router_ports(engines, devices, random_api):
    """
    Check on active ib router setup the interfaces assigned swid
    Test flow:
    on every active interface according to topology, check via gnmi that its assigned to the correct SWID
    """
    with allure.step("Get GNMI client"):
        client = get_gnmi_client(engines, devices)

    with allure.step("Checking that GNMI report correct SWID on each port"):
        for idx, port_list in IbRouterConsts.SWID_TO_PORTS_DICT.items():
            swid_name = IbRouterTool.get_swid_name(idx)
            for port in port_list:
                logger.info(f"Current port: {port}.")

                with allure.step(f"Start gnmi session and get port {port} output"):
                    gnmi_output_as_dict = get_gnmi_ib_router_output(client, full_path=port, call_interface_gnmi=True)

                with allure.step(f"Checking that gmni input for interface {port} matches the expected SWID {swid_name}"):
                    port_swid = gnmi_output_as_dict[IbInterfaceConsts.LINK_IB_SUBNET]
                    assert port_swid == swid_name, f"port {port} does not belong to SWID {swid_name}, it found to be member of unexpected SWID {port_swid}"


@pytest.mark.gnmi
@pytest.mark.skip_clear_config
def test_gnmi_ib_router_swid_count(engines, devices, random_api):
    """
    Compare GNMI swid count to the expected count
    Test flow:
    will go over the paths and do quick validation
    /ib-router/static/swid-count

    """
    with allure.step("Get GNMI client"):
        client = get_gnmi_client(engines, devices)

    with allure.step(f"Start gnmi session and get SWID count, and make sure its equal to {IbRouterConsts.SWID_COUNT}"):
        gnmi_output_as_dict = get_gnmi_ib_router_output(client, full_path=f"state/swid-count")

        logger.info(f"received swid count from gnmi - {gnmi_output_as_dict[IbRouterConsts.SWID_COUNT]}")
        assert gnmi_output_as_dict[IbRouterConsts.SWID_COUNT] == str(IbRouterConsts.SWID_NUM)


@pytest.mark.gnmi
@pytest.mark.skip_clear_config
def test_gnmi_ib_router_subnet(engines, devices, random_api):
    """
    Compare GNMI swid count to the expected count
    Test flow:
    will go over the paths and do quick validation
    ib-router/subnets/subnet[name=<subnet_name>]/state
    ib-router/subnets/subnet[name=<subnet_name>]/state/subnet-prefix
    ib-router/subnets/subnet[name=<subnet_name>]/state/counters
    """
    ib = Ib(None)

    with allure.step("Get GNMI client"):
        client = get_gnmi_client(engines, devices)

    with allure.step("Checking that GNMI report correct subnet info per SWID"):
        for swid_id in IbRouterConsts.OPERATIONAL_SWIDS:
            swid_name = IbRouterTool.get_swid_name(swid_id)
            with allure.step(f"Checking correct info for SWID {swid_id} - {swid_name}"):
                with allure.step(f"Checking correct subnet prefix for SWID {swid_id} - {swid_name} for gnmi subnet state command"):
                    gnmi_output_as_dict = get_gnmi_ib_router_output(client, full_path=f"subnets/subnet[name={swid_name}]/state")
                    with allure.step(f"Checking correct subnet prefix for SWID {swid_id} - {swid_name} "):
                        show_router_output = OutputParsingTool.parse_json_str_to_dictionary(ib.router.routing_table.show()).get_returned_value()
                        gnmi_subnet_prefix = gnmi_output_as_dict[IbRouterConsts.SUBNET_PREFIX]
                        cli_subnet_prefix = show_router_output[swid_name][IbRouterConsts.SUBNET_PREFIX]
                        logger.info(f"gnmi prefix for {swid_name} - {gnmi_subnet_prefix}, cli prefix - {cli_subnet_prefix}")
                        assert gnmi_subnet_prefix == cli_subnet_prefix, f"on swid {swid_name}, gnmi prefix {gnmi_subnet_prefix} is not equal to cli prefix {cli_subnet_prefix}"

                    with allure.step(f"Checking SWID {swid_id} - {swid_name} is valid"):
                        gnmi_valid_value = gnmi_output_as_dict[IbRouterConsts.VALID]
                        assert gnmi_valid_value == 'true', f"on swid {swid_name}, gnmi valid field is  {gnmi_valid_value} but expected to be 'true'"

                with allure.step(f"Checking correct subnet prefix for SWID {swid_id} - {swid_name} on prefix specific gnmi command"):
                    gnmi_output_as_dict = get_gnmi_ib_router_output(client, full_path=f"subnets/subnet[name={swid_name}]/state/subnet-prefix")

                    gnmi_subnet_prefix = gnmi_output_as_dict[IbRouterConsts.SUBNET_PREFIX]
                    logger.info(f"gnmi prefix for {swid_name} - {gnmi_subnet_prefix}, cli prefix - {cli_subnet_prefix}")
                    assert gnmi_subnet_prefix == cli_subnet_prefix, f"on swid {swid_name}, gnmi prefix {gnmi_subnet_prefix} is not equal to cli prefix {cli_subnet_prefix}"

                with allure.step(f"Running counters fetch for SWID {swid_id} - {swid_name} as sanity check"):
                    get_gnmi_ib_router_output(client, full_path=f"subnets/subnet[name={swid_name}]/state/counters")


def get_gnmi_client(engines, devices):
    """
    create gnmi client used by the tests
    """
    return GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, devices.dut.default_username,
                      devices.dut.default_password, verify_tools_installed=True)


def get_gnmi_ib_router_output(gnmi_client_obj, full_path='', call_interface_gnmi=False):
    """
    run ib router gnmi query with given client object and full path - for example subnets/subnet[name=infiniband-2]/state/counters
    """
    gnmi_prev_output_as_dict = {}
    logger.info(f"Pulling data every 1 seconds until we pull the latest data for {full_path}")
    for iteration in range(30):
        if call_interface_gnmi:
            gnmi_out, gnmi_err = gnmi_client_obj.gnmic_subscribe_interface(mode=GnmiMode.ONCE, interface_name=full_path,
                                                                           skip_cert_verify=True, wait_till_done=True,
                                                                           interface_path='')
        else:
            gnmi_out, gnmi_err = gnmi_client_obj.gnmic_subscribe_ib_router(mode=GnmiMode.ONCE, skip_cert_verify=True,
                                                                           wait_till_done=True,
                                                                           full_path=full_path)

        verify_msg_not_in_out_or_err(GnmicErr.AUTH_FAIL, gnmi_out, gnmi_err)
        gnmi_output_as_dict = parse_gnmi_output(gnmi_out)
        if len(gnmi_prev_output_as_dict) == 0:
            gnmi_prev_output_as_dict = gnmi_output_as_dict
        if gnmi_output_as_dict != gnmi_prev_output_as_dict:
            break
        assert gnmi_output_as_dict, f"failed to get any value from {full_path}"
        time.sleep(1)
        return gnmi_output_as_dict

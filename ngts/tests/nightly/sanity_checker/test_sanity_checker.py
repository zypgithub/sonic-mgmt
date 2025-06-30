import allure
import logging
import pytest
import re
import csv
import os

from retry.api import retry
from ngts.cli_util.cli_parsers import generic_sonic_output_parser
from ngts.helpers.secure_boot_helper import SonicSecureBootHelper
from ngts.tests.conftest import get_dut_loopbacks
from ngts.constants.constants import FILE_INCLUDE_FAILED_SANITY_CHECKER_CASE
from ngts.tests.nightly.sanity_checker.analyze_sanity_checker_result_and_take_action import write_failed_sanity_checker_cases_to_file

pytestmark = [
    pytest.mark.disable_loganalyzer
]

logger = logging.getLogger()

POSSIBLE_CPLD_LIST = ['CPLD1', 'CPLD2', 'CPLD3', 'CPLD4']
CURRENT_PATH = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope='module')
def sonic_topo():
    return "ptf-any"


@pytest.fixture(scope='module')
def is_in_deploy_image_flow(request):
    # When some sanity checker cases run in the following scripts, it will not fail the case when case fail
    script_in_deploy_image_flow_list = ["test_deploy_and_upgrade.py", "test_apply_configuration.py"]
    if request.node.name in script_in_deploy_image_flow_list:
        logger.info("sanity checker cases are running in deploy flow script")
        return True
    else:
        logger.info("sanity checker cases are not running in deploy flow script")
        return False


@pytest.fixture(scope='module', autouse=True)
def clear_file_inlcude_failed_sanity_check_case():
    if os.path.exists(FILE_INCLUDE_FAILED_SANITY_CHECKER_CASE):
        os.remove(FILE_INCLUDE_FAILED_SANITY_CHECKER_CASE)


@pytest.fixture(scope='module')
def platform_json_data(topology_obj):
    platform_json_data = topology_obj.players['dut']['cli'].chassis.get_platform_json_data()
    yield platform_json_data


@pytest.fixture(scope='function')
def enable_and_disable_fanout_lldp(request, engines, topology_obj, interfaces):
    """
    Pytest fixture which is enabling lldp on fanout and disable it when teardown
    :param request: request object fixture
    :param engines: engines object fixture
    :param topology_obj: topology object fixture
    """

    def enable_lldp(engine):
        logger.info(f"enable lldp on {engine.ip}")
        cmd_enalbe_lldp = "sudo config feature state lldp enabled" if engine.device_type == "linux" else "lldp"
        engine.run_cmd(cmd_enalbe_lldp)

    def disable_lldp(engine):
        logger.info(f"disable lldp on {engine.ip}")
        cmd_disable_lldp = "sudo config feature state lldp disabled" if engine.device_type == "linux" else "no lldp"
        engine.run_cmd(cmd_disable_lldp)

    enable_lldp(engines.fanout)
    if 'fanout_b' in engines:
        enable_lldp(engines.fanout_b)

    yield

    disable_lldp(engines.fanout)
    if 'fanout_b' in engines:
        disable_lldp(engines.fanout_b)


@pytest.mark.sanity_checker_common
def test_cpld_version_check(topology_obj, engines, platform_params, cli_objects, request, is_in_deploy_image_flow, sonic_topo):
    """
    This test validates that the CPLD version(s) deployed on the dut are the latest approved ones,
    as defined in the firmware.json versions file. If not, try it install the latest one.
    If case fail,
        The following actions will be handled in analyze_sanity_checker_result_and_take_action.py
        1. For sonic_tigon_r-tigon-15, sonic_anaconda_r-anaconda-15, the regression will be stopped by mars
        2. For the remaining setups,
           we will raise the failed case information in the allure report and disable bug handler tool
    :param engines: engines fixture
    :param platform_params: platform_params fixture
    """
    if "dpu" in sonic_topo:
        pytest.skip("DPU platform does not support this case")
    is_test_failed = False
    with allure.step('Getting info about the CPLD component from firmware.json'):
        cpld_component_data = None
        defined_cpld = None
        for cpld in POSSIBLE_CPLD_LIST:
            try:
                cpld_component_data = SonicSecureBootHelper.get_component_data(platform_params, cpld)
                defined_cpld = cpld
                break
            except Exception as e:
                logger.info(e)
                pass
        if not (defined_cpld and cpld_component_data):
            err_msg = "Failed to get the data for any CPLD from the firmware.json"
            assert_failure_or_just_print_err(err_msg, is_in_deploy_image_flow)
            is_test_failed = True

    with allure.step('Getting info about CPLD from dut'):
        component_versions_dict = get_info_about_current_components_version_dict(engines.dut)

    with allure.step(f'Checking CPLD version for: {defined_cpld}'):
        _, latest_cpld_ver = SonicSecureBootHelper.get_latest_expected_cpld(cpld_component_data, defined_cpld)
        current_cpld_ver = component_versions_dict[defined_cpld]
        if current_cpld_ver != latest_cpld_ver:
            if not is_in_deploy_image_flow:
                dut_topology_obj = topology_obj.players['dut']['cli']
                try:
                    with allure.step(f'Shutdown bpg all'):
                        dut_topology_obj.bgp.shutdown_bgp_all()
                    with allure.step(f'Restore CPLD to {latest_cpld_ver}'):
                        logger.info(f"Restore CPLD to the expected one:{latest_cpld_ver}")
                        SonicSecureBootHelper.restore_cpld(cli_objects, engines, topology_obj, platform_params, defined_cpld)
                    with allure.step("disconnect dut"):
                        engines.dut.disconnect()
                    with allure.step(f" After power cycle, check containers and interfaces are up"):
                        dut_topology_obj.general.verify_dockers_are_up()
                        check_port_oper_up_on_admin_up(dut_topology_obj)

                    with allure.step(f"Check if the cpld version is updated to {latest_cpld_ver}"):
                        component_versions_dict = get_info_about_current_components_version_dict(engines.dut)
                        current_cpld_ver = component_versions_dict[defined_cpld]
                        assert current_cpld_ver == latest_cpld_ver, \
                            f'Current {defined_cpld} version: {current_cpld_ver} is not latest: {latest_cpld_ver}'
                except Exception as err:
                    raise Exception(f"Fail to restore cpld \n. {err}")
                finally:
                    with allure.step(f'Start bpg all'):
                        dut_topology_obj.bgp.startup_bgp_all()
            else:
                logger.error(
                    f"The current CPLD {current_cpld_ver} ver does not match the latest one {latest_cpld_ver}")
                is_test_failed = True

    write_failed_case_name(is_test_failed, request.node.name, is_in_deploy_image_flow)


@pytest.mark.sanity_checker_ci
@pytest.mark.sanity_checker_common
def test_device_asic_check(engines, platform_params):
    """
    This test is verify that device asic status is ok.
    If case fail, the consequent regression steps will be stopped by mars
    """
    regrex_pci_dvice_name = ".*PCI Device Name:(?P<pci_device_name>.*)"
    device_info = engines.dut.run_cmd('sudo mlxfwmanager --query')
    pci_device_name = None
    for line in device_info.split("\n"):
        res = re.search(regrex_pci_dvice_name, line.strip())
        if res:
            pci_device_name = res.groupdict()["pci_device_name"]
            logger.info(f"pic device name is {pci_device_name}")
    assert pci_device_name, "device asic is not up"


@pytest.mark.flaky(reruns=2, reruns_delay=10)
@pytest.mark.sanity_checker_community
def test_cable_connection_between_dut_and_fanout_check(engines, topology_obj, request, enable_and_disable_fanout_lldp):
    """
    This test is verify that cable connection between dut and fanout is ok.
    If case fail, the consequent regression steps will be stopped by mars
    """
    cli_object_a = topology_obj.players['dut']['cli']
    dut_a = engines.dut

    with allure.step("Check cable connection between dut a and fanout a"):
        logger.info("Check cable connection between dut a and fanout a")
        check_one_dut_to_fanout_cable_connection(cli_object_a, dut_a)

    if "dual" in request.config.getoption("--setup_name"):
        cli_object_a = topology_obj.players['dut-b']['cli']
        dut_b = engines.dut_b
        with allure.step("Check cable connection between dut b and fanout b"):
            logger.info("Check cable connection between dut b and fanout b")
            check_one_dut_to_fanout_cable_connection(cli_object_a, dut_b)


@pytest.mark.flaky(reruns=30, reruns_delay=4)
@pytest.mark.sanity_checker_community
def test_bgp_session_status_check(topology_obj):
    """
    This test is verify that bgp session status is ok.
    If case fail, the consequent regression steps will be stopped by mars
    """
    ip_bgp_summary = topology_obj.players['dut']['cli'].bgp.parse_ip_bgp_summary()
    regex_full_digit = r"^\d+$"
    for neighbor_ip, neighbor_info in ip_bgp_summary.items():
        assert re.match(regex_full_digit, neighbor_info["State/PfxRcd"]), \
            f"The bpg session with neighbor {neighbor_ip} doesn't work"


@pytest.mark.flaky(reruns=30, reruns_delay=4)
@pytest.mark.sanity_checker_canonical
def test_cable_connection_for_canonical_check(topology_obj, sonic_topo):
    """
    This test is verify that the cable connection for canonical setup is ok.
    If case fail, the consequent regression steps will be stopped by mars
    """
    if sonic_topo != "ptf-any":
        pytest.skip(f"The topo {sonic_topo} does not support the case ")
    dut_cli_object = topology_obj.players['dut']['cli']
    lldp_table_info = dut_cli_object.lldp.parse_lldp_table_info()

    def _check_port_between_dut_and_host(host_name):
        host_cli_object = topology_obj.players[host_name]['cli']
        host_hostname = host_cli_object.general.hostname()

        for index in range(1, 3):
            dut_host_port = topology_obj.ports[f"dut-{host_name}-{index}"]
            host_dut_port = topology_obj.ports[f"{host_name}-dut-{index}"]
            assert lldp_table_info[dut_host_port][0] == host_hostname \
                and host_dut_port in lldp_table_info[dut_host_port][3], \
                f"port {index} connection ({dut_host_port}, {host_dut_port}) " \
                f"between dut and {host_name} doesn't match the definition in noga"

    _check_port_between_dut_and_host("ha")
    _check_port_between_dut_and_host("hb")

    # check loopbacks on dut
    lb_ports = get_dut_loopbacks(topology_obj, split=True)
    for ports in lb_ports:
        assert ports[1] == lldp_table_info[ports[0]][
            3], f"loopback for ports {ports} doesn't match the definition in noga"


@pytest.mark.flaky(reruns=30, reruns_delay=4)
@pytest.mark.sanity_checker_ci
@pytest.mark.sanity_checker_common
def test_fan_status_check(platform_params, topology_obj, platform_json_data, request, is_in_deploy_image_flow):
    """
    This test is verify that the fan status is ok.
    If case fail, we will raise the failed case information in the allure report and disable bug handler tool
    """
    fan_status_info = topology_obj.players['dut']['cli'].chassis.show_platform_fan()
    is_test_failed = False

    if len(platform_json_data["chassis"]["fan_drawers"]) == 1:
        fan_number = len(platform_json_data["chassis"]["fan_drawers"][0]["fans"])
    else:
        fan_number = len(platform_json_data["chassis"]["fan_drawers"])
    actual_fan_number = 0
    for fan_name, status_info in fan_status_info.items():
        if "psu" not in fan_name:
            actual_fan_number += 1
        if status_info["Status"].lower() != "ok":
            err_msg = f"The status of {fan_name} is not ok"
            assert_failure_or_just_print_err(err_msg, is_in_deploy_image_flow)
            is_test_failed = True

    if actual_fan_number not in [fan_number, fan_number * 2]:
        err_msg = f"fan number is not correct. expected:{fan_number} or {fan_number * 2}, actual: {actual_fan_number}"
        assert_failure_or_just_print_err(err_msg, is_in_deploy_image_flow)
        is_test_failed = True

    write_failed_case_name(is_test_failed, request.node.name, is_in_deploy_image_flow)


@pytest.mark.flaky(reruns=30, reruns_delay=4)
@pytest.mark.sanity_checker_ci
@pytest.mark.sanity_checker_common
def test_more_then_2_fan_status_wrong_check(topology_obj):
    """
    This test is verify more than 2 fan status are not ok
    If case fail, the consequent regression steps will be stopped by mars
    """
    fan_status_info = topology_obj.players['dut']['cli'].chassis.show_platform_fan()
    broken_fan_number = 0
    fail_case_threshold_for_broken_fan_number = 2
    for fan_name, status_info in fan_status_info.items():
        if status_info["Status"].lower() != "ok":
            broken_fan_number += 1
    logger.info(f"broken fan number is {broken_fan_number}")
    assert broken_fan_number < fail_case_threshold_for_broken_fan_number, \
        f"The status of {broken_fan_number} fan are not ok "


@pytest.mark.flaky(reruns=30, reruns_delay=4)
@pytest.mark.sanity_checker_ci
@pytest.mark.sanity_checker_common
def test_psu_status_check(platform_params, topology_obj, platform_json_data, request, is_in_deploy_image_flow):
    """
    This test is verify the psu status is ok or not
    If case fail, we will raise the failed case information in the allure report and disable bug handler tool
    """
    is_test_failed = False
    psu_status_info = topology_obj.players['dut']['cli'].chassis.show_platform_psu_status()
    psu_number = len(platform_json_data["chassis"]["psus"])
    actual_psu_number = len(psu_status_info.keys())

    if actual_psu_number != psu_number:
        err_msg = f"psu number is correct.Expected: {psu_number}, actual: {actual_psu_number}"
        assert_failure_or_just_print_err(err_msg, is_in_deploy_image_flow)
        is_test_failed = True

    for psu_name, status_info in psu_status_info.items():
        if status_info["Status"].lower() != "ok":
            err_msg = f"The status of {psu_name} is not ok"
            assert_failure_or_just_print_err(err_msg, is_in_deploy_image_flow)
            is_test_failed = True

    write_failed_case_name(is_test_failed, request.node.name, is_in_deploy_image_flow)


@pytest.mark.sanity_checker_common
def test_core_dump_file_in_var_core_check(engines, request, is_in_deploy_image_flow):
    """
    This test is verify if the folder of /var/core has the core dump file, if yes fail case
    If case fail, we will raise the failed case information in the allure report and disable bug handler tool
    """
    is_test_failed = False
    var_core_data = engines.dut.run_cmd("ls /var/core")

    if var_core_data:
        err_msg = f"/var/core folder has core dump file: {var_core_data}"
        assert_failure_or_just_print_err(err_msg, is_in_deploy_image_flow)
        is_test_failed = True

    write_failed_case_name(is_test_failed, request.node.name, is_in_deploy_image_flow)


def get_info_about_current_components_version_dict(engine):
    """
    Get dictionary with component name as key and version as value
    :param engine: dut engine
    :return: dictionary with component name as key and version as value
    """

    fwutil_show_status_output = engine.run_cmd('sudo fwutil show status')
    fwutil_show_status_dict = generic_sonic_output_parser(fwutil_show_status_output)
    component_names_list = fwutil_show_status_dict[0]['Component']
    component_versions_list = fwutil_show_status_dict[0]['Version']
    component_versions_dict = {}
    for component, version in zip(component_names_list, component_versions_list):
        component_versions_dict[component] = version

    return component_versions_dict


def read_csv_file(csv_file):
    with open(csv_file) as csv_file_object:
        reader = csv.DictReader(csv_file_object)
        return [row for row in reader]


def check_one_dut_to_fanout_cable_connection(cli_object, dut_engine):
    dut_name = dut_engine.run_cmd("hostname")
    hwsku = cli_object.chassis.get_platform_hwsku()
    dut_fanout_link_file = os.path.join(CURRENT_PATH,
                                        f"../../../../ansible/files/hwsku_vars/{dut_name}_setup/{hwsku}/sonic_nvidia_links.csv")
    dut_fanout_link_data = read_csv_file(dut_fanout_link_file)
    logger.info(f"dut_fanout_link_data:\n {dut_fanout_link_data}")

    interface_status_dict = cli_object.interface.parse_interfaces_status()
    logger.info(f"interface_status_dict:\n {interface_status_dict}")

    map_dut_oper_up_interface_and_fanout_interface = {}
    for one_dut_fanout_link in dut_fanout_link_data:
        if one_dut_fanout_link["StartDevice"] != dut_name:
            continue
        dut_port = one_dut_fanout_link["StartPort"]
        if dut_port.startswith("Ethernet") and dut_port in interface_status_dict and \
                interface_status_dict.get(dut_port, "").get("Oper", "down") == "up":
            map_dut_oper_up_interface_and_fanout_interface[dut_port] = one_dut_fanout_link["EndPort"]

    logger.info(f"dut port to fanout port map: {map_dut_oper_up_interface_and_fanout_interface}")
    assert map_dut_oper_up_interface_and_fanout_interface, "Not find any port connecting from dut to fanout"

    check_lldp_info_dut_to_fanout(dut_engine, map_dut_oper_up_interface_and_fanout_interface)


@retry(Exception, tries=10, delay=5)
def check_lldp_info_dut_to_fanout(dut_engine, map_dut_oper_up_interface_and_fanout_interface):
    lldp_table_res = dut_engine.run_cmd("show lldp table")
    lldp_table_list = generic_sonic_output_parser(lldp_table_res,
                                                  headers_ofset=1,
                                                  len_ofset=2,
                                                  data_ofset_from_start=3,
                                                  data_ofset_from_end=-2,
                                                  column_ofset=2,
                                                  )
    logger.info(f"lldp_table_list:\n {lldp_table_list}")

    def _look_up_matched_lldp_info(dut_interface, fanout_interface):
        for one_lldp_info in lldp_table_list:
            if dut_interface == one_lldp_info["LocalPort"] and (
                    fanout_interface.split(" ")[-1] in one_lldp_info["RemotePortID"] or
                    fanout_interface == one_lldp_info["RemotePortDescr"]):
                return True
        assert False, f"Not find the lldp info for dut port {dut_interface} and  fanout port {fanout_interface}. " \
            f"llp info:{one_lldp_info} Please check the cable connection of the two ports"

    for dut_interface, fanout_interface in map_dut_oper_up_interface_and_fanout_interface.items():
        _look_up_matched_lldp_info(dut_interface, fanout_interface)


@retry(Exception, tries=15, delay=5)
def check_port_oper_up_on_admin_up(dut_topology_obj):
    logger.info("Check the oper status is up when the corresponding admin status is up")
    with allure.step(f'check ports are up'):
        port_status = dut_topology_obj.interface.parse_interfaces_status()
        for port, status in port_status.items():
            if status["Admin"] == "up":
                assert status["Oper"] == 'up', f"{port} is not up"


def assert_failure_or_just_print_err(print_msg, is_in_deploy_image_flow):
    if is_in_deploy_image_flow:
        logger.error(print_msg)
    else:
        assert False, print_msg


def write_failed_case_name(is_test_failed, case_name, is_in_deploy_image_flow):
    if is_test_failed and is_in_deploy_image_flow:
        logger.info(f"write test name {case_name} to file")
        write_failed_sanity_checker_cases_to_file([f"{case_name} "])

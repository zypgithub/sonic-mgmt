import logging
import os
import random
import re
import string
import subprocess
import time

from retry import retry

import ngts.tools.test_utils.allure_utils as allure
from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from infra.tools.linux_tools.linux_tools import scp_file
from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import HealthConsts, NvosConst, DatabaseConst, SystemConsts, TestFlowType
from ngts.nvos_tools.ib.InterfaceConfiguration.MgmtPort import MgmtPort
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.Tools import Tools
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.general.security.certificate.CertInfo import CertInfo
from ngts.tests_nvos.general.security.certificate.constants import TestCert
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import CERTIFICATE, \
    DEFAULT_CERTIFICATE, GnmicErr
from ngts.tests_nvos.system.gnmi.constants import DUT_GNMI_CERTS_DIR, DOCKER_CERTS_DIR, GnmiMode, \
    GrpcMsg, SERVER_REFLECTION_SUBSCRIBE_RESPONSE
from ngts.tools.test_utils.nvos_general_utils import generate_scp_uri_using_player

logger = logging.getLogger()


def validate_memory_and_cpu_utilization():
    system = System()
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.show("memory")).get_returned_value()
    memory_util = output_dictionary[SystemConsts.MEMORY_PHYSICAL_KEY]["utilization"]
    assert SystemConsts.MEMORY_PERCENT_THRESH_MIN < memory_util < SystemConsts.MEMORY_PERCENT_THRESH_MAX, \
        "Physical utilization percentage is out of range"
    output_dictionary = OutputParsingTool.parse_json_str_to_dictionary(system.show("cpu")).get_returned_value()
    cpu_utilization = output_dictionary[SystemConsts.CPU_UTILIZATION_KEY]
    logger.info(f"cpu utilization: {cpu_utilization}")
    assert cpu_utilization < SystemConsts.CPU_PERCENT_THRESH_MAX, \
        "CPU utilization: {actual}% is higher than the maximum limit of: {expected}%" \
        "".format(actual=cpu_utilization, expected=SystemConsts.CPU_PERCENT_THRESH_MAX)


def run_gnmi_client_in_the_background(target_ip, xpath, device):
    prefix_and_path = xpath.rsplit("/", 1)
    command = f"gnmic -a {target_ip} --port {GnmiConsts.GNMI_DEFAULT_PORT} --skip-verify subscribe " \
        f"--prefix '{prefix_and_path[0]}' --path '{prefix_and_path[1]}' --target netq " \
        f"-u {device.default_username} -p {device.default_password} --format flat"
    # Use the subprocess.Popen function to run the command in the background
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               preexec_fn=os.setsid)
    return process


def gnmi_basic_flow(engines, mode='', ipv6=False, mgmt_port_name='eth0'):
    """
    Check gnmi basic flow: show command , disable and enable commands, validate stream updates to gnmi-client.
        Test flow:
            1. validate gnmi-server is running
            2. validate health status is OK
            3. change port description
            5. validate gnmi-server stream updates
            6. Disable gnmi-server
            7. validate gnmi-server is not running
            8. validate health status is OK
            9. enable gnmi-server
            10. validate gnmi-server is running
            11. validate gnmi-server stream updates
    """
    system = System()
    gnmi_server_obj = system.gnmi_server
    target_ip = MgmtPort(mgmt_port_name).interface.get_ipv6_address() if ipv6 else engines.dut.ip
    validate_gnmi_is_running_and_stream_updates(system, gnmi_server_obj, engines, target_ip, mode=mode)

    with allure.step('Disable gnmi'):
        gnmi_server_obj.disable_gnmi_server()
        validate_gnmi_disabled_and_not_running(gnmi_server_obj, engines)
        validate_gnmi_server_in_health_issues(system, expected_gnmi_health_issue=False)

    with allure.step('Enable gnmi'):
        gnmi_server_obj.enable_gnmi_server()
        validate_gnmi_is_running_and_stream_updates(system, gnmi_server_obj, engines, target_ip, mode=mode)


def validate_gnmi_is_running_and_stream_updates(system, gnmi_server_obj, engines, target_ip, mode='', username='',
                                                password=''):
    with allure.step('Validate gnmi is running and stream updates'):
        validate_gnmi_enabled_and_running(gnmi_server_obj, engines)
        validate_gnmi_server_in_health_issues(system, expected_gnmi_health_issue=False)
        port_description = Tools.RandomizationTool.get_random_string(7)
        change_port_description_and_validate_gnmi_updates(engines, port_description=port_description,
                                                          target_ip=target_ip, mode=mode, username=username,
                                                          password=password)


@retry(Exception, tries=6, delay=2)
def validate_gnmi_server_docker_state(engines, should_run=True):
    cmd_output = engines.dut.run_cmd('docker ps |grep {}'.format(GnmiConsts.GNMI_DOCKER))
    should_run_str = '' if should_run else 'not'
    is_running_str = '' if cmd_output else 'not'
    assert bool(cmd_output) == should_run, f"The gnmi-server docker is {is_running_str} running, " \
        f"but we expect it {should_run_str} to run"


def validate_show_gnmi(gnmi_server_obj, engines, gnmi_state=GnmiConsts.GNMI_STATE_ENABLED,
                       gnmi_is_running=GnmiConsts.GNMI_IS_RUNNING):
    gnmi_server_obj.compare_show_gnmi_output(expected={GnmiConsts.GNMI_STATE_FIELD: gnmi_state,
                                                       GnmiConsts.GNMI_IS_RUNNING_FIELD: gnmi_is_running})
    should_run = gnmi_is_running == GnmiConsts.GNMI_IS_RUNNING
    validate_gnmi_server_docker_state(engines, should_run=should_run)


def validate_gnmi_enabled_and_running(gnmi_server_obj, engines):
    validate_show_gnmi(gnmi_server_obj, engines, gnmi_state=GnmiConsts.GNMI_STATE_ENABLED,
                       gnmi_is_running=GnmiConsts.GNMI_IS_RUNNING)


def validate_gnmi_disabled_and_not_running(gnmi_server_obj, engines):
    validate_show_gnmi(gnmi_server_obj, engines, gnmi_state=GnmiConsts.GNMI_STATE_DISABLED,
                       gnmi_is_running=GnmiConsts.GNMI_IS_NOT_RUNNING)


def run_gnmi_client_and_parse_output(engines, devices, xpath, target_ip, target_port=GnmiConsts.GNMI_DEFAULT_PORT,
                                     mode='', username='', password=''):
    username = username or devices.dut.default_username
    password = password or devices.dut.default_password
    with allure.step("run gnmi-client and parse output"):
        sonic_mgmt_engine = engines.sonic_mgmt
        prefix_and_path = xpath.rsplit("/", 1)
        mode_flag = f"--mode {mode}" if mode else ''
        cmd = f"gnmic -a {target_ip} --port {target_port} --skip-verify subscribe --prefix '{prefix_and_path[0]}'" \
            f" --path '{prefix_and_path[1]}' --target netq -u {username} " \
            f"-p {password} {mode_flag} --format flat"
        logger.info(f"run on the sonic mgmt docker {sonic_mgmt_engine.ip}: {cmd}")
        if "poll" == mode:
            gnmi_client_output = sonic_mgmt_engine.run_cmd_set([cmd, '\n', '\n', '\x03', '\x03'],
                                                               patterns_list=["select target to poll:",
                                                                              "select subscription to poll:",
                                                                              "failed selecting target to poll:"])
            gnmi_client_output = re.findall(f"{re.escape(xpath)}:\\s+\\w+", gnmi_client_output)[0]
        elif "once" == mode:
            gnmi_client_output = sonic_mgmt_engine.run_cmd(cmd)
            gnmi_client_output = re.sub(r'(\\["\\n]+|\s+)', '', gnmi_client_output.split(":")[-1])
        else:
            gnmi_client_output = sonic_mgmt_engine.run_cmd_after_cmd([cmd, '\x03']).replace(cmd, '')
            gnmi_client_output = re.sub(r"\^C(.*\n.*)*", '', gnmi_client_output)
            gnmi_client_output = re.sub(r'(\\["\\n]+|\s+)', '', gnmi_client_output.split(":")[-1])

        gnmi_updates_dict = {}
        for item in gnmi_client_output.split('\n'):
            if item.strip():
                item_as_list = item.split(":")
                key = re.sub(r"\s+\[|\]", '', item_as_list[0])
                value = re.sub(r"\s|\r|\"", '', item_as_list[-1])
                gnmi_updates_dict.update({key: value})
        return gnmi_updates_dict


def change_port_description_and_validate_gnmi_updates(engines, port_description, target_ip, mode='', username='',
                                                      password=''):
    selected_port = Tools.RandomizationTool.select_random_port(requested_ports_state=None).returned_value
    selected_port.interface.set(NvosConst.DESCRIPTION, port_description, apply=True).verify_result()
    selected_port.update_output_dictionary()
    verify_description_value(selected_port.show_output_dictionary, port_description)

    devices = TestToolkit.devices

    xpath = f'interfaces/interface[name={selected_port.name}]/state/description'
    logger.info(f"sleep {GnmiConsts.SLEEP_TIME_FOR_UPDATE} sec until we start validate the gnmi stream")
    time.sleep(GnmiConsts.SLEEP_TIME_FOR_UPDATE)
    gnmi_stream_updates = run_gnmi_client_and_parse_output(engines, devices, xpath, target_ip, mode=mode,
                                                           username=username, password=password)
    assert port_description in list(gnmi_stream_updates.values()), \
        "we expect to see the new port description in the gnmi-client output but we didn't.\n" \
        f"port description: {port_description}\n" \
        f"but got: {list(gnmi_stream_updates.values())}"


@retry(Exception, tries=3, delay=3)
def validate_gnmi_server_in_health_issues(system, expected_gnmi_health_issue):
    health_issues = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).get_returned_value()[
        HealthConsts.ISSUES]
    error_msg = "gnmi-server is {} in the health issues".format("not" if expected_gnmi_health_issue else "")
    if expected_gnmi_health_issue:
        assert GnmiConsts.GNMI_DOCKER in list(health_issues.keys()), error_msg
    else:
        assert GnmiConsts.GNMI_DOCKER not in list(health_issues.keys()), error_msg


def create_gnmi_and_redis_cmd_dict(redis_cmd_db_num, redis_cmd_table, redis_cmd_key, xpath_gnmi_cmd,
                                   comparison_dict=None):
    gnmi_cmd_dict = {GnmiConsts.REDIS_CMD_DB_NAME: DatabaseConst.REDIS_DB_NUM_TO_NAME[redis_cmd_db_num],
                     GnmiConsts.REDIS_CMD_TABLE_NAME: redis_cmd_table,
                     GnmiConsts.REDIS_CMD_PARAM: redis_cmd_key,
                     GnmiConsts.XPATH_KEY: xpath_gnmi_cmd,
                     GnmiConsts.COMPARISON_KEY: comparison_dict}
    return gnmi_cmd_dict


def get_infiniband_name_from_port_name(engine, port_name):
    output = Tools.DatabaseTool.sonic_db_cli_hget(engine=engine, asic="", db_name=DatabaseConst.APPL_DB_NAME,
                                                  db_config=f"\"ALIAS_PORT_MAP:{port_name}\"", param="name")
    # output = engine.run_cmd(f"redis-cli -n 0 HGET \"ALIAS_PORT_MAP:{port_name}\" \"name\"")
    infiniband_name = output.replace("\"", "")
    return infiniband_name


def get_port_oid_from_infiniband_port(engine, infiniband_port):
    output = Tools.DatabaseTool.sonic_db_cli_hget(engine=engine, asic="", db_name=DatabaseConst.COUNTERS_DB_NAME,
                                                  db_config="COUNTERS_PORT_NAME_MAP", param=str(infiniband_port))
    # output = engine.run_cmd(f"redis-cli -n 2 HGET \"COUNTERS_PORT_NAME_MAP\" \"{infiniband_port}\"")
    port_oid = output.replace("\"", "")
    return port_oid


def create_interface_state_commands_list(port_name, infiniband_name):
    state_xpath = "interfaces/interface[name={port_name}]/state/{field}"
    gnmi_list = [create_gnmi_and_redis_cmd_dict(4, f"IB_PORT|{infiniband_name}", "admin_status",
                                                state_xpath.format(port_name=port_name, field="admin-status")),
                 create_gnmi_and_redis_cmd_dict(4, f"IB_PORT|{infiniband_name}", "index",
                                                state_xpath.format(port_name=port_name, field="ifindex")),
                 create_gnmi_and_redis_cmd_dict(4, f"IB_PORT|{infiniband_name}", "description",
                                                state_xpath.format(port_name=port_name, field="description")),
                 create_gnmi_and_redis_cmd_dict(4, f"IB_PORT|{infiniband_name}", "admin_status",
                                                state_xpath.format(port_name=port_name, field="enabled"),
                                                comparison_dict={"up": "true", "down": "false"})]
    return gnmi_list


def create_platform_general_commands_list():
    usage_name = "USAGE"
    state_xpath = "components/platform-general/{field}"
    gnmi_list = [
        create_gnmi_and_redis_cmd_dict(6, f"DISK_INFO|{usage_name}", "disk_total_size",
                                       state_xpath.format(field="disk-total-size")),
        create_gnmi_and_redis_cmd_dict(6, f"DISK_INFO|{usage_name}", "disk_usage",
                                       state_xpath.format(field="disk-used")),
        create_gnmi_and_redis_cmd_dict(6, f"RAM_INFO|{usage_name}", "memory_total_size",
                                       state_xpath.format(field="memory-total-size")),
        create_gnmi_and_redis_cmd_dict(6, f"RAM_INFO|{usage_name}", "memory_usage",
                                       state_xpath.format(field="memory-used")),
    ]
    return gnmi_list


def create_gnmi_counter_list(port_name, port_oid):
    state_xpath = "interfaces/interface[name={port_name}]/state/counters/{field}"
    gnmi_list = [create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_IF_IN_PKTS_EXT",
                                                state_xpath.format(port_name=port_name, field="in-pkts")),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_IF_OUT_PKTS_EXT",
                                                state_xpath.format(port_name=port_name, field="out-pkts")),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_PC_ERR_RCV_F",
                                                state_xpath.format(port_name=port_name, field="in-errors")),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_ERR_XMTCONSTR_F",
                                                state_xpath.format(port_name=port_name, field="out-errors")),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_IF_IN_OCTETS_EXT",
                                                state_xpath.format(port_name=port_name, field="in-octets")),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_IF_OUT_OCTETS_EXT",
                                                state_xpath.format(port_name=port_name, field="out-octets")),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_IF_IN_PKTS_EXT",
                                                state_xpath.format(port_name=port_name, field="in-pkts")),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_IF_IN_PKTS_EXT",
                                                state_xpath.format(port_name=port_name, field="in-pkts")),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_IF_IN_PKTS_EXT",
                                                state_xpath.format(port_name=port_name, field="in-pkts"))]
    return gnmi_list


def create_gnmi_infiniband_list(port_name, port_oid, infiniband_name):
    state_xpath = "interfaces/interface[name={port_name}]/infiniband/state/{field}"
    gnmi_list = [create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_LOGICAL_STATE",
                                                state_xpath.format(port_name=port_name, field="logical-port-state"),
                                                comparison_dict={"1": "Down",
                                                                 "2": "Initialize",
                                                                 "3": "Armed",
                                                                 "4": "Active"}),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_PHYSICAL_STATE",
                                                state_xpath.format(port_name=port_name, field="physical-port-state"),
                                                comparison_dict={"1": "Sleep",
                                                                 "2": "Polling",
                                                                 "3": "Disabled",
                                                                 "4": "PortConfigurationTraining",
                                                                 "5": "LINK_UP",
                                                                 "6": "LinkErrorRecovery",
                                                                 "7": "Phy Test",
                                                                 "8": "Disabled By Chassis Manager"}),
                 create_gnmi_and_redis_cmd_dict(6, f"IB_PORT_TABLE|{infiniband_name}", "speed_admin",
                                                state_xpath.format(port_name=port_name, field="supported-ib-speeds")),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_SPEED_OPER",
                                                state_xpath.format(port_name=port_name, field="speed")),
                 create_gnmi_and_redis_cmd_dict(4, f"IB_PORT|{infiniband_name}", "auto_neg",
                                                state_xpath.format(port_name=port_name, field="speed-negotiate"),
                                                comparison_dict={'on': 'true', 'off': 'false'}),
                 create_gnmi_and_redis_cmd_dict(6, f"IB_PORT_TABLE|{infiniband_name}", "lanes_admin",
                                                state_xpath.format(port_name=port_name, field="supported-widths"),
                                                comparison_dict={"1": "1X",
                                                                 "2": "2X",
                                                                 "3": "1X_2X",
                                                                 "4": "4X",
                                                                 "5": "1X_4X",
                                                                 "6": "2X_4X",
                                                                 "7": "1X_2X_4X"}),
                 create_gnmi_and_redis_cmd_dict(6, f"IB_PORT_TABLE|{infiniband_name}", "mtu_max",
                                                state_xpath.format(port_name=port_name, field="max-supported-MTUs")),
                 create_gnmi_and_redis_cmd_dict(2, f"COUNTERS:{port_oid}", "SAI_PORT_STAT_INFINIBAND_MTU_OPER",
                                                state_xpath.format(port_name=port_name, field="mtu")),
                 create_gnmi_and_redis_cmd_dict(6, f"IB_PORT_TABLE|{infiniband_name}", "ib_subnet",
                                                state_xpath.format(port_name=port_name, field="ib-Subnet"),
                                                comparison_dict={"0": "infiniband-default", "1": "infiniband-1"}),
                 create_gnmi_and_redis_cmd_dict(6, f"IB_PORT_TABLE|{infiniband_name}", "vl_admin",
                                                state_xpath.format(port_name=port_name, field="vl-capabilities"),
                                                comparison_dict={"1": "VL0",
                                                                 "2": "VL0-VL1",
                                                                 "3": "VL0-VL2",
                                                                 "4": "VL0-VL3",
                                                                 "5": "VL0-VL4",
                                                                 "6": "VL0-VL5",
                                                                 "7": "VL0-VL6",
                                                                 "8": "VL0-VL7",
                                                                 "15": "VL0-VL14"})]
    return gnmi_list


@retry(AssertionError, tries=3, delay=10)
def validate_redis_cli_and_gnmi_commands_results(engines, devices, gnmi_list, allowed_range_in_bytes=None):
    sonic_mgmt_engine = engines.sonic_mgmt
    for command in gnmi_list:
        prefix_and_path = command[GnmiConsts.XPATH_KEY].rsplit("/", 1)
        cmd = f"gnmic -a {engines.dut.ip} --port {GnmiConsts.GNMI_DEFAULT_PORT} --skip-verify subscribe " \
            f"--prefix '{prefix_and_path[0]}' --path '{prefix_and_path[1]}' --target netq " \
            f"-u {devices.dut.default_username} -p {devices.dut.default_password} --mode once --format flat"
        logger.info(f"run on the sonic mgmt docker {sonic_mgmt_engine.ip}: {cmd}")
        gnmi_client_output = sonic_mgmt_engine.run_cmd(cmd)
        gnmi_client_output = re.sub(r'(\\["\\n]+|\s+)', '', gnmi_client_output.split(":")[-1])
        redis_output = Tools.DatabaseTool.sonic_db_cli_hget(engine=engines.dut, asic="",
                                                            db_name=command[GnmiConsts.REDIS_CMD_DB_NAME],
                                                            db_config=f"\"{command[GnmiConsts.REDIS_CMD_TABLE_NAME]}\"",
                                                            param=command[GnmiConsts.REDIS_CMD_PARAM])
        if ',' in redis_output:
            redis_output = str(sorted(redis_output.split(',')))
            gnmi_client_output = str(sorted(gnmi_client_output.split(',')))
        if command[GnmiConsts.COMPARISON_KEY]:
            Tools.ValidationTool.compare_values(gnmi_client_output.lower(), command[GnmiConsts.COMPARISON_KEY][redis_output].lower()).verify_result()
        elif allowed_range_in_bytes is not None:
            result = abs(int(gnmi_client_output) - int(redis_output))
            assert 0 <= result <= allowed_range_in_bytes, (
                f"gNMI output: {gnmi_client_output} is not within {allowed_range_in_bytes} to "
                f"redis output:{redis_output} for field: {prefix_and_path[1]}")
        else:
            Tools.ValidationTool.compare_values(gnmi_client_output.lower(), redis_output.lower()).verify_result()


def verify_description_value(output, expected_description):
    Tools.ValidationTool.verify_field_value_in_output(output, NvosConst.DESCRIPTION,
                                                      expected_description).verify_result()


def change_interface_description(selected_port, new_description: str = ''):
    rand_str = new_description or ''.join(random.choice(string.ascii_lowercase) for _ in range(20))
    selected_port.interface.set(NvosConst.DESCRIPTION, rand_str, apply=True).verify_result()
    time.sleep(GnmiConsts.SLEEP_TIME_FOR_UPDATE)
    return rand_str


def load_certificate_into_gnmi(engine: LinuxSshEngine, cert: CertInfo):
    with allure.step('make dedicated dir in switch'):
        engine.run_cmd(f'mkdir -p {DUT_GNMI_CERTS_DIR}')
    with allure.step('scp cert to switch'):
        with allure.step(f'copy {cert.private_filename}'):
            scp_file(engine, f'{cert.private}', f'{DUT_GNMI_CERTS_DIR}/{cert.private_filename}')
        with allure.step(f'copy {cert.public_filename}'):
            scp_file(engine, f'{cert.public}', f'{DUT_GNMI_CERTS_DIR}/{cert.public_filename}')
    with allure.step('copy cert into gnmi docker'):
        engine.run_cmd(
            f'docker cp {DUT_GNMI_CERTS_DIR}/{cert.private_filename} {GnmiConsts.GNMI_DOCKER}:{DOCKER_CERTS_DIR}/{cert.private_filename}')
        engine.run_cmd(
            f'docker cp {DUT_GNMI_CERTS_DIR}/{cert.public_filename} {GnmiConsts.GNMI_DOCKER}:{DOCKER_CERTS_DIR}/{cert.public_filename}')
    with allure.step('restart gnmi'):
        system = System()
        system.gnmi_server.disable_gnmi_server()
        system.gnmi_server.enable_gnmi_server()


def verify_msg_existence_in_out_or_err(msg: str, should_be_in: bool, out: str, err: str = None):
    msg_in_out = msg in out
    msg_in_err = msg in err if err else False
    assert (msg_in_out or msg_in_err) == should_be_in, ((f'"{msg}" unexpectedly was{" not" if should_be_in else ""} '
                                                         f'found in out{"/err" if err is not None else ""}.\nout: {out}') +
                                                        (f'\nerr: {err}' if err is not None else ''))


def verify_msg_not_in_out_or_err(msg: str, out: str, err: str = None):
    verify_msg_existence_in_out_or_err(msg, False, out, err)


def verify_msg_in_out_or_err(msg: str, out: str, err: str = None):
    verify_msg_existence_in_out_or_err(msg, True, out, err)


def verify_gnmi_client(test_flow, server_host, server_port, username, password, skip_cert_verify: bool,
                       err_msg_to_check: str, port_to_change=None, cacert=''):
    assert cacert or skip_cert_verify, 'given cacert can not be empty when skip_cert_verify is False'

    log_msg = (f'verify gnmi client with{"" if skip_cert_verify else "out"} skip-verify '
               f'and credentials: {username} / {password}')
    selected_port = port_to_change or Tools.RandomizationTool.select_random_port(
        requested_ports_state=None).returned_value

    with allure.step('create gnmi client'):
        client = GnmiClient(server_host, server_port, username, password, cacert=cacert, cmd_time=10)
    with allure.step(f'change description of interface: "{selected_port.name}"'):
        new_description = change_interface_description(selected_port)
    if test_flow == TestFlowType.GOOD_FLOW:
        with allure.step(f'good-flow: {log_msg}'):
            with allure.step('verify using capabilities command'):
                out, err = client.gnmic_capabilities(skip_cert_verify=skip_cert_verify)
                verify_msg_not_in_out_or_err(err_msg_to_check, out, err)
            with allure.step('verify using subscribe command'):
                out, err = client.gnmic_subscribe_interface(GnmiMode.ONCE, selected_port.name,
                                                            skip_cert_verify=skip_cert_verify)
                verify_msg_in_out_or_err(new_description, out)
                verify_msg_not_in_out_or_err(err_msg_to_check, out, err)
            with allure.step('verify using reflection command'):
                services = [SERVER_REFLECTION_SUBSCRIBE_RESPONSE]
                verify_server_reflection(test_flow, client, skip_cert_verify, err_msg_to_check, services)
    else:
        with allure.step(f'bad-flow: {log_msg}'):
            with allure.step('verify using capabilities command'):
                out, err = client.gnmic_capabilities(skip_cert_verify=skip_cert_verify)
                verify_msg_in_out_or_err(err_msg_to_check, out, err)
            with allure.step('verify using subscribe command'):
                out, err = client.gnmic_subscribe_interface(GnmiMode.ONCE, selected_port.name,
                                                            skip_cert_verify=skip_cert_verify)
                verify_msg_not_in_out_or_err(new_description, out)
                verify_msg_in_out_or_err(err_msg_to_check, out, err)
            with allure.step('verify using reflection command'):
                verify_server_reflection(test_flow, client, skip_cert_verify, err_msg_to_check)


def verify_server_reflection(test_flow, client, skip_cert_verify, err_msg_to_check, services=None):
    out_reflect, err_reflect = client.grpcurl_describe(skip_cert_verify=skip_cert_verify)
    if test_flow == TestFlowType.GOOD_FLOW:
        verify_msg_in_out_or_err(GrpcMsg.MSG_SERVER_REFLECT, out_reflect)
        verify_msg_not_in_out_or_err(err_msg_to_check, out_reflect, err_reflect)
        for service in services:
            out_reflect, err_reflect = client.grpcurl_describe(service=service, skip_cert_verify=skip_cert_verify)
            verify_msg_in_out_or_err(GrpcMsg.ALL_MSGS[service], out_reflect)
            verify_msg_not_in_out_or_err(err_msg_to_check, out_reflect, err_reflect)
    else:
        verify_msg_not_in_out_or_err(GrpcMsg.MSG_SERVER_REFLECT, out_reflect)
        verify_msg_in_out_or_err(err_msg_to_check, out_reflect, err_reflect)


def factory_reset_gnmi_check():
    cert = TestCert.cert_valid_1
    system = System()
    dut_engine = TestToolkit.engines.dut
    with allure.step(f'before factory reset - import and load certificate "{cert.name}" to gnmi'):
        with allure.step(f'import cert {cert.name}'):
            system.security.certificate.cert_id[cert.name].action_import(
                uri_bundle=generate_scp_uri_using_player(dut_engine, cert.p12_bundle),
                passphrase=cert.p12_password).verify_result()
        with allure.step(f'set certificate "{cert.name}" to gnmi'):
            system.gnmi_server.set(CERTIFICATE, cert.name, apply=True).verify_result()
    yield
    with allure.step(f'after factory reset - verify default gnmi certificate'):
        out = OutputParsingTool.parse_json_str_to_dictionary(system.gnmi_server.show()).get_returned_value()
        assert out[CERTIFICATE] == DEFAULT_CERTIFICATE, (f'value of field "{CERTIFICATE}" not as expected (default)\n'
                                                         f'expected (default): {DEFAULT_CERTIFICATE}\n'
                                                         f'actual: {out[CERTIFICATE]}')
    with allure.step('after factory reset - verify client cannot request using the certificate'):
        verify_gnmi_client(TestFlowType.BAD_FLOW, cert.ip or cert.dn, GnmiConsts.GNMI_DEFAULT_PORT,
                           dut_engine.username, dut_engine.password, False, GnmicErr.CERT_VERIFY_FAIL,
                           cacert=cert.cacert)
    yield  # to prevent StopIteration on the 2nd next() call


factory_reset_gnmi_checker = factory_reset_gnmi_check()  # generator

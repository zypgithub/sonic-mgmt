import random
import time

import pytest

from infra.tools.validations.traffic_validations.port_check.port_checker import check_port_status_till_alive
from ngts.nvos_constants.constants_nvos import SystemConsts, NvosConst, TcpDumpConsts, ApiType
from ngts.nvos_tools.ib.InterfaceConfiguration.Interface import Interface
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.infra.IpTool import IpTool
from ngts.nvos_tools.infra.LLDPTool import LLDPTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_lldp_enabled(engines, devices, test_api):
    """
    Verify lldp functionality is working by default.

    1. Verify lldp is running.
    2. Verify lldp is sending and receiving frames.
    """
    TestToolkit.tested_api = test_api
    system = System()
    lldp = system.lldp
    _verify_lldp_is_sending_frames(lldp=lldp, engine=engines.dut, device=devices.dut)


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
def test_lldp_show(engines, devices):
    """
    Verify lldp show is working as expected.

    1. Verify lldp is running.
    2. Verify interface lldp contains neighbor field.
    """
    system = System()
    lldp = system.lldp

    _verify_lldp_running(lldp, engine=engines.dut)
    lldp_output = OutputParsingTool.parse_json_str_to_dictionary(Interface(parent_obj=None).lldp.show()).get_returned_value()
    for interface_name in devices.dut.get_mgmt_ports():
        ValidationTool.verify_field_exist_in_json_output(lldp_output,
                                                         [interface_name]).verify_result()
        eth_output = lldp_output[interface_name]
        ValidationTool.verify_field_exist_in_json_output(eth_output,
                                                         [SystemConsts.LLDP_LLDP]).verify_result()
        eth_lldp_output = eth_output[SystemConsts.LLDP_LLDP]
        ValidationTool.verify_field_exist_in_json_output(eth_lldp_output,
                                                         [SystemConsts.LLDP_NEIGHBOR]).verify_result()


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_lldp_disabled(engines, devices, test_api):
    """
    Check that lldp is disabled correctly.

    1. Verify lldp is running.
    2. Disable lldp state.
    3. Verify lldp is not running and not sending any frames.
    4. Verify neighbors table is empty
    5. Enable back lldp and verify it is working.
    """
    TestToolkit.tested_api = test_api
    system = System()
    lldp = system.lldp

    _verify_lldp_is_sending_frames(lldp, engine=engines.dut, device=devices.dut)

    try:
        _set_lldp_state(lldp, key=SystemConsts.STATE, val=NvosConst.DISABLED)
        _verify_lldp_not_running(lldp, engine=engines.dut, device=devices.dut)

    finally:
        _set_lldp_state(lldp, key=SystemConsts.STATE, val=NvosConst.ENABLED)
        _verify_lldp_is_sending_frames(lldp, engine=engines.dut, device=devices.dut)


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_lldp_with_custom_interval(engines, devices, test_api):
    """
    Check that lldp frames have correct data in them.
    1. Verify lldp is running with custom interval.
    2. Verify lldp information is the same as in tcpdump.
    """
    TestToolkit.tested_api = test_api

    system = System()
    lldp = system.lldp
    cli_output = lldp.parsed_show()
    default_interval = cli_output[SystemConsts.LLDP_INTERVAL]

    _verify_lldp_running(lldp, engine=engines.dut)

    interval = 5

    try:
        system_output = OutputParsingTool.parse_json_str_to_dictionary(system.show()).get_returned_value()
        _set_lldp_state(lldp, SystemConsts.LLDP_INTERVAL, interval)

        _verify_cli_output_with_dump_output(engines.dut, devices.dut, lldp, system_output)
    finally:
        _set_lldp_state(lldp, SystemConsts.LLDP_INTERVAL, default_interval)


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_lldp_custom_hostname(engines, devices, test_api):
    """
    Check that lldp frames have correct custom hostname.
    1. Verify lldp is running.
    2. Change default hostname to custom.
    3. Verify lldp is sending correct hostname.
    4. Change hostname back to default.
    """
    TestToolkit.tested_api = test_api
    system = System()
    _verify_lldp_running(system.lldp, engine=engines.dut)

    custom_hostname = "lldp-host"
    with allure.step("Get current system hostname"):
        system_dict = OutputParsingTool.parse_json_str_to_dictionary(
            system.show()).get_returned_value()
        default_hostname = system_dict[SystemConsts.HOSTNAME]
    try:
        system.set(SystemConsts.HOSTNAME, custom_hostname, apply=True, ask_for_confirmation=True).verify_result()
        with allure.step("Verify hostname in tcpdump"):
            lldp_dump = LLDPTool.get_lldp_frames(engine=engines.dut)
            lldp_dict = LLDPTool.parse_lldp_dump(lldp_dump)
            assert lldp_dict[
                TcpDumpConsts.LLDP_SYSTEM_NAME] == custom_hostname, f'The lldp {lldp_dict[TcpDumpConsts.LLDP_SYSTEM_NAME]} is not {custom_hostname}'
    finally:
        system.set(SystemConsts.HOSTNAME, default_hostname, apply=True, ask_for_confirmation=True).verify_result()


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_lldp_one_neighbor(engines, devices, test_api):
    """
    Check that interfaces have only one lldp neighbor.
    1. Verify lldp is running.
    2. For each mgmt interface verify it has only one neighbor.
    3. Verify neighbor's output is not empty
    """
    TestToolkit.tested_api = test_api
    system = System()
    _verify_lldp_running(system.lldp, engine=engines.dut)

    for interface_name in devices.dut.get_mgmt_ports():
        with allure.step(f"Verify {interface_name} has only one neighbor"):
            mgmt_interface = Port(name=interface_name)
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(
                mgmt_interface.interface.lldp.neighbor.show()).get_returned_value()
            neighbor_keys = list(output_dict.keys())
            assert len(neighbor_keys) == 1, "There is not only one neighbor"
        neighbor_id = neighbor_keys[0]

        with allure.step(f"Verify neighbor {neighbor_id} is not empty for {interface_name}"):
            neighbor_dict = OutputParsingTool.parse_json_str_to_dictionary(
                mgmt_interface.interface.lldp.neighbor.neighbor_id[neighbor_id].show())
            assert neighbor_dict, f"The neighbor {neighbor_id} is empty"


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_lldp_incorrect_values(engines, devices, test_api):
    """
    Check that lldp set commands are not working for values outside the range.
    1. Verify lldp is running.
    2. Try to set incorrect interval.
    3. Try to set incorrect multiplier.
    """
    TestToolkit.tested_api = test_api
    system = System()
    lldp = system.lldp

    _verify_lldp_running(lldp, engine=engines.dut)
    wrong_interval = 32769
    wrong_multiplier = 8193

    with allure.step(f"Verify can't set interval to {wrong_interval}"):
        lldp.set(SystemConsts.LLDP_INTERVAL, wrong_interval).verify_result(should_succeed=False)
    with allure.step(f"Verify can't set hold-multiplier to {wrong_multiplier}"):
        lldp.set(SystemConsts.LLDP_MULTIPLIER, wrong_multiplier).verify_result(should_succeed=False)

    max_allowed_ttl = 65535
    with allure.step(f"Generate random interval and multiplier, so ttl will exceed max allowed value of {max_allowed_ttl}"):
        while True:
            interval = random.randint(5, 32768)
            multiplier = random.randint(1, 8192)
            ttl = interval * multiplier
            if ttl > max_allowed_ttl:
                break

    with allure.step(f"Verify can't set {interval} * {multiplier} which exceeds TTL of {max_allowed_ttl}"):
        lldp.set(SystemConsts.LLDP_INTERVAL, interval).verify_result()
        lldp.set(SystemConsts.LLDP_MULTIPLIER, multiplier, apply=True).verify_result(should_succeed=False)
        lldp.unset(apply=True).verify_result()


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
def test_lldp_max_values(engines, devices):
    """
    Check that lldp set commands are working with max values
    1. Verify lldp is running.
    2. Set max interval and multiplier.
    3. Verify ttl.
    """
    system = System()
    lldp = system.lldp

    _verify_lldp_running(lldp, engine=engines.dut)
    max_interval = 13107  # Interval * multiplier should be less or equal to 65535
    max_multiplier = 5

    try:
        with allure.step(f"Verify lldp works with interval {max_interval}"):
            _set_lldp_state(lldp, SystemConsts.LLDP_INTERVAL, max_interval, apply=False)
        with allure.step(f"Verify lldp works with interval {max_multiplier}"):
            _set_lldp_state(lldp, SystemConsts.LLDP_MULTIPLIER, max_multiplier)

        with allure.step("Disable and enable lldp to get first frame instead of waiting forever"):
            _set_lldp_state(lldp, key=SystemConsts.STATE, val=NvosConst.DISABLED)
            # WA in order to get first lldp frame without waiting for long ttl
            _set_lldp_state(lldp, key=SystemConsts.STATE, val=NvosConst.ENABLED, sleep_time=0)

        with allure.step("Verify interval values"):
            lldp_dump = LLDPTool.get_lldp_frames(engine=engines.dut)
            lldp_dict = LLDPTool.parse_lldp_dump(lldp_dump)
            ttl = max_interval * max_multiplier
            assert int(lldp_dict[
                TcpDumpConsts.LLDP_TIME_TO_LIVE]) == ttl, 'The cli ttl does not match sent frame time to live'

    finally:
        with allure.step("Return to default lldp values"):
            lldp.unset(SystemConsts.LLDP_INTERVAL).verify_result()
            lldp.unset(SystemConsts.LLDP_MULTIPLIER).verify_result()
            lldp.unset(SystemConsts.STATE, apply=True).verify_result()
            _verify_lldp_running(lldp, engine=engines.dut)


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
def test_lldp_additional_ipv6(engines, devices, serial_engine):
    """
    Check that correct lldp frames sent all IpV6 addresses.
    1. Verify lldp is running.
    2. Add additional IpV6 address.
    3. Verify lldp frames contain this new IpV6 address.
    """
    system = System()
    engine = engines.dut
    _verify_lldp_running(system.lldp, engine=engine)

    for interface_name in devices.dut.get_mgmt_ports():
        mgmt_interface = Port(name=interface_name)

        try:
            ip_address_full = IpTool.select_random_ipv6_address().verify_result()  # 40c9:7735:e23d:dd2a:ca43:c5e9:682e:decb/114
            ip_address, prefix = ip_address_full.split("/")
            with allure.step(f"Set random ipv6 address {ip_address} for {interface_name}"):
                mgmt_interface.interface.ip.address.set(op_param_name=ip_address_full, apply=True,
                                                        ask_for_confirmation=True,
                                                        dut_engine=serial_engine).verify_result()
                check_port_status_till_alive(False, engine.ip, engine.ssh_port)

            with allure.step("Verify ipv6 address is in the lldp frame"):
                output = LLDPTool.get_lldp_frames(engine=serial_engine, interface=interface_name)
                assert ip_address in output, f"The ipv6 address {ip_address} is not in lldp frame"

        finally:
            mgmt_interface.interface.ip.address.unset(apply=True, dut_engine=serial_engine,
                                                      ask_for_confirmation=True).verify_result()


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
def test_lldp_interface_flapping(engines, devices, serial_engine):
    """
    Check that correct lldp frames are sent after interface flapping
    1. Verify lldp is running.
    2. Do interface flapping for each of mgmt ports.
    3. Verify lldp frames are sent and valid.
    """
    system = System()
    lldp = system.lldp
    _verify_lldp_running(lldp, engine=engines.dut)

    mgmt_ports = [Port(name=interface_name) for interface_name in devices.dut.get_mgmt_ports()]

    try:
        for _ in range(4):
            for mgmt_port in mgmt_ports:
                mgmt_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_DOWN, apply=True,
                                                   ask_for_confirmation=True, dut_engine=serial_engine).verify_result()

            serial_engine.run_cmd("nv config apply -y")

            for mgmt_port in mgmt_ports:
                mgmt_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_UP, apply=True,
                                                   ask_for_confirmation=True, dut_engine=serial_engine).verify_result()

            serial_engine.run_cmd("nv config apply -y")

        check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)

    finally:
        with allure.step("Verify ports are up after all the flapping test"):
            for mgmt_port in mgmt_ports:
                mgmt_port.interface.link.state.unset(apply=True, dut_engine=serial_engine, ask_for_confirmation=True).verify_result()
            check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)
            _verify_lldp_is_sending_frames(lldp=lldp, engine=engines.dut, device=devices.dut)


@pytest.mark.lldp
@pytest.mark.system
@pytest.mark.interface
def test_lldp_disable_dhcp(engines, devices, serial_engine):
    """
    Check that correct lldp sends mac address if dhcp is disabled.
    1. Verify lldp is running.
    2. Disable dhcp client
    3. Verify lldp frames do not contain ip addresses.
    4. Verify lldp frames contain mac address.
    """
    system = System()
    _verify_lldp_running(system.lldp, engine=engines.dut)

    with allure.step(f"Testing all mgmt ports"):
        for interface_name in devices.dut.get_mgmt_ports():
            mgmt_interface = Port(name=interface_name)
            with allure.independent_step(f"Testing {interface_name}"):
                try:
                    with allure.step("Get ip addresses"):
                        ip_addresses_dict = mgmt_interface.interface.ip.address.parse_show(dut_engine=serial_engine)
                        ip_addresses = list(ip_addresses_dict.keys())

                    with allure.step(f"Disable dhcp-client for {interface_name}"):
                        mgmt_interface.interface.ip.dhcp_client.set(SystemConsts.STATE, NvosConst.DISABLED, apply=True,
                                                                    ask_for_confirmation=True, dut_engine=serial_engine).verify_result()
                        check_port_status_till_alive(False, engines.dut.ip, engines.dut.ssh_port)

                    with allure.step("Verify lldp frames do not contain hostname"):
                        LLDPTool.verify_mgmt_ports_are_up(engine=serial_engine)
                        output = LLDPTool.get_lldp_frames(engine=serial_engine, interface=interface_name)
                        interface_link = OutputParsingTool.parse_json_str_to_dictionary(mgmt_interface.interface.link.show(dut_engine=serial_engine)).get_returned_value()
                        for ip_address in ip_addresses:
                            assert ip_address not in output, f"The {ip_address} is found in output"
                        assert interface_link[SystemConsts.MAC] in output, f"The {interface_link[SystemConsts.MAC]} is not found in output"

                finally:
                    mgmt_interface.interface.ip.dhcp_client.unset(apply=True, dut_engine=serial_engine, ask_for_confirmation=True).verify_result()
                    check_port_status_till_alive(True, engines.dut.ip, engines.dut.ssh_port)


def _verify_cli_output_with_dump_output(engine, device, lldp, system_output):
    cli_output = lldp.parsed_show()
    for interface_name in device.get_mgmt_ports():
        with allure.step(f"Get and parse tcp dump for {interface_name}"):
            lldp_dump = LLDPTool.get_lldp_frames(engine=engine, interface=interface_name)
            lldp_dict = LLDPTool.parse_lldp_dump(lldp_dump)
            ttl = int(cli_output[SystemConsts.LLDP_INTERVAL]) * int(cli_output[SystemConsts.LLDP_MULTIPLIER])
            assert lldp_dict[
                TcpDumpConsts.LLDP_PORT_ID] == interface_name, f'The {interface_name} name does not match lldp frame port id'
            assert int(
                lldp_dict[
                    TcpDumpConsts.LLDP_TIME_TO_LIVE]) == ttl, 'The cli ttl does not match sent frame time to live'
            is_match_hostname = lldp_dict[TcpDumpConsts.LLDP_SYSTEM_NAME] in system_output[SystemConsts.HOSTNAME] or \
                system_output[SystemConsts.HOSTNAME] in lldp_dict[TcpDumpConsts.LLDP_SYSTEM_NAME]
            assert is_match_hostname, "The hostname do not match"


def _verify_lldp_running(lldp, engine):
    with allure.step("Verify lldp container is running"):
        lldp_running = engine.run_cmd('docker inspect --format \'{{.State.Running}}\' lldp')
        assert lldp_running == 'true', 'The lldp docker container is down'
    with allure.step("Verify lldp is running and enabled"):
        cli_output = lldp.parsed_show()
        assert cli_output[SystemConsts.LLDP_STATE] == NvosConst.ENABLED, 'The lldp is not enabled'


def _verify_lldp_is_sending_frames(lldp, engine, device):
    _verify_lldp_running(lldp, engine)
    cli_output = lldp.parsed_show()

    with allure.step("Verify lldp frames are being sent for each active mgmt interface"):
        interval = int(cli_output[SystemConsts.LLDP_INTERVAL])
        for interface_name in device.get_mgmt_ports():
            output = LLDPTool.get_lldp_frames(engine=engine, interval=interval, interface=interface_name)
            assert interface_name in output, f"The data for {interface_name} not found in lldp frames"

            mgmt_interface = Port(name=interface_name)
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(
                mgmt_interface.interface.lldp.neighbor.show()).get_returned_value()
            assert output_dict, f"The neighbors output for {interface_name} is empty"


def _verify_lldp_not_running(lldp, engine, device):
    with allure.step("Verify lldp container is not running"):
        lldp_running = engine.run_cmd('docker inspect --format \'{{.State.Running}}\' lldp')
        assert lldp_running == 'false', 'The lldp docker container is up'
    with allure.step("Verify lldp is not running and not enabled"):
        cli_output = lldp.parsed_show()
        assert cli_output[SystemConsts.LLDP_STATE] == NvosConst.DISABLED, 'The lldp is enabled'

    with allure.step("Verify lldp frames are not being sent for each active mgmt interface"):
        for interface_name in device.get_mgmt_ports():
            mgmt_interface = Port(name=interface_name)
            output_dict = OutputParsingTool.parse_json_str_to_dictionary(
                mgmt_interface.interface.lldp.neighbor.show()).get_returned_value()
            assert not output_dict, f"The neighbors output for {interface_name} is not empty"

            with allure.step(f"Verify that no lldp frames are sent"):
                lldp_frames_output = LLDPTool.get_lldp_frames(engine=engine, interface=interface_name)
                assert not lldp_frames_output, f"There are still lldp frames sent for {interface_name}"


def _set_lldp_state(lldp, key, val, sleep_time=10, apply=True):
    with allure.step(f"Set lldp {key} to {val}"):
        lldp.set(key, val, apply=apply).verify_result()
        time.sleep(sleep_time)  # It takes time for state to change

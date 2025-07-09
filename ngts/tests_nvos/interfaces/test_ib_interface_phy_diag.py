import logging
import time
from typing import Union, Dict, Tuple, List

import pytest

from ngts.nvos_constants.constants_nvos import ActionConsts
from ngts.nvos_tools.Devices.IbDevice import JulietSwitch
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.IbInterfaceTool import IbInterfaceTool
from ngts.nvos_tools.infra.MultiPlanarTool import MultiPlanarTool
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.RegressionConfigurations import RegressionLinks
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.interfaces.nvl5_port.helpers import skip_if_no_trunk_links
from ngts.tools.test_utils import allure_utils as allure

LOCAL = 'local'
REMOTE = 'remote'
REASON_CODE_FIELD = {side: f'linkdown-reason-code-{side}' for side in (LOCAL, REMOTE)}
REASON_STATUS_FIELD = {side: f'linkdown-reason-status-{side}' for side in (LOCAL, REMOTE)}
INTENTIONAL_LINK_DOWN_EVENTS = 'intentional-link-down-events'
UNINTENTIONAL_LINK_DOWN_EVENTS = 'unintentional-link-down-events'
PLANE_SPLITTER = '/'
INTENTIONAL_LINK_DOWN_LOCAL_CODE = 22
INTENTIONAL_LINK_DOWN_REMOTE_CODE = 33
LINK_DOWN_PREI_CODE = 4
LINK_DOWN_UNKNOWN_CODE = 1

# source: PRM Rev 1.55.205, section 9.17.7 PUDE - Port Up/Down Event, table 1684 - PUDE - Port Up/Down Event Fields
CODE_TO_DESCRIPTION = {
    0: "No_link_down_indication", 1: "Unknown_reason", 2: "Hi_SER_or_Hi_BER", 3: "Block_Lock_loss", 4: "Alignment_loss",
    5: "FEC_sync_loss", 6: "PLL_lock_loss", 7: "FIFO_overflow", 8: "false_SKIP_condition",
    9: "Minor_Error_threshold_exceeded", 10: "Physical_layer_retransmission_timeout", 11: "Heartbeat_errors",
    12: "Link_Layer_credit_monitoring_watchdog", 13: "Link_Layer_integrity_threshold_exceeded",
    14: "Link_Layer_buffer_overrun", 15: "Down_by_outband_command_with_healthy_link",
    16: "Down_by_outband_command_for_link_with_hi_ber", 17: "Down_by_inband_command_with_healthy_link",
    18: "Down_by_inband_command_for_link_with_hi_ber", 19: "Down_by_verification_GW", 20: "Received_Remote_Fault",
    21: "Received_TS1", 22: "Down_by_management_command", 23: "Cable_was_unplugged", 24: "Cable_access_issue",
    25: "Cable_Thermal_shutdown", 26: "Current_issue", 27: "Power_budget", 28: "Fast_recovery_raw_ber",
    29: "Fast_recovery_effective_ber", 30: "Fast_recovery_symbol_ber", 31: "Fast_recovery_credit_watchdog",
    32: "Peer_side_down_to_sleep_state", 33: "Peer_side_down_to_disable_state",
    34: "Peer_side_down_to_disable_and_port_lock", 35: "Peer_side_down_due_to_thermal_event",
    36: "Peer_side_down_due_to_force_event", 37: "Peer_side_down_due_to_reset_event", 38: "Reset_no_power_cycle",
    39: "Fast_recovery_tx_plr_trigger", 40: "Down_due_to_HW_force_event", 41: "Down_due_to_thermal_event",
    42: "L1_exit_failure", 43: "too_many_link_error_recoveries", 44: "Down_due_to_contain_mode",
    45: "BW_loss_threshold_exceeded", 46: "ELS_laser_fault",
}

logger = logging.getLogger()


@pytest.mark.ib_interfaces
def test_show_phy_diag(engines, test_api, output_format):
    """Checks that `nv show interface <port> link phy-diag` returns non-empty output in a valid format."""
    selected_port = RandomizationTool.select_random_port(requested_ports_state=None).get_returned_value()
    output = selected_port.interface.link.phy_diag.show(output_format=output_format)
    d = OutputParsingTool.parse_show_output_to_dict(output, output_format).get_returned_value()
    assert len(d) > 1


@pytest.mark.ib_interfaces
def test_intentional_link_down_counter(engines, devices):
    """
    Test for `nv show interface <port> link phy-diag` intentional-link-down-events field. Flow:
    1.  Get intentional-link-down-events and unintentional-link-down-events counters for a port
    2.  Set port down
    3.  Assert the intentional- counter increased
    4.  Assert the unintentional- counter did not increase
    """
    skip_if_no_trunk_links(devices)
    with allure.step("Get initial values"):
        selected_port: Port = RandomizationTool.select_random_port().get_returned_value()
        initial_intentional, initial_unintentional = get_counters(selected_port)

    selected_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_DOWN, apply=True).verify_result()
    time.sleep(5)

    with allure.step("Get final values"):
        intentional, unintentional = get_counters(selected_port)

    with allure.step("Assert intentional counter increased"):
        # The counter aggregates all planes so the increase amount should equal the number of planes
        assert intentional > initial_intentional, (
            f"Expected the {INTENTIONAL_LINK_DOWN_EVENTS} counter to increase, but the old value is "
            f"{initial_intentional} and the new value is {intentional}"
        )
    with allure.step("Assert unintentional counter did not change"):
        assert unintentional == initial_unintentional, (
            f"Expected the {UNINTENTIONAL_LINK_DOWN_EVENTS} counter not to change, but the old value is "
            f"{initial_unintentional} and the new value is {unintentional}"
        )


@pytest.mark.ib_interfaces
def test_unintentional_link_down_counter(engines, devices, enable_asic_error_injection):
    """
    Test for `nv show interface <port> link phy-diag` unintentional-link-down-events field. Flow:
    1.  Get intentional-link-down-events and unintentional-link-down-events counters for a port
    2.  Simulate link drop
    3.  Assert the unintentional- counter increased
    4.  Assert the intentional- counter did not increase
    """
    skip_if_no_trunk_links(devices)
    with allure.step("Get initial values"):
        selected_port: Port = RandomizationTool.select_random_port(interface_type='sw').get_returned_value()
        initial_intentional, initial_unintentional = get_counters(selected_port)

    port_name = (selected_port.name if isinstance(devices.dut, JulietSwitch) else
                 MultiPlanarTool.select_random_plane_port(Fae(port_name=selected_port.name)).port.name)
    IbInterfaceTool.simulate_toggle_port_event(engines.dut, devices.dut, port_name)

    with allure.step("Get final values"):
        intentional, unintentional = get_counters(selected_port)

    with allure.step("Assert unintentional counter increased"):
        assert unintentional == initial_unintentional + 1, (
            f"Expected the {UNINTENTIONAL_LINK_DOWN_EVENTS} counter to increase by 1, but the old value is "
            f"{initial_unintentional} and the new value is {unintentional}"
        )
    with allure.step("Assert intentional counter did not change"):
        assert intentional == initial_intentional, (
            f"Expected the {INTENTIONAL_LINK_DOWN_EVENTS} counter not to change, but the old value is "
            f"{initial_intentional} and the new value is {intentional}"
        )


@pytest.mark.ib_interfaces
def test_link_down_reason(engines, devices, setup_name, enable_asic_error_injection):
    """
    Test the 'link-down-code' field (and related fields) under `nv show interface <port> link phy-diag`.
    Flow:
        1. Choose a random loopback port ("test port") and some other connected port.
        2. Set the test-port down, then set it back up.
        3. Assert the test-port's link-down-reason has the value it's expected to have after the user set the link down.
        4. Assert also for the other end of the same loopback connection (the "remote port").
        5. Simulate link error on the test-port, and wait for it to recover.
        6. Assert the test-port's local & remote link-down reasons are as expected after a link drop.
        7. Assert also for the remote port.
        8. Assert that the other port (selected in stage 1) link-down-reason has not changed during the test.
    """
    skip_if_no_trunk_links(devices)
    tested_port, tested_plane, remote_port, remote_plane, other_port = _get_test_ports(engines.dut, devices.dut)
    # todo: the above line will be replaced by the following once the required port selection functions are implemented
    # tested_port, [tested_plane], remote_port, [remote_plane] = get_loopback_plane_ports(engines.dut, setup_name)
    # _, other_port = RandomizationTool.get_random_transceiver_and_port(
    #     engines.dut, setup_name, is_loopback=True,
    #     forbidden_transceivers=[tested_port.get_transceiver_name(), remote_port.get_transceiver_name()])
    # other_port = Port(other_port)
    with allure.step("Set port down & up to reset the link-down reason"):
        tested_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_DOWN, apply=True).verify_result()
        tested_port.interface.link.state.set(op_param_name=NvosConsts.LINK_STATE_UP, apply=True).verify_result()
        tested_port.interface.wait_for_port_state(state=NvosConsts.LINK_STATE_UP)

    with allure.step("Check initial link down reasons"):
        tested_port_initial_codes = get_codes(tested_port)
        remote_port_initial_codes = get_codes(remote_port)
        other_port_initial_codes = get_codes(other_port)
        assert_reason_all_planes(tested_port, LOCAL, INTENTIONAL_LINK_DOWN_LOCAL_CODE)
        assert_reason_all_planes(tested_port, REMOTE, INTENTIONAL_LINK_DOWN_REMOTE_CODE)
        assert_reason_all_planes(remote_port, LOCAL, INTENTIONAL_LINK_DOWN_REMOTE_CODE)
        assert_reason_all_planes(remote_port, REMOTE, INTENTIONAL_LINK_DOWN_LOCAL_CODE)

    with allure.step("Simulate link error and wait for link to return to up state"):
        IbInterfaceTool.simulate_toggle_port_event(engines.dut, devices.dut, tested_plane.name)
        tested_port.interface.wait_for_port_state(state=NvosConsts.LINK_STATE_UP)

    with allure.step("Check link-down reasons"):
        assert_reason_for_plane(tested_plane, LINK_DOWN_PREI_CODE, tested_port_initial_codes)
        assert_reason_for_plane(remote_plane, LINK_DOWN_PREI_CODE, remote_port_initial_codes)
        assert_reason_not_changed(other_port, other_port_initial_codes)


def _get_test_ports(engine, device) -> Tuple[Port, Port, Port, Port, Port]:
    # temporary function to get ports until the needed port-selection-functions are implemented
    PORTS = {
        '10.7.145.61': ('swA5p1', 'swA8p1', 'swA3p1'),
        '10.7.145.62': ('swA5p1', 'swA8p1', 'swA3p1'),
        '10.7.148.94': ('swB1p1', 'swB2p1', 'swA10p1'),
        '10.7.148.95': ('swB1p1', 'swB2p1', 'swA10p1'),
        '10.7.148.138': ('swA1p1', 'swA2p1', 'swA15p1'),
        '10.7.148.139': ('swA1p1', 'swA2p1', 'swA15p1'),
        '10.7.148.248': ('sw9p1', 'sw10p1', 'sw67p1'),
        '10.7.148.249': ('sw9p1', 'sw10p1', 'sw67p1'),

        # juliet:
        '10.7.145.52': ('sw2p1s1', 'sw3p1s1', 'sw17p1s1'),
        '10.7.145.53': ('sw2p1s1', 'sw3p1s1', 'sw17p1s1'),
        '10.7.148.126': ('sw11p1s1', 'sw12p1s1', 'sw12p2s1'),
        '10.7.148.127': ('sw11p1s1', 'sw12p1s1', 'sw12p2s1'),
        '10.7.148.146': ('sw7p1s1', 'sw13p1s1', 'sw13p2s1'),
        '10.7.148.147': ('sw7p1s1', 'sw13p1s1', 'sw13p2s1'),
        '10.7.145.52': ('sw17p1s1', 'sw18p1s1', 'sw2p2s1'),
        '10.7.145.53': ('sw17p1s1', 'sw18p1s1', 'sw2p2s1'),
    }
    test_port, remote_port, other_port = [Port(p) for p in PORTS[engine.ip]]
    if isinstance(device, JulietSwitch):
        test_plane = test_port
        remote_plane = remote_port
    else:
        test_plane = test_port.get_plane_port(2)
        remote_plane = remote_port.get_plane_port(2)
    return test_port, test_plane, remote_port, remote_plane, other_port


@pytest.fixture
def enable_asic_error_injection(devices):
    """
    Enables error injection on juliet switches, then disables it when the test ends. For other switches, does nothing.
    This is necessary because on juliet-switches error-injection is blocked by default, and needs to be enabled in
    order to simulate link drops.
    """
    if 'bmc' in devices.dut.platform_inventory_items_dict:
        fae = Fae()
        with allure.step("Enable ASIC error injection"):
            fae.platform.asic.error_injection.action(ActionConsts.ENABLE, expected_output='Error injection has been')
        try:
            yield
        finally:
            with allure.step("Cleanup: disable ASIC error injection"):
                fae.platform.asic.error_injection.action(ActionConsts.DISABLE, expected_output='Error injection has been')
    else:
        yield
        return


def get_phy_diag(port):
    return OutputParsingTool.parse_show_output_to_dict(port.interface.link.phy_diag.show()).get_returned_value()


def get_counters(port: Port) -> Tuple[int, int]:
    """Runs nv show interface <port> link phy-diag, and returns the intentional & unintentional link-down counters"""
    phy_diag_output = get_phy_diag(port)
    return int(phy_diag_output[INTENTIONAL_LINK_DOWN_EVENTS]), int(phy_diag_output[UNINTENTIONAL_LINK_DOWN_EVENTS])


def assert_reason_for_plane(plane_port: Port, code: int, all_planes_previous_codes: Dict):
    """
    For the given plane_port, asserts the link down code (local or remote - according to `side`) is the given `code` and
    that the link down status matches this code. For all other planes of the same port, asserts their local & remote
    codes are the same as in all_planes_previous_codes.
    """
    with allure.step("Check link down reasons"):
        new_codes = get_codes(plane_port.get_aggregated_port())
        plane_index = 0 if plane_port.plane_number is None else plane_port.plane_number - 1
        # converts the plane number (1-based) to a list index (0-based)
        with allure.independent_step(f"Check reason for downed plane {plane_port.name}"):
            ValidationTool.assert_expected_value(code, new_codes[LOCAL][plane_index], 'link-down-reason code')
            ValidationTool.assert_expected_value(code, new_codes[REMOTE][plane_index], 'link-down-reason code')
        for i in range(len(all_planes_previous_codes[LOCAL])):
            if i == plane_index:
                continue
            with allure.independent_step(f"For plane {i + 1}"):
                for side in (LOCAL, REMOTE):
                    ValidationTool.assert_expected_value(all_planes_previous_codes[side][i], new_codes[side][i],
                                                         f"Plane {i + 1} {side} link-down-reason has changed")


def assert_reason_not_changed(port: Port, previous_codes):
    """Asserts the link-down local & remote codes are the same as the previous_codes."""
    with allure.step(f"Assert link-down reasons have not changed for {port.name}"):
        new_codes = get_codes(port)
        for i in range(len(new_codes[LOCAL])):
            for side in (LOCAL, REMOTE):
                ValidationTool.assert_expected_value(previous_codes[side][i], new_codes[side][i],
                                                     f"{port.name} plane {i} {side} reason changed")


def assert_reason_all_planes(aggregated_port: Port, side: str, expected_code: int):
    """Finds the current link-down-reason for the port and asserts all planes show the expected reason code"""
    with allure.step(f'Assert port {aggregated_port.name} {side} link-down-reason code is {expected_code} for all planes'):
        codes = get_codes(aggregated_port)[side]
        for i, code in enumerate(codes):
            with allure.independent_step(f'Plane {i}'):
                ValidationTool.assert_expected_value(expected_code, code)


def assert_description_matches_code(description: str, code: Union[int, str], item: str):
    expected = CODE_TO_DESCRIPTION[code].upper()
    assert description.upper() == expected, (
        f"{item} has {description=} but reason-code is {code} which is expected to have this description: " +
        expected
    )


def get_codes(port: Port) -> Dict[str, Tuple[int]]:
    """
    Obtains the output of nv show interface <port> link phy-diag --output json , for example:
    {
      ...
      "linkdown-reason-code-local": "22###22###22###22",
      "linkdown-reason-code-remote": "33###33###33###33",
      "linkdown-reason-status-local": "DOWN_BY_MANAGEMENT_COMMAND###DOWN_BY_MANAGEMENT_COMMAND###DOWN_BY_MANAGEMENT_COMMAND###DOWN_BY_MANAGEMENT_COMMAND",
      "linkdown-reason-status-remote": "PEER_SIDE_DOWN_TO_DISABLE_STATE###PEER_SIDE_DOWN_TO_DISABLE_STATE###PEER_SIDE_DOWN_TO_DISABLE_STATE###PEER_SIDE_DOWN_TO_DISABLE_STATE",
      ...
    }

    Asserts that the local & remote link-down-reason descriptions for each plane, match their respective codes.
    Then returns the list of local-reason codes and the list of remote-reason codes; in this example:
      {LOCAL: (22, 22, 22, 22), REMOTE: (33, 33, 33, 33)}
    """
    with allure.step(f"Get link-down reasons for {port.name}"):
        output = port.interface.link.phy_diag.show()
        output = OutputParsingTool.parse_show_output_to_dict(output).get_returned_value()
        result = {}
        for side in (LOCAL, REMOTE):
            with allure.step(f"Assert {side} reason descriptions match their codes"):
                codes = tuple(int(x) for x in output[REASON_CODE_FIELD[side]].split(PLANE_SPLITTER))
                descriptions = output[REASON_STATUS_FIELD[side]].split(PLANE_SPLITTER)
                assert len(codes) == len(descriptions), (
                    f"{REASON_CODE_FIELD[side]} shows {len(codes)} planes but {REASON_STATUS_FIELD[side]} shows {len(descriptions)}")
                for i in range(len(codes)):
                    assert_description_matches_code(descriptions[i], codes[i], f"Plane {i} {side}")
                result[side] = codes
        logger.info(f"Link down reason codes for {port.name}: {result}")
        assert len(result[LOCAL]) == len(result[REMOTE]), (
            f"{REASON_CODE_FIELD[LOCAL]} shows {len(result[LOCAL])} planes but {REASON_STATUS_FIELD[REMOTE]} shows {len(result[REMOTE])}")
        return result


def get_loopback_plane_ports(engine, setup_name, num_of_planes=1, forbidden_transceivers=None
                             ) -> Tuple[Port, List[Port], Port, List[Port]]:
    """
    Finds two ends of a loopback connection and returns fae plane-ports.
    :returns: local_planes, remote_planes
        where local_planes is a list of fae plane-ports on the same aggregated port, and remote_planes is a list of
        their respective plane-ports at the other side of the same loopback cable. The number of items in each list is
        num_of_planes.
    """
    with allure.step("Getting loopback ports"):
        transceiver, local_port = RandomizationTool.get_random_transceiver_and_port(
            engine, setup_name, requested_ports_state=NvosConsts.LINK_STATE_UP, is_loopback=True,
            forbidden_transceivers=forbidden_transceivers)
        remote_port = Port(name=RegressionLinks.get_loopback_end(setup_name, transceiver, local_port))
        local_planes = [fae.port for fae in
                        MultiPlanarTool.select_random_plane_ports(Fae(port_name=local_port), num_of_planes)]
        remote_planes = [remote_port.get_plane_port(local_plane.plane_number) for local_plane in local_planes]
        local_port = Port(local_port)
        allure.attach("Selected ports", f"{local_port=}, {local_planes=}, {remote_port=}, {remote_planes=}")
        return local_port, local_planes, remote_port, remote_planes

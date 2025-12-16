from functools import partial
import logging
import random
import pytest
import time
import re

from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvlInterfaceConsts
from ngts.nvos_constants.constants_nvos import OutputFormat, MultiPlanarConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import NvosConsts
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.tools.test_utils import allure_utils as allure
from ngts.ngts_types import EnginesT, DevicesT
from ngts.tests_nvos.constants import MINUTE

from . import helpers

pytestmark = pytest.mark.usefixtures("enable_cluster_for_mini_oberon", "has_active_access_ports")

logger = logging.getLogger(__name__)
PLR_DEFAULT_MODE = 'cs-and-crc'
PLR_MODES_MAPPER = {
    'margin-threshold1': {
        'margin-threshold': 1,
        'reject-mode': 'rejection-based-on-plr-margin',
    },
    'margin-threshold2': {
        'margin-threshold': 2,
        'reject-mode': 'rejection-based-on-plr-margin',
    },
    'cs': {
        'margin-threshold': 0,
        'reject-mode': 'rejection-based-on-cs',
    },
    'cs-and-crc': {
        'margin-threshold': 0,
        'reject-mode': 'rejection-based-on-crc-and-cs',
    },
}


@pytest.fixture(scope='module', autouse=True)
def cleanup_plr_config(access_ports: Port):
    yield
    access_ports.interface.link.plr.unset('mode', apply=True, ask_for_confirmation=True)
    helpers.reboot_gpus()


def _cleanup(port: Port):
    with allure.step(f"Unset PLR config on port {port.name}"):
        port.interface.link.plr.unset(apply=True, ask_for_confirmation=True)

    helpers.reboot_gpus()


@pytest.mark.timeout(5 * MINUTE, func_only=True)
def test_plr_cli_flow(engines: EnginesT, devices: DevicesT, access_ports: Port, register_cleanup, unregister_cleanup):
    last_acp_port_name = max(devices.dut.nvl_access_ports_list, key=lambda p: int(p.replace(NvlInterfaceConsts.ACP_PORT_TYPE, '')))
    port = Port(last_acp_port_name)
    logger.info(f"Selected NVLink port: {port.name}")

    with allure.step('Show PLR configuration'):
        logger.info(f"Running PLR show command on port {port.name}")
        output = port.interface.link.plr.show(output_format=OutputFormat.yaml)

        with allure.step('Validate output format'):
            modes = set(PLR_MODES_MAPPER.keys())
            modes_regex = "|".join(modes)
            logger.info(f"Validating mode in output against pattern: {modes_regex}")
            assert re.search(f'mode: ({modes_regex})', output), f"Output format is not as expected. Expected: {modes}, Actual: {output}"

            margin_thresholds = set(map(str, [i['margin-threshold'] for i in PLR_MODES_MAPPER.values()]))
            margin_thresholds_regex = r"\s*$|".join(margin_thresholds) + r"\s*$"
            logger.info(f"Validating margin-threshold in output against pattern: {margin_thresholds_regex}")
            assert re.search(f'margin-threshold: ({margin_thresholds_regex})', output, flags=re.M), f"Output format is not as expected. Expected: {margin_thresholds}, Actual: {output}"

            reject_modes = set(i['reject-mode'] for i in PLR_MODES_MAPPER.values())
            reject_modes_regex = r"\s*$|".join(reject_modes) + r"\s*$"
            logger.info(f"Validating reject-mode in output against pattern: {reject_modes_regex}")
            assert re.search(f'reject-mode: ({reject_modes_regex})', output, flags=re.M), f"Output format is not as expected. Expected: {reject_modes}, Actual: {output}"

    with allure.step('Select random PLR mode'):
        port_mode: str = port.interface.link.plr.parse_show()['mode']
        logger.info(f"Current port mode: {port_mode}")
        available_modes = [mode for mode in PLR_MODES_MAPPER if mode != port_mode]
        random_mode = random.choice(available_modes)
        logger.info(f"Selected random mode for testing: {random_mode}")

        with allure.step(f'Set {random_mode} mode'):
            logger.info(f"Setting PLR mode to {random_mode} on port {port.name}")
            access_ports.interface.link.plr.set('mode', random_mode, apply=True, ask_for_confirmation=True)
            register_cleanup(cleanup_func_ptr := partial(_cleanup, access_ports))

            helpers.reboot_gpus()  # need to reboot the GPUs to ensure that link will go up
            port.wait_for_port_state(port, NvosConsts.LINK_STATE_UP)
            logger.info(f"Successfully set PLR mode to {random_mode}")

        logger.info(f"Verifying PLR configuration after setting mode to {random_mode}")

        with allure.step("Verify PLR configuration"):
            for port_ in helpers.get_random_ports(engines.dut)[1]:
                with allure.independent_step(f'Verify PLR configuration on port {port_.name}'):
                    plr = port_.interface.link.plr.parse_show()
                    logger.info(f"Current PLR configuration: {plr}")

                    items = (
                        ('mode', plr['mode'], random_mode),
                        ('reject-mode', plr['reject-mode'], PLR_MODES_MAPPER[random_mode]['reject-mode']),
                        ('margin-threshold', plr['margin-threshold'], PLR_MODES_MAPPER[random_mode]['margin-threshold']),
                    )

                    with allure.independent_step('Verify PLR configuration'):
                        for check_name, actual_value, expected_value in items:
                            logger.info(f"Checking {check_name}: actual={actual_value}, expected={expected_value}")
                            with allure.independent_step(f'Verify {check_name}'):
                                error_msg = f'{check_name} is not as expected. Expected: {expected_value!r}, Actual: {actual_value!r}'
                                assert actual_value == expected_value, error_msg

    with allure.step('Unset PLR mode'):
        logger.info(f"Unsetting PLR mode on port {port.name}")
        access_ports.interface.link.plr.unset('mode', apply=True, ask_for_confirmation=True)
        with allure.step(f"Wait for port {port.name} to be up"):
            port.wait_for_port_state(port, NvosConsts.LINK_STATE_UP)
        helpers.reboot_gpus()  # need to reboot the GPUs to ensure that link will go up

        with allure.step("Verify PLR mode reverted to default"):
            for port_ in helpers.get_random_ports(engines.dut)[1]:
                with allure.independent_step(f'Wait for port {port_.name} to be up'):
                    port_.wait_for_port_state(port_, NvosConsts.LINK_STATE_UP)
                    logger.info("Successfully unset PLR mode")

                    with allure.step('Verify PLR mode reverted to default'):
                        logger.info("Checking if PLR mode reverted to default")
                        port_mode = port_.interface.link.plr.parse_show()['mode']
                        logger.info(f"Current PLR mode after unset: {port_mode}")

                    assert port_mode == PLR_DEFAULT_MODE, f"Port mode is not as expected. Expected: {PLR_DEFAULT_MODE}, Actual: {port_mode}"

        # the test successfully returned to the original state,
        # so we can unregister the cleanup function
        unregister_cleanup(cleanup_func_ptr)


@pytest.mark.timeout(MINUTE, func_only=True)
def test_feature_invalid_plr_mode_rejected(engines: EnginesT):
    """
    Verify that attempting to configure an unsupported PLR mode results in an error.

    Test Steps:
        1. Get a random NVLink interface port
        2. Run: nv set interface <nvlink-interface-id> link plr mode invalid_mode
        3. Verify the command fails as expected

    Expected Outcome:
        The CLI returns an error indicating that "invalid_mode" is not a supported PLR mode,
        and the configuration is not applied
    """
    port = helpers.get_random_port(engines.dut)
    logger.info(f"Selected NVLink port: {port.name}")

    with allure.step('Attempt to set invalid PLR mode'):
        logger.info(f"Attempting to set invalid PLR mode 'invalid-mode' on port {port.name}")
        port.interface.link.plr.set('mode', 'invalid-mode').verify_result(
            should_succeed=False,
            expected_value='Error:'
        )


@pytest.mark.timeout(5 * MINUTE, func_only=True)
def test_feature_link_transition_timing(engines: EnginesT, register_cleanup):
    """
    Verify that after applying a PLR configuration change, the interface goes down and returns up
    within defined time thresholds.

    Test Steps:
        1. Get a random NVLink interface port
        2. Configure a different PLR mode than the current one
        3. Start a timer when the configuration is applied
        4. Monitor the interface status until a "link down" event is observed
        5. Continue monitoring until the interface is "up" again
        6. Calculate the elapsed times for link down and return up

    Expected Outcome:
        The interface goes down and up within 12 seconds
    """
    port = helpers.get_random_port(engines.dut)
    logger.info(f"Selected NVLink port: {port.name}")

    plr_mode = port.interface.link.plr.parse_show()['mode']
    logger.info(f"Current PLR mode on port {port.name}: {plr_mode}")

    available_modes = [mode for mode in PLR_MODES_MAPPER if mode != plr_mode]
    random_mode = random.choice(available_modes)
    logger.info(f"Selected random mode for testing: {random_mode}")

    start_time = time.perf_counter()
    logger.info(f"Starting timer at {start_time}")

    with allure.step(f'Set {random_mode} mode'):
        logger.info(f"Setting PLR mode to {random_mode} on port {port.name}")
        port.interface.link.plr.set('mode', random_mode, apply=True, ask_for_confirmation=True)
        register_cleanup(partial(_cleanup, port))

        helpers.reboot_gpus()  # need to reboot the GPUs to ensure that link will go up
        port.wait_for_port_state(port, NvosConsts.LINK_STATE_UP)
        logger.info(f"Successfully set PLR mode to {random_mode}")

    start_time = time.perf_counter()
    with allure.step('Wait for port to come back up'):
        logger.info(f"Waiting for port {port.name} to come back up")
        port.wait_for_port_state(port, NvosConsts.LINK_STATE_UP)
        up_time = time.perf_counter() - start_time
        logger.info(f"Port {port.name} came back up after {up_time:.2f} seconds")

        # TODO: verify what is the expected time for the port to go up
        expected_transition_time = MultiPlanarConsts.PORT_UP_MAX_TIME + MultiPlanarConsts.PORT_DOWN_MAX_TIME
    assert up_time < expected_transition_time, \
        f'Port did not go up within {expected_transition_time} seconds (took {up_time:.2f}s)'

import random
import time

import pytest
import logging
from retry.api import retry_call

from ngts.constants.constants import GnmiConsts
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.cluster.cluster_tools import summarize_switch_ports
from ngts.tests_nvos.interfaces.nvl5_port.helpers import (skip_if_no_trunk_links, skip_if_no_access_links,
                                                          validate_default_config, validate_mode_set,
                                                          select_random_nvl_port_name, reset_gpus_if_needed)
from ngts.tests_nvos.system.gnmi.GnmiClient import GnmiClient
from ngts.tests_nvos.system.gnmi.constants import GnmiMode, GnmicErr
from ngts.tests_nvos.system.gnmi.helpers import verify_msg_not_in_out_or_err, verify_msg_in_out_or_err
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import FWRecoveryConsts, NvosConsts

logger = logging.getLogger()


# Shared config templates
FAE_RECOVERY_CONFIG_DICT = {
    "serdes-eq": {
        "setting_prefix": FWRecoveryConsts.SerdesEQ.SETTING_PREFIX,
        "mode": FWRecoveryConsts.SerdesEQ.MODE,
        "timeout": FWRecoveryConsts.SerdesEQ.TIMEOUT,
    },
    # "logic-relock": {
    #     "setting_prefix": FWRecoveryConsts.LogicRelock.SETTING_PREFIX,
    #     "mode": FWRecoveryConsts.LogicRelock.MODE,
    #     "timeout": FWRecoveryConsts.LogicRelock.TIMEOUT,
    # }
}

FAE_RECOVERY_CONFIG_PARAMS = [
    pytest.param(config, id=name) for name, config in FAE_RECOVERY_CONFIG_DICT.items()
]


@pytest.mark.interface
@pytest.mark.multiplanar
def test_show_fw_recovery_counters(engines, devices):
    """
    @summary:
        Verify default FAE recovery counters via NV "show interface" and GNMI subscription.

    Steps:
    1. Run `nv show interface <port> link phy-diag --view detailed` and parse JSON output.
    2. Confirm all default counters match FWRecoveryConsts.DEFAULT_FW_RECOVERY_COUNTERS.
    3. Pick a random counter, subscribe via GNMI ONCE to `phy-diag/state/<counter>`.
    4. Verify GNMI stream contains the counter name and its default value.
    """
    port_result = RandomizationTool.select_random_port(
        requested_ports_state=NvosConsts.LINK_STATE_ALL_TYPES)

    if not port_result.result:
        pytest.skip(f"Skipping test - {port_result.info}")

    selected_port = port_result.get_returned_value()

    with allure.step("Validate show interface command with all nvl5 interfaces"):
        port_output = OutputParsingTool.parse_json_str_to_dictionary(
            selected_port.interface.link.phy_diag.show()).get_returned_value()

    expected_fields = list(FWRecoveryConsts.DEFAULT_FW_RECOVERY_COUNTERS.keys())
    expected_values = list(FWRecoveryConsts.DEFAULT_FW_RECOVERY_COUNTERS.values())

    ValidationTool.validate_fields_values_in_output(expected_fields, expected_values, port_output)

    random_counter = random.choice(expected_fields)
    with allure.step(f'set up gnmi client'):
        client = GnmiClient(engines.dut.ip, GnmiConsts.GNMI_DEFAULT_PORT, devices.dut.default_username,
                            devices.dut.default_password, verify_tools_installed=True)

    with allure.step(f'subscribe client to counter: {random_counter} and verify information'):
        out, err = client.gnmic_subscribe_interface(GnmiMode.ONCE, selected_port.name, skip_cert_verify=True,
                                                    interface_path=f'phy-diag/state/{random_counter}')

    with allure.step(f'check that "{random_counter}" was streamed'):
        verify_msg_not_in_out_or_err(GnmicErr.AUTH_FAIL, out, err)
        verify_msg_in_out_or_err(f'{random_counter}: {FWRecoveryConsts.DEFAULT_FW_RECOVERY_COUNTERS.get(random_counter)}', out)


@pytest.mark.interface
@pytest.mark.multiplanar
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_fw_recovery_bad_flow(devices, engines, test_name, test_api):
    """
    @summary:
        Negative validation of phy-recovery parameters rejects invalid values.

    Steps:
    1. Attempt to show a non-existent phy-recovery attribute; expect failure.
    2. For each field in FWRecoveryConsts.negative_test_cases:
       a. Set the field to its bad_value with apply=True and ask_for_confirmation=True.
       b. Verify that the expected_error is raised.
    """
    TestToolkit.tested_api = test_api
    with allure.step(f"Select port for test"):
        port_result = RandomizationTool.select_random_port(
            requested_ports_state=NvosConsts.LINK_STATE_ALL_TYPES)

        if not port_result.result:
            pytest.skip(f"Skipping test - {port_result.info}")

        selected_port = port_result.get_returned_value()
        selected_port = Fae(port_name=selected_port.name)

    with allure.step(f"Testing interface {selected_port.port.name}"):
        phy_recovery_obj = selected_port.port.interface.link.phy_recovery
        with allure.independent_step(f"Testing show non-existing attribute in phy-recovery"):
            phy_recovery_obj.show('non-existing', should_succeed=False)

        with allure.independent_step(f"Testing bad arguments on interface {selected_port.port.name}"):
            for field, case in FWRecoveryConsts.negative_test_cases.items():
                bad_value = case["bad_value"]
                expected_error = case["expected_error"]
            with allure.step(f"Set {field} to bad value '{bad_value}'"):
                phy_recovery_obj.set(field, bad_value, apply=True, ask_for_confirmation=True, expected_str=expected_error).verify_result(False)


@pytest.mark.interface
@pytest.mark.multiplanar
@pytest.mark.parametrize('config', FAE_RECOVERY_CONFIG_PARAMS)
def test_set_fae_fw_recovery_trunk_ports(engines, devices, random_api, standalone_system, config):
    """
    @summary:
        Verify that firmware recovery settings (mode and timeout) can be applied and updated on trunk ports (sw).

    Steps:
    1. Skip if no trunk links.
    2. Enable recovery mode and set timeout on all trunk ports.
    3. Verify settings on a single random trunk port.
    4. Update timeout higher and lower, verifying group vs. local effects.
    5. Disable recovery and confirm defaults restored.
    """
    skip_if_no_trunk_links(devices)
    port_name = select_random_nvl_port_name(devices, 'sw')
    summarized_switch_ports = summarize_switch_ports(devices.dut.nvl5_trunk_ports_list)

    _run_fae_mode_timeout_test(
        test_api=random_api,
        group_all_ports=summarized_switch_ports,
        devices=devices,
        port_name=port_name,
        config=config,
    )


@pytest.mark.interface
@pytest.mark.multiplanar
@pytest.mark.parametrize('config', FAE_RECOVERY_CONFIG_PARAMS)
def test_set_fae_fw_recovery_access_ports(engines, devices, random_api, standalone_system, has_loopbox, config, setup_name):
    """
    @summary:
        Verify that firmware recovery settings (mode and timeout) can be applied and updated on access ports (acp).

    Steps:
    1. Skip if no access links.
    2. Enable recovery mode and set timeout on all access ports.
    3. Verify settings on a single random access port.
    4. Update timeout higher and lower, verifying group vs. local effects.
    5. Disable recovery and confirm defaults restored.
    """
    skip_if_no_access_links(has_loopbox, standalone_system)
    port_name = select_random_nvl_port_name(devices, 'acp')
    _run_fae_mode_timeout_test(
        test_api=random_api,
        group_all_ports=f'acp1-{str(len(devices.dut.nvl5_access_ports_list))}',
        devices=devices,
        port_name=port_name,
        config=config,
        standalone_system=standalone_system,
        setup_name=setup_name,
    )


def _run_fae_mode_timeout_test(test_api, group_all_ports, devices, port_name, config, standalone_system=False, setup_name=None):
    TestToolkit.tested_api = test_api

    selected_port = Fae(port_name=port_name)
    all_ports = Fae(port_name=group_all_ports)

    validate_default_config(selected_port)

    try:
        for mode in FWRecoveryConsts.MODES:
            with allure.step(f"Set {config['mode']} to {mode}"):
                if mode == FWRecoveryConsts.ENABLED:
                    _apply_mode(all_ports, config, mode)
                    _apply_timeout(all_ports, config, 100)
                    reset_gpus_if_needed(setup_name)
                    _verify_config(selected_port, config, mode, 100)

                    higher_timeout = random.randint(11, 20) * 10
                    with allure.step(f"Update timeout to higher value ({higher_timeout}) while mode {mode}"):
                        _apply_timeout(all_ports, config, higher_timeout)
                        reset_gpus_if_needed(setup_name)
                        _validate_timeout(selected_port, config, higher_timeout)

                    lower_timeout = random.randint(1, 9) * 10
                    if standalone_system:
                        with allure.step(f"Update timeout to lower value ({lower_timeout}) locally — expect NO change"):
                            _apply_timeout(selected_port, config, lower_timeout)
                            _validate_timeout(selected_port, config, higher_timeout, verify_after_seconds=30)

                    with allure.step(f"Update timeout to lower value ({lower_timeout}) on all ports"):
                        _apply_timeout(all_ports, config, lower_timeout)
                        reset_gpus_if_needed(setup_name)
                        _validate_timeout(selected_port, config, lower_timeout)
                else:
                    _apply_mode(all_ports, config, mode)
                    _verify_config(selected_port, config, mode)
    finally:
        with allure.step("Unset configuration to return to defaults"):
            all_ports.port.interface.link.phy_recovery.unset(apply=True, ask_for_confirmation=True).verify_result()
            reset_gpus_if_needed(setup_name)

        retry_call(validate_default_config, [selected_port], exceptions=AssertionError, tries=6, delay=30)


def _apply_mode(selected_port, config, mode):
    selected_port.port.interface.link.phy_recovery.set(config["mode"], mode, apply=True,
                                                       ask_for_confirmation=True).verify_result()


def _apply_timeout(selected_port, config, timeout):
    selected_port.port.interface.link.phy_recovery.set(config["timeout"], timeout, apply=True,
                                                       ask_for_confirmation=True).verify_result()


def _verify_config(selected_port, config, mode, timeout=None):
    retry_call(validate_mode_set, [selected_port, config, mode, timeout], exceptions=AssertionError, tries=6, delay=30)


def _validate_timeout(selected_port, config, expected_timeout=None, verify_after_seconds=None):
    _verify_config(selected_port, config, FWRecoveryConsts.ENABLED, expected_timeout)

    if verify_after_seconds:
        with allure.step(f"Wait {verify_after_seconds}s and re-verify timeout is still {expected_timeout}"):
            time.sleep(verify_after_seconds)
            _verify_config(selected_port, config, FWRecoveryConsts.ENABLED, expected_timeout)

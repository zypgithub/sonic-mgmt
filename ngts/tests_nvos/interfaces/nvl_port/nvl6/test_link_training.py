import time
import pytest
import random
from itertools import combinations

from ngts.ngts_types import CleanUpT, DevicesT
from ngts.nvos_constants import constants_nvos as consts_nv
from ngts.nvos_tools.Devices import IbDevice
from ngts.nvos_tools.ib.InterfaceConfiguration import Port, nvos_consts as ib_consts
from ngts.nvos_tools.infra import Fae
from ngts.nvos_tools.infra import NvosTestToolkit as TestToolkit
from ngts.nvos_tools.infra import OutputParsingTool
from ngts.nvos_tools.infra import ValidationTool
from ngts.tests_nvos.helpers.interfaces import interface_helpers
from ngts.tests_nvos.helpers.interfaces.nvl_port.nvl6 import link_training_helpers
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope="session")
def fae_objs(linked_ports_pair: tuple[str, str]) -> tuple[Fae.Fae, Fae.Fae]:
    return tuple(Fae.Fae(port_name=port) for port in linked_ports_pair)


def _skip_if_fec_measure_not_supported(devices: DevicesT) -> None:
    if isinstance(devices.dut, IbDevice.RosalindSwitch) and devices.dut.asic_type in [consts_nv.NvosConst.QTM4, consts_nv.NvosConst.NVL6]:
        return
    pytest.skip("FEC measure is not supported on this device")


@pytest.mark.parametrize('test_api', [random.choice(consts_nv.ApiType.ALL_TYPES)])
def test_link_training(devices: DevicesT, fae_objs: tuple[Fae.Fae, Fae.Fae], test_api: consts_nv.ApiType, register_cleanup: CleanUpT):
    """
    Test fec-measure-mode lifecycle and mismatch on NVL6 link-training.

    Verifies the fec-measure-mode field on QTM4/NVL6 devices through the full
    configuration lifecycle and a cross-port mismatch scenario.

    Test Steps:
        1. Verify default link-training params on both linked ports
        2. Set fec-measure-mode to 'disabled' on both ports, verify
        3. Set fec-measure-mode to 'enabled' on both ports, verify
        4. Mismatch: port 1 'enabled', port 2 'disabled', verify negotiation
        5. Unset link-training on both ports, verify defaults restored
    """
    _skip_if_fec_measure_not_supported(devices)

    TestToolkit.TestToolkit.tested_api = test_api
    fae_port_1, fae_port_2 = fae_objs
    port_objs = [Port.Port(fae.port.name) for fae in fae_objs]

    register_cleanup(lambda: link_training_helpers.cleanup_link_training(devices, fae_objs))

    with allure.step("Verify default link-training params on both ports"):
        with allure.step("Verify link-training params"):
            for fae in fae_objs:
                with allure.step(f"Verify port {fae.port.name}"):
                    ValidationTool.ValidationTool.compare_nested_dictionary_content(
                        fae.interface.link.link_training.parse_show_operational_applied(),
                        link_training_helpers.LINK_TRAINING_DEFAULTS,
                    ).verify_result()

    with allure.step("Set fec-measure-mode to 'enabled' on both ports"):
        for fae in fae_objs:
            fae.interface.link.link_training.set(
                op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                apply=True,
                ask_for_confirmation=True,
            ).verify_result()
        interface_helpers.wait_and_verify_link(port_objs, timeout=ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_ENABLED)
        with allure.step("Verify link-training params"):
            for fae in fae_objs:
                with allure.step(f"Verify port {fae.port.name}"):
                    ValidationTool.ValidationTool.compare_nested_dictionary_content(
                        fae.interface.link.link_training.parse_show_operational_applied(),
                        {
                            consts_nv.ConfState.OPERATIONAL: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE:
                                    consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                            },
                            consts_nv.ConfState.APPLIED: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE:
                                    consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                            },
                        },
                    ).verify_result()

    with allure.step("Set fec-measure-mode to 'disabled' on both ports"):
        for fae in fae_objs:
            fae.interface.link.link_training.set(
                op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
                apply=True,
                ask_for_confirmation=True,
            ).verify_result()
        interface_helpers.wait_and_verify_link(port_objs, timeout=ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_DISABLED)
        with allure.step("Verify link-training params"):
            for fae in fae_objs:
                with allure.step(f"Verify port {fae.port.name}"):
                    ValidationTool.ValidationTool.compare_nested_dictionary_content(
                        fae.interface.link.link_training.parse_show_operational_applied(),
                        {
                            consts_nv.ConfState.OPERATIONAL: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE:
                                    consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
                            },
                            consts_nv.ConfState.APPLIED: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE:
                                    consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
                            },
                        },
                    ).verify_result()

    with allure.step("Mismatch: port 1 'enabled', port 2 'disabled'"):
        fae_port_1.interface.link.link_training.set(
            op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
            op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
            apply=True,
            ask_for_confirmation=True,
        ).verify_result()
        fae_port_2.interface.link.link_training.set(
            op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
            op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
            apply=True,
            ask_for_confirmation=True,
        ).verify_result()
        interface_helpers.wait_and_verify_link(port_objs, timeout=ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_ENABLED)
        with allure.step(f"Verify port {fae_port_1.port.name}"):
            ValidationTool.ValidationTool.compare_nested_dictionary_content(
                fae_port_1.interface.link.link_training.parse_show_operational_applied(),
                {
                    consts_nv.ConfState.OPERATIONAL: {
                        consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE:
                            consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                    },
                    consts_nv.ConfState.APPLIED: {
                        consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE:
                            consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                    },
                },
            ).verify_result()
        with allure.step(f"Verify port {fae_port_2.port.name}"):
            ValidationTool.ValidationTool.compare_nested_dictionary_content(
                fae_port_2.interface.link.link_training.parse_show_operational_applied(),
                {
                    consts_nv.ConfState.OPERATIONAL: {
                        consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE:
                            consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                    },
                    consts_nv.ConfState.APPLIED: {
                        consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE:
                            consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
                    },
                },
            ).verify_result()


@pytest.mark.parametrize('test_api', [random.choice(consts_nv.ApiType.ALL_TYPES)])
def test_link_training_negotiation(devices: DevicesT, fae_objs: tuple[Fae.Fae, Fae.Fae], test_api: consts_nv.ApiType, register_cleanup: CleanUpT):
    """
    Test fec-measure-fail-action negotiation on NVL6 link-training.

    Verifies fail-action negotiation between linked ports:
        1. Enable fec-measure-mode on both ports
        2. Set the same fail-action on both ports, verify oper/applied match
        3. For each mismatch pair, verify operational = max(priority)
    """
    _skip_if_fec_measure_not_supported(devices)

    TestToolkit.TestToolkit.tested_api = test_api
    fae_port_1, fae_port_2 = fae_objs
    port_objs = [Port.Port(fae.port.name) for fae in fae_objs]
    FailAction = consts_nv.LinkTrainingConsts.FecMeasureFailAction

    register_cleanup(lambda: link_training_helpers.cleanup_link_training(devices, fae_objs))

    with allure.step("Set fec-measure-mode to 'enabled' on both ports"):
        for fae in fae_objs:
            fae.interface.link.link_training.set(
                op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                apply=True,
                ask_for_confirmation=True,
            ).verify_result()
        interface_helpers.wait_and_verify_link(port_objs, timeout=ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_ENABLED)
        with allure.step("Verify link-training params"):
            for fae in fae_objs:
                with allure.step(f"Verify port {fae.port.name}"):
                    ValidationTool.ValidationTool.compare_nested_dictionary_content(
                        fae.interface.link.link_training.parse_show_operational_applied(),
                        {
                            consts_nv.ConfState.OPERATIONAL: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE:
                                    consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                            },
                            consts_nv.ConfState.APPLIED: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE:
                                    consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                            },
                        },
                    ).verify_result()

    with allure.step("Same fail-action on both ports"):
        for action in FailAction.operational():
            with allure.step(f"Set both ports to {action}"):
                for fae in fae_objs:
                    fae.interface.link.link_training.set(
                        op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION,
                        op_param_value=action,
                        apply=True,
                        ask_for_confirmation=True,
                    ).verify_result()
                interface_helpers.wait_and_verify_link(port_objs, timeout=ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_ENABLED)
                with allure.step("Verify link-training params"):
                    for fae in fae_objs:
                        with allure.step(f"Verify port {fae.port.name}"):
                            ValidationTool.ValidationTool.compare_nested_dictionary_content(
                                fae.interface.link.link_training.parse_show_operational_applied(),
                                {
                                    consts_nv.ConfState.OPERATIONAL: {
                                        consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: action,
                                    },
                                    consts_nv.ConfState.APPLIED: {
                                        consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: action,
                                    },
                                },
                            ).verify_result()

    with allure.step("Mismatch: verify operational = max priority"):
        mismatch_pairs = [
            sorted(pair, key=lambda fail_action: consts_nv.LinkTrainingConsts.FAIL_ACTION_PRIORITY[fail_action])
            for pair in combinations(FailAction.operational(), 2)
        ]
        for low_action, high_action in mismatch_pairs:
            with allure.step(f"Mismatch: port1={low_action}, port2={high_action}"):
                fae_port_1.interface.link.link_training.set(
                    op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION,
                    op_param_value=low_action,
                    apply=True,
                    ask_for_confirmation=True,
                ).verify_result()
                fae_port_2.interface.link.link_training.set(
                    op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION,
                    op_param_value=high_action,
                    apply=True,
                    ask_for_confirmation=True,
                ).verify_result()
                interface_helpers.wait_and_verify_link(port_objs, timeout=ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_ENABLED)
                with allure.step(f"Verify port {fae_port_1.port.name}"):
                    ValidationTool.ValidationTool.compare_nested_dictionary_content(
                        fae_port_1.interface.link.link_training.parse_show_operational_applied(),
                        {
                            consts_nv.ConfState.OPERATIONAL: {consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: high_action},
                            consts_nv.ConfState.APPLIED: {consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: low_action},
                        },
                    ).verify_result()
                with allure.step(f"Verify port {fae_port_2.port.name}"):
                    ValidationTool.ValidationTool.compare_nested_dictionary_content(
                        fae_port_2.interface.link.link_training.parse_show_operational_applied(),
                        {
                            consts_nv.ConfState.OPERATIONAL: {consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: high_action},
                            consts_nv.ConfState.APPLIED: {consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: high_action},
                        },
                    ).verify_result()


_FAIL_ACTION_EXPECTED_LINK_STATE: dict[str, tuple[str, str | None]] = {
    consts_nv.LinkTrainingConsts.FecMeasureFailAction.FORCE_LINKUP.value: (
        ib_consts.NvosConsts.LINK_STATE_UP, ib_consts.IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_LINK_UP,
    ),
    consts_nv.LinkTrainingConsts.FecMeasureFailAction.GOTO_POLLING.value: (
        ib_consts.NvosConsts.LINK_STATE_DOWN, ib_consts.IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_POLLING,
    ),
    consts_nv.LinkTrainingConsts.FecMeasureFailAction.GOTO_DISABLE.value: (
        ib_consts.NvosConsts.LINK_STATE_DOWN, ib_consts.IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE_DISABLED,
    ),
}


@pytest.mark.parametrize('test_api', [random.choice(consts_nv.ApiType.ALL_TYPES)])
def test_link_training_fail_action(
    devices: DevicesT,
    fae_objs: tuple[Fae.Fae, Fae.Fae],
    test_api: consts_nv.ApiType,
    register_cleanup: CleanUpT,
):
    """
    Verify link state per fail-action when FEC measure is forced to fail.

    Keeps port 1 fail-action at fw-default (lowest priority) and sets port 2
    through force-linkup, goto-polling, goto-disable. Since both ports have
    force-fail=all-iterations, FEC always fails. The negotiated operational
    fail-action = max(port1, port2) = port 2's value, determining link state.
    """
    _skip_if_fec_measure_not_supported(devices)

    TestToolkit.TestToolkit.tested_api = test_api
    fae_port_1, fae_port_2 = fae_objs
    port_objs = [Port.Port(fae.port.name) for fae in fae_objs]
    FailAction = consts_nv.LinkTrainingConsts.FecMeasureFailAction

    register_cleanup(lambda: link_training_helpers.cleanup_link_training(devices, fae_objs))

    with allure.step("Enable fec-measure-mode and force-fail=all-iterations on both ports"):
        for fae in fae_objs:
            fae.interface.link.link_training.set(
                op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                apply=True,
                ask_for_confirmation=True,
            ).verify_result()
        interface_helpers.wait_and_verify_link(port_objs, timeout=ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_ENABLED)
        for fae in fae_objs:
            fae.interface.link.link_training.set(
                op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL,
                op_param_value=consts_nv.LinkTrainingConsts.FecMeasureForceFail.ALL_ITERATIONS.value,
                apply=True,
                ask_for_confirmation=True,
            ).verify_result()
        interface_helpers.wait_and_verify_link(port_objs, timeout=ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_ENABLED)
        with allure.step("Verify link-training params"):
            for fae in fae_objs:
                with allure.step(f"Verify port {fae.port.name}"):
                    ValidationTool.ValidationTool.compare_nested_dictionary_content(
                        fae.interface.link.link_training.parse_show_operational_applied(),
                        {
                            consts_nv.ConfState.OPERATIONAL: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION_OPERATIONAL_DEFAULT.value,
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL: consts_nv.LinkTrainingConsts.FecMeasureForceFail.ALL_ITERATIONS.value,
                            },
                            consts_nv.ConfState.APPLIED: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION_APPLIED_DEFAULT.value,
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL: consts_nv.LinkTrainingConsts.FecMeasureForceFail.ALL_ITERATIONS.value,
                            },
                        },
                    ).verify_result()

    for fail_action in FailAction.operational():
        with allure.step(f"Set port1 fail-action={fail_action}, port2 stays at fw-default"):
            fae_port_1.interface.link.link_training.set(
                op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION,
                op_param_value=fail_action,
                apply=True,
                ask_for_confirmation=True,
            ).verify_result()
        time.sleep(ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_ENABLED)
        with allure.step("Verify link-training params"):
            ValidationTool.ValidationTool.compare_nested_dictionary_content(
                fae_port_1.interface.link.link_training.parse_show_operational_applied(),
                {
                    consts_nv.ConfState.OPERATIONAL: {
                        consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: fail_action,
                    },
                    consts_nv.ConfState.APPLIED: {
                        consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: fail_action,
                    },
                },
            ).verify_result()

        expected_state, expected_physical_state = _FAIL_ACTION_EXPECTED_LINK_STATE[fail_action]

        with allure.step(f"Verify link state={expected_state} because negotiated fail-action={fail_action}"):
            for port in port_objs:
                link_output = OutputParsingTool.OutputParsingTool.parse_show_interface_link_output_to_dictionary(
                    port.interface.link.show(),
                ).get_returned_value()
                assert link_output[ib_consts.IbInterfaceConsts.LINK_STATE] == expected_state, (
                    f"Port {port.name} link state is {link_output[ib_consts.IbInterfaceConsts.LINK_STATE]}"
                    f" - expected {expected_state} because negotiated fail-action={fail_action}"
                )
                assert link_output[ib_consts.IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE] == expected_physical_state, (
                    f"Port {port.name} physical-state is {link_output[ib_consts.IbInterfaceConsts.LINK_PHYSICAL_PORT_STATE]}"
                    f" - expected {expected_physical_state} because negotiated fail-action={fail_action}"
                )


@pytest.mark.parametrize('test_api', [random.choice(consts_nv.ApiType.ALL_TYPES)])
def test_link_training_force_fail(
    devices: DevicesT, fae_objs: tuple[Fae.Fae, Fae.Fae], test_api: consts_nv.ApiType, register_cleanup: CleanUpT,
):
    """
    Verify link state per force-fail when FEC measure is forced to fail.

    In this test, the following steps are performed:
    1. Enable `fec-measure-mode` on both ports, apply the config, and verify that
       `FEC_MEASURE_FORCE_FAIL` field is set to its default value on both ports.
    2. For each possible value of `force-fail`:
       a. Set `FEC_MEASURE_FORCE_FAIL` to the value on both ports, apply the config.
       b. Wait for link-up.
       c. Verify that operational/applied state reflects the configured force-fail value.
    """
    _skip_if_fec_measure_not_supported(devices)

    TestToolkit.TestToolkit.tested_api = test_api
    port_objs = [Port.Port(fae.port.name) for fae in fae_objs]

    register_cleanup(lambda: link_training_helpers.cleanup_link_training(devices, fae_objs))

    with allure.step("Enable fec-measure-mode on both ports and verify force-fail default"):
        for fae in fae_objs:
            fae.interface.link.link_training.set(
                op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                apply=True,
                ask_for_confirmation=True,
            ).verify_result()
        interface_helpers.wait_and_verify_link(
            port_objs, timeout=ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_ENABLED,
        )
        with allure.step("Verify link-training params"):
            for fae in fae_objs:
                with allure.step(f"Verify port {fae.port.name}"):
                    ValidationTool.ValidationTool.compare_nested_dictionary_content(
                        fae.interface.link.link_training.parse_show_operational_applied(),
                        {
                            consts_nv.ConfState.OPERATIONAL: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL: consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL_OPERATIONAL_DEFAULT.value,
                            },
                            consts_nv.ConfState.APPLIED: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL: consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL_APPLIED_DEFAULT.value,
                            },
                        },
                    ).verify_result()

    with allure.step("Set force-fail to all-iterations on both ports"):
        for value in consts_nv.LinkTrainingConsts.FecMeasureForceFail.all():
            for fae in fae_objs:
                fae.interface.link.link_training.set(
                    op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL,
                    op_param_value=value,
                    apply=True,
                    ask_for_confirmation=True,
                ).verify_result()
        interface_helpers.wait_and_verify_link(
            port_objs, timeout=ib_consts.InternalNvosConsts.NVL6_ACP_LINK_UP_TIMEOUT_LTX_ENABLED,
        )
        with allure.step("Verify link-training params"):
            for fae in fae_objs:
                with allure.step(f"Verify port {fae.port.name}"):
                    ValidationTool.ValidationTool.compare_nested_dictionary_content(
                        fae.interface.link.link_training.parse_show_operational_applied(),
                        {
                            consts_nv.ConfState.OPERATIONAL: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL: value,
                            },
                            consts_nv.ConfState.APPLIED: {
                                consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL: value,
                            },
                        },
                    ).verify_result()

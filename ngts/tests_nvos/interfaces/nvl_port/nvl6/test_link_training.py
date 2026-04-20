import random
import pytest
import logging
from itertools import combinations

from ngts.ngts_types import DevicesT
from ngts.nvos_constants import constants_nvos as consts_nv
from ngts.nvos_tools.Devices import IbDevice
from ngts.nvos_tools.ib.InterfaceConfiguration import Port as Port_module
from ngts.nvos_tools.ib.InterfaceConfiguration import nvos_consts as ib_consts
from ngts.nvos_tools.infra import Fae
from ngts.nvos_tools.infra import NvosTestToolkit as TestToolkit
from ngts.cli_wrappers.nvue import nvue_general_clis as gen_clis
from ngts.tests_nvos.helpers.interfaces.nvl_port.nvl6 import link_training_helpers
from ngts.tools.test_utils import allure_utils as allure

logger: logging.Logger = logging.getLogger(__name__)

_NVL_SPEED_BOUNDARY_LOW = 200
_NVL_SPEED_BOUNDARY_HIGH = 400


def _select_nvl_speed(devices: DevicesT) -> tuple[str, int]:
    """Select the max NVL speed strictly between 200G and 400G; fall back to 400G with doubled timeout."""
    intermediate = [s for s in devices.dut.supported_nvl_speeds
                    if _NVL_SPEED_BOUNDARY_LOW < int(s.rstrip('G')) < _NVL_SPEED_BOUNDARY_HIGH]
    if intermediate:
        return min(intermediate, key=lambda s: int(s.rstrip('G'))), ib_consts.InternalNvosConsts.DEFAULT_TIMEOUT

    assert '400G' in devices.dut.supported_nvl_speeds, (
        f"No usable NVL speed: no intermediate speeds and 400G not in {devices.dut.supported_nvl_speeds}"
    )
    return '400G', ib_consts.InternalNvosConsts.DEFAULT_TIMEOUT * 2


@pytest.fixture(scope="session")
def fae_objs(linked_ports_pair: tuple[str, str]) -> tuple[Fae.Fae, Fae.Fae]:
    return tuple(Fae.Fae(port_name=port) for port in linked_ports_pair)


def _set_linked_ports_speed(fae_objs: tuple[Fae.Fae, ...], devices: DevicesT) -> None:
    speed, timeout = _select_nvl_speed(devices)
    with allure.step(f"Set linked ports speed to {speed}{' (fallback)' if timeout else ''}"):
        for fae in fae_objs:
            Port_module.Port(fae.port.name).interface.link.set(
                op_param_name='speed',
                op_param_value=speed,
                apply=True,
                ask_for_confirmation=True,
            ).verify_result()
    link_training_helpers.wait_and_verify_link(fae_objs, timeout=timeout)


def _unset_linked_ports_speed(fae_objs: tuple[Fae.Fae, ...]) -> None:
    with allure.step("Unset linked ports speed"):
        for fae in fae_objs:
            Port_module.Port(fae.port.name).interface.link.unset(
                op_param='speed',
                apply=True,
                ask_for_confirmation=True,
            ).verify_result()
    link_training_helpers.wait_and_verify_link(fae_objs)


def _skip_if_fec_measure_not_supported(devices: DevicesT) -> None:
    if isinstance(devices.dut, IbDevice.RosalindSwitch) and devices.dut.asic_type in [consts_nv.NvosConst.QTM4, consts_nv.NvosConst.NVL6]:
        return
    pytest.skip("FEC measure is not supported on this device")


@pytest.mark.parametrize('test_api', [random.choice(consts_nv.ApiType.ALL_TYPES)])
def test_link_training(devices: DevicesT, fae_objs: tuple[Fae.Fae, Fae.Fae], test_api: consts_nv.ApiType, register_cleanup):
    """
    Test fec-measure-mode lifecycle and mismatch on NVL6 link-training.

    Verifies the fec-measure-mode field on QTM4/NVL6 devices through the full
    configuration lifecycle and a cross-port mismatch scenario.

    Test Steps:
        1. Set linked ports to the min intermediate NVL speed
        2. Verify default link-training params on both linked ports
        3. Set fec-measure-mode to 'enabled' on both ports, verify
        4. Mismatch: port 1 'enabled', port 2 'disabled', verify negotiation
        5. Set fec-measure-mode to 'disabled' on both ports, verify
        6. Unset link-training on both ports, verify defaults restored
    """
    _skip_if_fec_measure_not_supported(devices)

    TestToolkit.TestToolkit.tested_api = test_api
    fae_port_1, fae_port_2 = fae_objs

    register_cleanup(lambda: link_training_helpers.cleanup_link_training(fae_objs))
    register_cleanup(lambda: _unset_linked_ports_speed(fae_objs))

    _set_linked_ports_speed(fae_objs, devices)

    with allure.step("Verify default link-training params on both ports"):
        link_training_helpers.verify_link_training([
            (fae_port_1, link_training_helpers.LINK_TRAINING_DEFAULTS),
            (fae_port_2, link_training_helpers.LINK_TRAINING_DEFAULTS),
        ])

    with allure.step("Set fec-measure-mode to 'enabled' on both ports"):
        for fae in fae_objs:
            fae.interface.link.kr.set(
                op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
            ).verify_result()
        gen_clis.NvueGeneralCli.apply_config(TestToolkit.TestToolkit.engines.dut, ask_for_confirmation=True)
        link_training_helpers.wait_and_verify_link(fae_objs)
        expected_enabled: link_training_helpers.OperationalAppliedT = {
            consts_nv.ConfState.OPERATIONAL: {consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value},
            consts_nv.ConfState.APPLIED: {consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value},
        }
        link_training_helpers.verify_link_training([
            (fae_port_1, expected_enabled),
            (fae_port_2, expected_enabled),
        ])

    with allure.step("Mismatch: port 1 'enabled', port 2 'disabled'"):
        fae_port_1.interface.link.kr.set(
            op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
            op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
            apply=True,
            ask_for_confirmation=True,
        ).verify_result()
        fae_port_2.interface.link.kr.set(
            op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
            op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
            apply=True,
            ask_for_confirmation=True,
        ).verify_result()
        link_training_helpers.wait_and_verify_link(fae_objs)
        link_training_helpers.verify_link_training([
            (fae_port_1, {
                consts_nv.ConfState.OPERATIONAL: {consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value},
                consts_nv.ConfState.APPLIED: {consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value},
            }),
            (fae_port_2, {
                consts_nv.ConfState.OPERATIONAL: {consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value},
                consts_nv.ConfState.APPLIED: {consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value},
            }),
        ])

    with allure.step("Set fec-measure-mode to 'disabled' on both ports"):
        for fae in fae_objs:
            fae.interface.link.kr.set(
                op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
            ).verify_result()
        gen_clis.NvueGeneralCli.apply_config(TestToolkit.TestToolkit.engines.dut, ask_for_confirmation=True)
        link_training_helpers.wait_and_verify_link(fae_objs)
        expected_disabled: link_training_helpers.OperationalAppliedT = {
            consts_nv.ConfState.OPERATIONAL: {consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value},
            consts_nv.ConfState.APPLIED: {consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value},
        }
        link_training_helpers.verify_link_training([
            (fae_port_1, expected_disabled),
            (fae_port_2, expected_disabled),
        ])


@pytest.mark.parametrize('test_api', [random.choice(consts_nv.ApiType.ALL_TYPES)])
def test_link_training_negotiation(devices: DevicesT, fae_objs: tuple[Fae.Fae, Fae.Fae], test_api: consts_nv.ApiType, register_cleanup):
    """
    Test fec-measure-fail-action negotiation on NVL6 link-training.

    Verifies fail-action negotiation between linked ports:
        1. Set both ports to the min intermediate NVL speed
        2. Enable fec-measure-mode on both ports
        3. Set the same fail-action on both ports, verify oper/applied match
        4. For each mismatch pair, verify operational = max(priority)
    """
    _skip_if_fec_measure_not_supported(devices)

    TestToolkit.TestToolkit.tested_api = test_api
    fae_port_1, fae_port_2 = fae_objs
    FailAction = consts_nv.LinkTrainingConsts.FecMeasureFailAction

    register_cleanup(lambda: link_training_helpers.cleanup_link_training(fae_objs))
    register_cleanup(lambda: _unset_linked_ports_speed(fae_objs))

    _set_linked_ports_speed(fae_objs, devices)

    with allure.step("Enable fec-measure-mode on both ports"):
        for fae in fae_objs:
            fae.interface.link.kr.set(
                op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
            ).verify_result()
        gen_clis.NvueGeneralCli.apply_config(TestToolkit.TestToolkit.engines.dut, ask_for_confirmation=True)
        link_training_helpers.wait_and_verify_link(fae_objs)

    with allure.step("Same fail-action on both ports"):
        for action in FailAction.operational():
            with allure.step(f"Set both ports to {action}"):
                for fae in fae_objs:
                    fae.interface.link.kr.set(
                        op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION,
                        op_param_value=action,
                    ).verify_result()
                gen_clis.NvueGeneralCli.apply_config(TestToolkit.TestToolkit.engines.dut, ask_for_confirmation=True)
                link_training_helpers.wait_and_verify_link(fae_objs)
                expected_same: link_training_helpers.OperationalAppliedT = {
                    consts_nv.ConfState.OPERATIONAL: {consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: action},
                    consts_nv.ConfState.APPLIED: {consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: action},
                }
                link_training_helpers.verify_link_training([
                    (fae_port_1, expected_same),
                    (fae_port_2, expected_same),
                ])

    with allure.step("Mismatch: verify operational = max priority"):
        mismatch_pairs = [
            sorted(pair, key=lambda fail_action: consts_nv.LinkTrainingConsts.FAIL_ACTION_PRIORITY[fail_action])
            for pair in combinations(FailAction.operational(), 2)
        ]
        for low_action, high_action in mismatch_pairs:
            with allure.step(f"Mismatch: port1={low_action}, port2={high_action}"):
                fae_port_1.interface.link.kr.set(
                    op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION,
                    op_param_value=low_action,
                ).verify_result()
                fae_port_2.interface.link.kr.set(
                    op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION,
                    op_param_value=high_action,
                ).verify_result()
                gen_clis.NvueGeneralCli.apply_config(TestToolkit.TestToolkit.engines.dut, ask_for_confirmation=True)
                link_training_helpers.wait_and_verify_link(fae_objs)
                link_training_helpers.verify_link_training([
                    (fae_port_1, {
                        consts_nv.ConfState.OPERATIONAL: {consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: high_action},
                        consts_nv.ConfState.APPLIED: {consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: low_action},
                    }),
                    (fae_port_2, {
                        consts_nv.ConfState.OPERATIONAL: {consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: high_action},
                        consts_nv.ConfState.APPLIED: {consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: high_action},
                    }),
                ])

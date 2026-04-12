import random
import pytest
import logging

from ngts.ngts_types import devices_T as dev_t
from ngts.nvos_constants import constants_nvos as consts_nv
from ngts.nvos_tools.Devices import IbDevice
from ngts.nvos_tools.infra import Fae as fae_mod
from ngts.nvos_tools.infra import NvosTestToolkit as tt
from ngts.tests_nvos.helpers.interfaces.nvl_port.nvl6 import link_training_helpers as lt
from ngts.tools.test_utils import allure_utils as allure

logger: logging.Logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def fae_objs(linked_ports_pair: tuple[str, str]) -> tuple[fae_mod.Fae, fae_mod.Fae]:
    return tuple(fae_mod.Fae(port_name=port) for port in linked_ports_pair)


def skip_if_fec_measure_not_supported(devices: dev_t.DevicesT) -> None:
    if isinstance(devices.dut, IbDevice.RosalindSwitch) and devices.dut.asic_type in [consts_nv.NvosConst.QTM4, consts_nv.NvosConst.NVL6]:
        return
    pytest.skip("FEC measure is not supported on this device")


@pytest.mark.parametrize('test_api', [random.choice(consts_nv.ApiType.ALL_TYPES)])
def test_link_training(devices: dev_t.DevicesT, fae_objs: tuple[fae_mod.Fae, fae_mod.Fae], test_api: consts_nv.ApiType):
    """
    Test fec-measure-mode lifecycle on NVL6 link-training.

    Verifies the fec-measure-mode field on QTM4/NVL6 devices through the full
    configuration lifecycle: default -> enabled -> disabled -> unset.

    Test Steps:
        1. Verify default fec-measure-mode on both linked ports
        2. Set fec-measure-mode to 'enabled' on both ports, verify
        3. Set fec-measure-mode to 'disabled' on both ports, verify
        4. Unset fec-measure-mode on both ports, verify defaults restored
    """
    skip_if_fec_measure_not_supported(devices)

    tt.TestToolkit.tested_api = test_api
    fae_port_1, fae_port_2 = fae_objs

    with allure.step("Verify default fec-measure-mode on both ports"):
        lt.verify_fec_measure_mode([
            (fae_port_1, lt.FEC_MEASURE_MODE_DEFAULT),
            (fae_port_2, lt.FEC_MEASURE_MODE_DEFAULT),
        ])

    try:
        with allure.step("Set fec-measure-mode to 'enabled' on both ports"):
            for fae in fae_objs:
                fae.interface.link.kr.set(
                    op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                    op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                    apply=True,
                    ask_for_confirmation=True,
                ).verify_result()
            lt.wait_and_verify_link(fae_objs)
            expected_enabled: lt.OperationalAppliedT = {
                consts_nv.ConfState.OPERATIONAL: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                consts_nv.ConfState.APPLIED: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
            }
            lt.verify_fec_measure_mode([
                (fae_port_1, expected_enabled),
                (fae_port_2, expected_enabled),
            ])

        with allure.step("Set fec-measure-mode to 'disabled' on both ports"):
            for fae in fae_objs:
                fae.interface.link.kr.set(
                    op_param_name=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                    op_param_value=consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
                    apply=True,
                    ask_for_confirmation=True,
                ).verify_result()
            lt.wait_and_verify_link(fae_objs)
            expected_disabled: lt.OperationalAppliedT = {
                consts_nv.ConfState.OPERATIONAL: consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
                consts_nv.ConfState.APPLIED: consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
            }
            lt.verify_fec_measure_mode([
                (fae_port_1, expected_disabled),
                (fae_port_2, expected_disabled),
            ])
    finally:
        lt.cleanup_fec_measure_mode(fae_objs)


@pytest.mark.parametrize('test_api', [random.choice(consts_nv.ApiType.ALL_TYPES)])
def test_link_training_mismatch(devices: dev_t.DevicesT, fae_objs: tuple[fae_mod.Fae, fae_mod.Fae], test_api: consts_nv.ApiType):
    """
    Test fec-measure-mode mismatch on NVL6 link-training.

    Verifies that when one port is set to 'enabled' and the peer port is set to
    'disabled', both ports resolve to 'enabled' in both operational and applied.

    Test Steps:
        1. Set port 1 to 'enabled' and port 2 to 'disabled', verify both are enabled
        2. Unset fec-measure-mode on both ports, verify defaults restored
    """
    skip_if_fec_measure_not_supported(devices)

    tt.TestToolkit.tested_api = test_api
    fae_port_1, fae_port_2 = fae_objs

    try:
        with allure.step("Set port 1 to 'enabled' and port 2 to 'disabled'"):
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
            lt.wait_and_verify_link(fae_objs)
            expected_port_1: lt.OperationalAppliedT = {
                consts_nv.ConfState.OPERATIONAL: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                consts_nv.ConfState.APPLIED: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
            }
            expected_port_2: lt.OperationalAppliedT = {
                consts_nv.ConfState.OPERATIONAL: consts_nv.LinkTrainingConsts.FecMeasureMode.ENABLED.value,
                consts_nv.ConfState.APPLIED: consts_nv.LinkTrainingConsts.FecMeasureMode.DISABLED.value,
            }
            lt.verify_fec_measure_mode([
                (fae_port_1, expected_port_1),
                (fae_port_2, expected_port_2),
            ])
    finally:
        lt.cleanup_fec_measure_mode(fae_objs)

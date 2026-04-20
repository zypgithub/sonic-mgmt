import logging
from typing import TypedDict

from ngts.nvos_constants import constants_nvos as consts_nv
from ngts.nvos_tools.ib.InterfaceConfiguration import nvos_consts as ib_consts
from ngts.nvos_tools.infra import Fae
from ngts.nvos_tools.infra import ValidationTool
from ngts.tests_nvos.interfaces.nvl_port import helpers as nvl_port_helpers
from ngts.tools.test_utils import allure_utils as allure

logger: logging.Logger = logging.getLogger(__name__)


OperationalAppliedT = TypedDict('OperationalAppliedT', {
    consts_nv.ConfState.OPERATIONAL: dict[str, str],
    consts_nv.ConfState.APPLIED: dict[str, str],
})

LINK_TRAINING_DEFAULTS: OperationalAppliedT = {
    consts_nv.ConfState.OPERATIONAL: {
        consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE_OPERATIONAL_DEFAULT.value,
        consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION_OPERATIONAL_DEFAULT.value,
    },
    consts_nv.ConfState.APPLIED: {
        consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE_APPLIED_DEFAULT.value,
        consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION_APPLIED_DEFAULT.value,
    },
}


def wait_and_verify_link(fae_objs: tuple[Fae.Fae, ...], timeout: int = ib_consts.InternalNvosConsts.DEFAULT_TIMEOUT) -> None:
    port_names: list[str] = [fae.port.name for fae in fae_objs]
    with allure.step("Wait for port state to be up on both ports"):
        for fae in fae_objs:
            fae.port.interface.wait_for_port_state(
                ib_consts.NvosConsts.LINK_STATE_UP, timeout=timeout,
            ).verify_result()
    with allure.step("Verify link diagnostics on both ports"):
        nvl_port_helpers.verify_link_diagnostic(port_names)


def verify_link_training(
    expected_values: list[tuple[Fae.Fae, OperationalAppliedT]],
) -> None:
    with allure.step("Verify link-training params"):
        for fae, expected in expected_values:
            with allure.step(f"Verify port {fae.port.name}"):
                actual: OperationalAppliedT = {
                    consts_nv.ConfState.OPERATIONAL: fae.interface.link.kr.parse_show(rev=consts_nv.ConfState.OPERATIONAL),
                    consts_nv.ConfState.APPLIED: fae.interface.link.kr.parse_show(rev=consts_nv.ConfState.APPLIED),
                }
                ValidationTool.ValidationTool.compare_nested_dictionary_content(
                    actual, expected,
                ).verify_result()


def cleanup_link_training(fae_objs: tuple[Fae.Fae, ...]) -> None:
    with allure.step("Cleanup: unset link-training component, wait for link, verify defaults"):
        for fae in fae_objs:
            fae.interface.link.kr.unset(apply=True, ask_for_confirmation=True).verify_result()
        wait_and_verify_link(fae_objs)
        verify_link_training([(fae, LINK_TRAINING_DEFAULTS) for fae in fae_objs])

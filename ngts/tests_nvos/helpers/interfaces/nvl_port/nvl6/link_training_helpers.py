from ngts.ngts_types import DevicesT, OperationalAppliedT
from ngts.nvos_constants import constants_nvos as consts_nv
from ngts.nvos_tools.ib.InterfaceConfiguration import Port, nvos_consts as ib_consts
from ngts.nvos_tools.infra import Fae
from ngts.nvos_tools.infra import ValidationTool
from ngts.tests_nvos.helpers.interfaces import interface_helpers
from ngts.tools.test_utils import allure_utils as allure

LINK_TRAINING_DEFAULTS: OperationalAppliedT = {
    consts_nv.ConfState.OPERATIONAL: {
        consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE_OPERATIONAL_DEFAULT.value,
        consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION_OPERATIONAL_DEFAULT.value,
        consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL: consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL_OPERATIONAL_DEFAULT.value,
    },
    consts_nv.ConfState.APPLIED: {
        consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE: consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE_APPLIED_DEFAULT.value,
        consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION: consts_nv.LinkTrainingConsts.FEC_MEASURE_FAIL_ACTION_APPLIED_DEFAULT.value,
        consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL: consts_nv.LinkTrainingConsts.FEC_MEASURE_FORCE_FAIL_APPLIED_DEFAULT.value,
    },
}


def cleanup_link_training(devices: DevicesT, fae_objs: tuple[Fae.Fae, ...]) -> None:
    with allure.step("Cleanup: unset link-training component, wait for link, verify defaults"):
        for fae in fae_objs:
            fae.interface.link.link_training.unset(apply=True, ask_for_confirmation=True).verify_result()
        interface_helpers.wait_and_verify_link(
            [Port.Port(fae.port.name) for fae in fae_objs],
            timeout=devices.dut.expected_operation_durations.get(ib_consts.InternalNvosConsts.ACP_PORT_GOES_UP),
        )
        with allure.step("Verify link-training params"):
            for fae in fae_objs:
                with allure.step(f"Verify port {fae.port.name}"):
                    actual: OperationalAppliedT = fae.interface.link.link_training.parse_show_operational_applied()
                    ValidationTool.ValidationTool.compare_nested_dictionary_content(
                        actual, LINK_TRAINING_DEFAULTS,
                    ).verify_result()

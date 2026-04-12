import re
import logging
from typing import TypedDict

from ngts.nvos_constants import constants_nvos as consts_nv
from ngts.nvos_tools.ib.InterfaceConfiguration import nvos_consts as ib_consts
from ngts.nvos_tools.infra import Fae as fae_mod
from ngts.nvos_tools.infra import NvosTestToolkit as tt
from ngts.nvos_tools.infra import ValidationTool as vt
from ngts.tests_nvos.interfaces.nvl_port import helpers as nvl_port_helpers
from ngts.tools.test_utils import allure_utils as allure

logger: logging.Logger = logging.getLogger(__name__)


OperationalAppliedT = TypedDict('OperationalAppliedT', {
    consts_nv.ConfState.OPERATIONAL: str,
    consts_nv.ConfState.APPLIED: str,
})

FEC_MEASURE_MODE_REGEX: re.Pattern = re.compile(
    rf"{consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE}\s+"
    rf"({'|'.join(consts_nv.LinkTrainingConsts.FecMeasureMode.all())})\s+"
    rf"({'|'.join(consts_nv.LinkTrainingConsts.FecMeasureMode.all())})"
)

FEC_MEASURE_MODE_DEFAULT: OperationalAppliedT = {
    consts_nv.ConfState.OPERATIONAL: consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE_OPERATIONAL_DEFAULT.value,
    consts_nv.ConfState.APPLIED: consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE_APPLIED_DEFAULT.value,
}


def get_fec_measure_mode_output(fae_obj: fae_mod.Fae) -> OperationalAppliedT:
    with allure.step(f"Get fec-measure-mode output for port {fae_obj.port.name}"):
        show_cmd = f"nv show {fae_obj.interface.link.kr.get_resource_path().replace('/', ' ')}"
        output = tt.TestToolkit.engines.dut.run_cmd(show_cmd)
        match = FEC_MEASURE_MODE_REGEX.search(output)
        assert match is not None, f"No fec-measure-mode match in output: {output}"
        return {
            consts_nv.ConfState.OPERATIONAL: match.group(1),
            consts_nv.ConfState.APPLIED: match.group(2),
        }


def wait_and_verify_link(fae_objs: tuple[fae_mod.Fae, ...]) -> None:
    port_names: list[str] = [fae.port.name for fae in fae_objs]
    with allure.step("Wait for port state to be up on both ports"):
        for fae in fae_objs:
            fae.port.interface.wait_for_port_state(ib_consts.NvosConsts.LINK_STATE_UP).verify_result()
    with allure.step("Verify link diagnostics on both ports"):
        nvl_port_helpers.verify_link_diagnostic(port_names)


def verify_fec_measure_mode(expected_values: list[tuple[fae_mod.Fae, OperationalAppliedT]]) -> None:
    with allure.step("Verify fec-measure-mode on both ports"):
        for fae, expected in expected_values:
            actual = get_fec_measure_mode_output(fae)
            vt.ValidationTool.compare_dictionaries(actual, expected).verify_result()


def cleanup_fec_measure_mode(fae_objs: tuple[fae_mod.Fae, ...]) -> None:
    with allure.step("Cleanup: unset fec-measure-mode, wait for link, verify defaults"):
        for fae in fae_objs:
            fae.interface.link.kr.unset(
                op_param=consts_nv.LinkTrainingConsts.FEC_MEASURE_MODE,
                apply=True,
                ask_for_confirmation=True,
            ).verify_result()
        wait_and_verify_link(fae_objs)
        verify_fec_measure_mode([
            (fae, FEC_MEASURE_MODE_DEFAULT) for fae in fae_objs
        ])

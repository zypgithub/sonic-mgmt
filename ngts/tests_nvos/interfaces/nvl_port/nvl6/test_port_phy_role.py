import random
import re
import pytest
import logging
from typing import Dict, List, Optional, Tuple, TypedDict, Union
from ngts.ngts_types.devices_T import DevicesT
from ngts.nvos_tools.ib.InterfaceConfiguration.nvos_consts import IbInterfaceConsts, NvosConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.interfaces.nvl_port.helpers import validate_ports_state_and_speed
from ngts.nvos_constants.constants_nvos import ApiType, PhyRoleConsts, ConfState
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.interfaces.nvl_port.helpers import is_qtm4_device
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port
from ngts.cli_wrappers.nvue.nvue_ib_interface_clis import NvueIbInterfaceCli

logger: logging.Logger = logging.getLogger(__name__)

EXPECTED_LINK_DIAGNOSTIC_STATUS = {'0': {'status': 'No issue was observed'}}

PhyRoleOutputT = TypedDict('PhyRoleOutputT', {
    ConfState.OPERATIONAL: PhyRoleConsts.PhyRole,
    ConfState.APPLIED: PhyRoleConsts.PhyRole
})

ConstantRoleOutputT = TypedDict('ConstantRoleOutputT', {
    ConfState.OPERATIONAL: PhyRoleConsts.ConstantRole,
    ConfState.APPLIED: PhyRoleConsts.ConstantRole
})

PhyRolesOutputT = TypedDict('PhyRolesOutputT', {
    PhyRoleConsts.PHY_ROLE: PhyRoleOutputT,
    PhyRoleConsts.CONSTANT_ROLE: ConstantRoleOutputT
})

PHY_ROLE_REGEX = rf"{PhyRoleConsts.PHY_ROLE}\s+({'|'.join(PhyRoleConsts.PhyRole.all())})\s+({'|'.join(PhyRoleConsts.PhyRole.all())})"
CONSTANT_ROLE_REGEX = rf"{PhyRoleConsts.CONSTANT_ROLE}\s+({'|'.join(PhyRoleConsts.ConstantRole.all())})\s+({'|'.join(PhyRoleConsts.ConstantRole.all())})"


def is_device_set_simplex(fae_objs: Tuple[Fae, Fae]) -> bool:
    # Check if the device is set to simplex
    try:
        validate_ports_state_and_speed(IbInterfaceConsts.XDR_SLOW_SPEED, [fae.port.name for fae in fae_objs], "acp")
    except AssertionError:
        return False
    # If the device is set to simplex, verify that the phy-role is N/A
    for fae in fae_objs:
        fae_link_show_cmd = f"nv show {fae.interface.link.get_resource_path().replace('/', ' ')}"
        fae_link_output = TestToolkit.engines.dut.run_cmd(fae_link_show_cmd)
        phy_role_match = re.search(PHY_ROLE_REGEX, fae_link_output)
        assert phy_role_match is None, f"Phy role is not N/A when set to simplex on {fae.port.name}: {fae_link_output}"
    return True


def get_fae_objs(linked_ports_pair: Tuple[str, str]) -> Tuple[Fae, Fae]:
    return tuple(Fae(port_name=port) for port in linked_ports_pair)


@pytest.fixture(scope="session")
def fae_objs(linked_ports_pair: Tuple[str, str]) -> Tuple[Fae, Fae]:
    return get_fae_objs(linked_ports_pair)


def _get_phy_roles_output(fae_obj: Fae) -> PhyRolesOutputT:
    with allure.step(f"Get phy-role and constant-role output for port {fae_obj.port.name}"):
        fae_link_show_cmd = f"nv show {fae_obj.interface.link.get_resource_path().replace('/', ' ')}"
        fae_link_output = TestToolkit.engines.dut.run_cmd(fae_link_show_cmd)
        phy_role_match = re.search(PHY_ROLE_REGEX, fae_link_output)
        assert phy_role_match is not None, f"No phy-role match found in output: {fae_link_output}"
        constant_role_match = re.search(CONSTANT_ROLE_REGEX, fae_link_output)
        assert constant_role_match is not None, f"No constant-role match found in output: {fae_link_output}"
        return {
            PhyRoleConsts.PHY_ROLE: {
                ConfState.OPERATIONAL: phy_role_match.group(1),
                ConfState.APPLIED: phy_role_match.group(2)
            },
            PhyRoleConsts.CONSTANT_ROLE: {
                ConfState.OPERATIONAL: constant_role_match.group(1),
                ConfState.APPLIED: constant_role_match.group(2)
            }
        }


def verify_link_diagnostic(ports: List[str]) -> None:
    output = NvueIbInterfaceCli.show_interface(TestToolkit.engines.dut, port_name='--view link-diagnostics')
    output_dict = OutputParsingTool.parse_json_str_to_dictionary(output).get_returned_value()
    for port_name in ports:
        port_diagnostics = output_dict[port_name]['link']['diagnostics']
        assert port_diagnostics == EXPECTED_LINK_DIAGNOSTIC_STATUS, f"Port {port_name} diagnostics status is not 0"


def _verify_role_output(role_output: Union[PhyRoleOutputT, ConstantRoleOutputT], operational_expected: Union[str, List[str]], applied_expected: Union[str, List[str]]) -> None:
    with allure.step("Verify role output matches expected values"):
        if isinstance(operational_expected, list):
            assert role_output[ConfState.OPERATIONAL] in operational_expected, \
                f"Operational role {role_output[ConfState.OPERATIONAL]} is not in {operational_expected}"
        else:
            assert role_output[ConfState.OPERATIONAL] == operational_expected, \
                f"Operational role {role_output[ConfState.OPERATIONAL]} is not {operational_expected}"
        if isinstance(applied_expected, list):
            assert role_output[ConfState.APPLIED] in applied_expected, \
                f"Applied role {role_output[ConfState.APPLIED]} is not in {applied_expected}"
        else:
            assert role_output[ConfState.APPLIED] == applied_expected, \
                f"Applied role {role_output[ConfState.APPLIED]} is not {applied_expected}"


def role_case(
    roles_to_set: Optional[List[Tuple[Fae, Union[PhyRoleConsts.PhyRole, PhyRoleConsts.ConstantRole], str]]] = None,
    expected_values: Optional[List[Tuple[Fae, Union[PhyRoleConsts.PhyRole, PhyRoleConsts.ConstantRole], Union[str, List[str]], Union[str, List[str]]]]] = None
) -> Optional[Dict[Fae, PhyRolesOutputT]]:
    roles_outputs: Optional[Dict[Fae, PhyRolesOutputT]] = None
    if roles_to_set is not None:
        for fae, role, value in roles_to_set:
            with allure.step(f"Set {role} to {value} on {fae.port.name}"):
                fae.interface.link.set(
                    op_param_name=role, op_param_value=value, apply=True, ask_for_confirmation=True
                ).verify_result()
        with allure.step("Wait for port state to be up"):
            seen = set()
            for fae, _, _ in roles_to_set:
                if fae.port.name in seen:
                    continue
                seen.add(fae.port.name)
                fae.port.interface.wait_for_port_state(NvosConsts.LINK_STATE_UP).verify_result()
    if expected_values is not None:
        roles_outputs: Dict[Fae, PhyRolesOutputT] = {}
        with allure.step("Verify link diagnostic"):
            port_names: List[str] = [fae.port.name for fae, _, _, _ in expected_values]
            verify_link_diagnostic(port_names)
        with allure.step("Get ports roles output"):
            seen = set()
            for fae, _, _, _ in expected_values:
                if fae.port.name in seen:
                    continue
                seen.add(fae.port.name)
                roles_outputs[fae] = _get_phy_roles_output(fae)
        for fae, role, expected_operational, expected_applied in expected_values:
            with allure.step(f"Verify {role} output on {fae.port.name}"):
                _verify_role_output(roles_outputs[fae][role], expected_operational, expected_applied)
    return roles_outputs


def verify_phy_role_default(fae_port_1: Fae, fae_port_2: Fae) -> None:
    with allure.step("Verify default phy-role on both ports"):
        roles_outputs: Optional[Dict[Fae, PhyRolesOutputT]] = role_case(
            expected_values=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, [PhyRoleConsts.PhyRole.PRIMARY.value, PhyRoleConsts.PhyRole.SECONDARY.value], PhyRoleConsts.PhyRole.FW_DEFAULT.value),
                (fae_port_2, PhyRoleConsts.PHY_ROLE, [PhyRoleConsts.PhyRole.PRIMARY.value, PhyRoleConsts.PhyRole.SECONDARY.value], PhyRoleConsts.PhyRole.FW_DEFAULT.value)
            ]
        )
        assert roles_outputs is not None, "Roles outputs are None"
        assert roles_outputs[fae_port_1][PhyRoleConsts.PHY_ROLE][ConfState.OPERATIONAL] is not roles_outputs[fae_port_2][PhyRoleConsts.PHY_ROLE][ConfState.OPERATIONAL], \
            f"Both ports have the same operational role: {roles_outputs[fae_port_1][PhyRoleConsts.PHY_ROLE][ConfState.OPERATIONAL]} and "\
            f"{roles_outputs[fae_port_2][PhyRoleConsts.PHY_ROLE][ConfState.OPERATIONAL]}"


@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_port_phy_role(devices: DevicesT, fae_objs: Tuple[Fae, Fae], test_api: ApiType):
    """
    Test phy role functionality on NVL ports.
    This test verifies the phy role feature on QTM4 devices, which allows a port to be configured to
    a specific role (primary, secondary, or auto). The test validates that the port's role is set correctly
    and remains stable across port state flips.
    Test Steps:
        1. Verify default phy-role and constant-role on both ports
        2. Set first port to primary role
        3. Set first port to secondary role
        4. Set first port to auto role
        5. Unset both ports
    """
    if not is_qtm4_device(devices):
        pytest.skip("Phy role is only supported on QTM4 devices")
    if is_device_set_simplex(fae_objs):
        pytest.skip("Phy role is not supported on devices set to simplex")

    TestToolkit.tested_api = test_api
    fae_port_1, fae_port_2 = fae_objs
    with allure.step("Verify default phy-role and constant-role on both ports"):
        verify_phy_role_default(fae_port_1, fae_port_2)
    with allure.step("Set first port to primary role"):
        role_case(
            roles_to_set=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.PRIMARY.value)
            ],
            expected_values=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.PRIMARY.value, [PhyRoleConsts.PhyRole.PRIMARY.value, PhyRoleConsts.PhyRole.FW_DEFAULT.value]),
                (fae_port_2, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.SECONDARY.value, [PhyRoleConsts.PhyRole.SECONDARY.value, PhyRoleConsts.PhyRole.FW_DEFAULT.value])
            ]
        )
    with allure.step("Set first port to secondary role"):
        role_case(
            roles_to_set=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.SECONDARY.value)
            ],
            expected_values=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.SECONDARY.value, [PhyRoleConsts.PhyRole.SECONDARY.value, PhyRoleConsts.PhyRole.FW_DEFAULT.value]),
                (fae_port_2, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.PRIMARY.value, [PhyRoleConsts.PhyRole.PRIMARY.value, PhyRoleConsts.PhyRole.FW_DEFAULT.value])
            ]
        )
    with allure.step("Set first port to primary and second port to secondary"):
        role_case(
            roles_to_set=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.PRIMARY.value),
                (fae_port_2, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.SECONDARY.value)
            ],
            expected_values=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.PRIMARY.value, PhyRoleConsts.PhyRole.PRIMARY.value),
                (fae_port_2, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.SECONDARY.value, PhyRoleConsts.PhyRole.SECONDARY.value)
            ]
        )
    with allure.step("Set first port to auto role"):
        role_case(
            roles_to_set=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.AUTO.value)
            ],
            expected_values=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.PRIMARY.value, PhyRoleConsts.PhyRole.AUTO.value),
                (fae_port_2, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.SECONDARY.value, PhyRoleConsts.PhyRole.SECONDARY.value)
            ]
        )
    with allure.step("unset both ports"):
        fae_port_1.interface.link.unset(op_param=PhyRoleConsts.PHY_ROLE, apply=True, ask_for_confirmation=True).verify_result()
        fae_port_2.interface.link.unset(op_param=PhyRoleConsts.PHY_ROLE, apply=True, ask_for_confirmation=True).verify_result()
        fae_port_1.port.interface.wait_for_port_state(NvosConsts.LINK_STATE_UP).verify_result()
        fae_port_2.port.interface.wait_for_port_state(NvosConsts.LINK_STATE_UP).verify_result()
        verify_phy_role_default(fae_port_1, fae_port_2)


@pytest.mark.parametrize('test_api', [random.choice(ApiType.ALL_TYPES)])
def test_port_constant_role(devices: DevicesT, fae_objs: Tuple[Fae, Fae], test_api: ApiType):
    """
    Test constant role functionality on NVL ports.
    This test verifies the constant-role feature on QTM4 devices, which allows a port to maintain
    its PHY role even after link state changes. The test validates that when constant-role is enabled,
    the port's role remains stable across port state flips.
    Test Steps:
        1. Verify default phy-role and constant-role on both ports
        2. Set first port to auto role and enable constant-role
        3. Verify role sticks after port state flip (down/up)
        4. Unset constant-role on both ports
    """
    if not is_qtm4_device(devices):
        pytest.skip("Constant role is only supported on QTM4 devices")
    if is_device_set_simplex(fae_objs):
        pytest.skip("Phy role is not supported on devices set to simplex")

    TestToolkit.tested_api = test_api
    fae_port_1, fae_port_2 = fae_objs
    with allure.step("Verify default phy-role and constant-role on both ports"):
        verify_phy_role_default(fae_port_1, fae_port_2)
        roles_outputs: Dict[Fae, PhyRolesOutputT] = role_case(
            expected_values=[
                (fae_port_1, PhyRoleConsts.CONSTANT_ROLE, PhyRoleConsts.ConstantRole.ENABLED.value, PhyRoleConsts.ConstantRole.ENABLED.value),
                (fae_port_2, PhyRoleConsts.CONSTANT_ROLE, PhyRoleConsts.ConstantRole.ENABLED.value, PhyRoleConsts.ConstantRole.ENABLED.value)
            ]
        )
        assert roles_outputs is not None, "Roles outputs are None"
        assert fae_port_2 in roles_outputs, f"Port {fae_port_2.port.name} not found in roles outputs"
        default_port_2: PhyRolesOutputT = roles_outputs[fae_port_2].copy()
    with allure.step("Set first port to auto role and enable constant-role"):
        port_1_expected_operational_role: str = [v for v in PhyRoleConsts.PhyRole.operational() if v != default_port_2[PhyRoleConsts.PHY_ROLE][ConfState.OPERATIONAL]][0]
        role_case(
            roles_to_set=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, PhyRoleConsts.PhyRole.AUTO.value),
                (fae_port_1, PhyRoleConsts.CONSTANT_ROLE, PhyRoleConsts.ConstantRole.ENABLED.value)
            ],
            expected_values=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, port_1_expected_operational_role, PhyRoleConsts.PhyRole.AUTO.value),
                (fae_port_1, PhyRoleConsts.CONSTANT_ROLE, PhyRoleConsts.ConstantRole.ENABLED.value, PhyRoleConsts.ConstantRole.ENABLED.value),
                (fae_port_2, PhyRoleConsts.PHY_ROLE, default_port_2[PhyRoleConsts.PHY_ROLE][ConfState.OPERATIONAL], default_port_2[PhyRoleConsts.PHY_ROLE][ConfState.APPLIED]),
                (fae_port_2, PhyRoleConsts.CONSTANT_ROLE, default_port_2[PhyRoleConsts.CONSTANT_ROLE][ConfState.OPERATIONAL], default_port_2[PhyRoleConsts.CONSTANT_ROLE][ConfState.APPLIED])
            ]
        )
    with allure.step("Verify role sticks after port state flip"):
        fae_port_1.port.interface.link.state.set(NvosConsts.LINK_STATE_DOWN, apply=True, ask_for_confirmation=True).verify_result()
        fae_port_1.port.interface.link.state.set(NvosConsts.LINK_STATE_UP, apply=True, ask_for_confirmation=True).verify_result()
        fae_port_1.port.interface.wait_for_port_state(NvosConsts.LINK_STATE_UP).verify_result()
        role_case(
            expected_values=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, port_1_expected_operational_role, PhyRoleConsts.PhyRole.AUTO.value),
                (fae_port_1, PhyRoleConsts.CONSTANT_ROLE, PhyRoleConsts.ConstantRole.ENABLED.value, PhyRoleConsts.ConstantRole.ENABLED.value),
                (fae_port_2, PhyRoleConsts.PHY_ROLE, default_port_2[PhyRoleConsts.PHY_ROLE][ConfState.OPERATIONAL], default_port_2[PhyRoleConsts.PHY_ROLE][ConfState.APPLIED]),
                (fae_port_2, PhyRoleConsts.CONSTANT_ROLE, default_port_2[PhyRoleConsts.CONSTANT_ROLE][ConfState.OPERATIONAL], default_port_2[PhyRoleConsts.CONSTANT_ROLE][ConfState.APPLIED])
            ]
        )
    with allure.step("Unset constant-role"):
        fae_port_1.interface.link.unset(op_param=PhyRoleConsts.CONSTANT_ROLE, apply=True, ask_for_confirmation=True).verify_result()
        fae_port_2.interface.link.unset(op_param=PhyRoleConsts.CONSTANT_ROLE, apply=True, ask_for_confirmation=True).verify_result()
        fae_port_1.port.interface.wait_for_port_state(NvosConsts.LINK_STATE_UP).verify_result()
        fae_port_2.port.interface.wait_for_port_state(NvosConsts.LINK_STATE_UP).verify_result()
        role_case(
            expected_values=[
                (fae_port_1, PhyRoleConsts.PHY_ROLE, port_1_expected_operational_role, PhyRoleConsts.PhyRole.AUTO.value),
                (fae_port_1, PhyRoleConsts.CONSTANT_ROLE, PhyRoleConsts.ConstantRole.ENABLED.value, PhyRoleConsts.ConstantRole.ENABLED.value),
                (fae_port_2, PhyRoleConsts.PHY_ROLE, default_port_2[PhyRoleConsts.PHY_ROLE][ConfState.OPERATIONAL], default_port_2[PhyRoleConsts.PHY_ROLE][ConfState.APPLIED]),
                (fae_port_2, PhyRoleConsts.CONSTANT_ROLE, default_port_2[PhyRoleConsts.CONSTANT_ROLE][ConfState.OPERATIONAL], default_port_2[PhyRoleConsts.CONSTANT_ROLE][ConfState.APPLIED])
            ]
        )

import pytest

from ngts.nvos_constants.constants_nvos import ApiType, DatabaseConst, PtpConsts
from ngts.nvos_tools.infra.DatabaseTool import DatabaseTool
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.RegisterTool import RegisterTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_configure_ptp_state(engines, devices, test_api):
    """
    Validate configuring feature state by using the fae commands:
    - Validate show system ptp command
    - Validate set system ptp tc <enabled|disabled> command
    - Validate unset system ptp tc command

    Test flow:
    1. Verify unset system ptp command
    2. Verify set system ptp tc enabled command
    3. Verify set system ptp tc disabled command
    4. Verify set system ptp tc enabled command
    5. Verify unset system ptp command
    6. Verify tc-state persist disabled after reboot
    """
    TestToolkit.tested_api = test_api
    engines_dut = engines.dut
    system = System()

    try:
        # Verify unset system ptp tc
        unset_and_verify_ptp_state(system, engines_dut, devices)

        # Verify set system ptp tc enabled
        set_and_verify_ptp_state(system, engines_dut, devices, PtpConsts.TcState.ENABLED.value)

        # Verify set system ptp tc disabled
        set_and_verify_ptp_state(system, engines_dut, devices, PtpConsts.TcState.DISABLED.value)

        # Verify set system ptp tc enabled
        set_and_verify_ptp_state(system, engines_dut, devices, PtpConsts.TcState.ENABLED.value)

        # Verify unset system ptp tc
        unset_and_verify_ptp_state(system, engines_dut, devices)

        with allure.step("Perform system reboot"):
            system.reboot.action_reboot(params='force').verify_result()

        with allure.step("Verify tc-state persist disabled after reboot"):
            verify_ptp_state(system, engines_dut, devices, PtpConsts.TcState.DISABLED.value)
    finally:
        with allure.step("Set ptp tc-state to default"):
            system.ptp.unset(apply=True).verify_result()


@pytest.mark.system
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
def test_set_ptp_invalid_commands(test_api):
    """
    Check set ptp command with invalid param value.

    Test flow:
    1. nv set system ptp tc <invalid state>
    """

    TestToolkit.tested_api = test_api

    with allure.step("Validate set fae interface link lanes with invalid lanes"):
        System().ptp.set(op_param_name=PtpConsts.TC_STATE, op_param_value='invalid_state',
                         apply=True).verify_result(should_succeed=False)

# ----------------------------------------------


def parse_mtpcpc_register(mtpcpc_value):
    """
    @Summary:
        This function will parse the MTPCPC register value and return output dictionary.
    @param mtpcpc_value: The MTPCPC register value. for example:
        Sending access register...

        Field Name                     | Data
        ============================================
        lp_msb                         | 0x00000000
        local_port                     | 0x00000001
        pport                          | 0x00000000
        ptp_trap_en                    | 0x00000000
        ing_correction_message_type    | 0x0000070f
        egr_correction_message_type    | 0x0000070f
        num_domains                    | 0x00000000
        domain[3]                      | 0x00000000
        domain[2]                      | 0x00000000
        domain[1]                      | 0x00000000
        domain[0]                      | 0x00000000
        ============================================
    @return: PTP TC status dictionary:
        enabled: corr_msg_dict= { 'ing_correction_message_type': '0x0000070f',
                                  'egr_correction_message_type': '0x0000070f'} or
        disabled: corr_msg_dict= { 'ing_correction_message_type': '0x00000000',
                                   'egr_correction_message_type': '0x00000000'} or
        invalid: corr_msg_dict= { 'ing_correction_message_type': '0xffffffff',
                                  'egr_correction_message_type': '0xffffffff'}
    """
    corr_msg_dict = PtpConsts.DEFAULT_DICT
    mtpcpc_output_list = mtpcpc_value.split('\n')
    for out in mtpcpc_output_list:
        if PtpConsts.ING_CORRECTION_MSG_TYPE in out:
            corr_msg_dict[PtpConsts.ING_CORRECTION_MSG_TYPE] = out.split("| ")[-1]
        elif PtpConsts.EGR_CORRECTION_MSG_TYPE in out:
            corr_msg_dict[PtpConsts.EGR_CORRECTION_MSG_TYPE] = out.split("| ")[-1]
            break

    return corr_msg_dict


def verify_mtpcpc_register(engines_dut, devices, expected_state):
    """
    @Summary:
        This function will parse the MTPCPC register value and verify PTP TC state according to expected input:
        register tc state is 'enabled' in case:
            'ing_correction_message_type': '0x0000070f'
            'egr_correction_message_type': '0x0000070f'
        register tc state is 'disabled' in case:
            'ing_correction_message_type': '0xffffffff'
            'egr_correction_message_type': '0x00000000'
        register tc state is 'invalid' otherwise.
    @param engines_dut: engines.dut
    @param devices: devices
    @param expected_state: the expected ptp tc state value ('enabled'|'disabled')
    """
    corr_msg_dict = parse_mtpcpc_register(RegisterTool.get_mst_register_value(
        engines_dut, devices.dut.mst_dev_name[0], PtpConsts.MTPCPC_REGISTER, PtpConsts.MTPCPC_INDEXES))
    if (corr_msg_dict[PtpConsts.ING_CORRECTION_MSG_TYPE] == PtpConsts.REG_DISABLE_VALUE) and \
       (corr_msg_dict[PtpConsts.EGR_CORRECTION_MSG_TYPE] == PtpConsts.REG_DISABLE_VALUE):
        tc_state = PtpConsts.TcState.DISABLED.value
    elif (corr_msg_dict[PtpConsts.ING_CORRECTION_MSG_TYPE] == PtpConsts.REG_ENABLE_VALUE) and \
         (corr_msg_dict[PtpConsts.EGR_CORRECTION_MSG_TYPE] == PtpConsts.REG_ENABLE_VALUE):
        tc_state = PtpConsts.TcState.ENABLED.value
    else:
        tc_state = PtpConsts.TcState.INVALID.value
    assert tc_state == expected_state, f"mtpcpc register tc state is {tc_state} but expected {expected_state}"


def verify_ptp_in_database(engines_dut, expected_state):
    """
    @Summary:
        This function will parse the CONFIG_DB PTP_TABLE and verify TC state is according to the expected state input
    @param engines_dut: engines.dut
    @param expected_state: the expected ptp tc state value ('enabled'|'disabled')
    """
    output = DatabaseTool.sonic_db_cli_hgetall(engine=engines_dut, asic="", db_name=DatabaseConst.CONFIG_DB_NAME,
                                               table_name=PtpConsts.PTP_TABLE_TC)
    db_tc_state = list(output.replace('\'', '').split())[-1].replace('}', '')
    assert db_tc_state == expected_state, (
        f"tc state in CONFIG_DB PTP_TABLE is {db_tc_state} but expected {expected_state}"
    )


def verify_ptp_state(system, engines_dut, devices, expected_state):
    """
    @Summary:
        This function verify the expected tc state is successfully configured in:
        - nv show system ptp
        - MTPCPC register
        - CONFIG_DB PTP_TABLE
    @param system: system class
    @param engines_dut: engines.dut
    @param devices: devices
    @param expected_state: the expected ptp tc state value ('enabled'|'disabled')
    """
    with allure.step(f"Verify tc is {expected_state} in 'nv show system ptp' command"):
        stats_show = OutputParsingTool.parse_json_str_to_dictionary(system.ptp.show()).get_returned_value()
        assert stats_show[PtpConsts.TC_STATE] == expected_state, \
            f"tc state parameter is {stats_show[PtpConsts.TC_STATE]}, but expected to be {expected_state}"

    with allure.step("Verify tc-state in MTPCPC register"):
        verify_mtpcpc_register(engines_dut, devices, expected_state)

    with allure.step("Verify tc-state in CONFIG_DB PTP_TABLE"):
        verify_ptp_in_database(engines_dut, expected_state)


def set_and_verify_ptp_state(system, engines_dut, devices, state):
    """
    @Summary:
        This function config new ptp tc state and verify the value is successfully configured in:
        - nv show system ptp
        - MTPCPC register
        - CONFIG_DB PTP_TABLE
    @param system: system class
    @param engines_dut: engines.dut
    @param devices: devices
    @param state: the expected ptp tc state value ('enabled'|'disabled')
    """
    with allure.step(f"Set system ptp tc to {state}"):
        system.ptp.set(op_param_name=PtpConsts.TC_STATE, op_param_value=state, apply=True).verify_result()

    verify_ptp_state(system, engines_dut, devices, state)


def unset_and_verify_ptp_state(system, engines_dut, devices):
    """
    @Summary:
        This function unset ptp tc state and verify the value is successfully configured in:
        - nv show system ptp
        - MTPCPC register
        - CONFIG_DB PTP_TABLE
    @param system: system class
    @param engines_dut: engines.dut
    @param devices: devices
    """
    with allure.step(f"Verify unset system ptp tc command"):
        system.ptp.unset(apply=True).verify_result()

    verify_ptp_state(system, engines_dut, devices, PtpConsts.TcState.DISABLED.value)

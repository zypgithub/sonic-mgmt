import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.constants.constants import LinuxConsts
from ngts.nvos_constants.constants_nvos import NvosConst
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.system.clock.ClockConsts import ClockConsts
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(autouse=True)
def tpm_debug_prints(engines, check_tpm_ready_for_testing):
    debug_cmds = [
        'sudo tpm2 getcap properties-variable | grep TPM2_PT_LOCKOUT_COUNTER:',
        "sudo tpm2_getcap properties-fixed | awk '/TPM2_PT_TOTAL_COMMANDS/,/raw:/ {print}'"
    ]

    with allure.step('debug prints before test case'):
        attachment = '\n'.join([f'$ {cmd}\n{engines.dut.run_cmd(cmd)}\n' for cmd in debug_cmds])
        allure.orig_allure.attach(attachment, 'tpm_debug_prints_before_case', allure.orig_allure.attachment_type.TEXT)
    yield
    with allure.step('debug prints after test case'):
        attachment = '\n'.join([f'$ {cmd}\n{engines.dut.run_cmd(cmd)}\n' for cmd in debug_cmds])
        allure.orig_allure.attach(attachment, 'tpm_debug_prints_after_case', allure.orig_allure.attachment_type.TEXT)


@pytest.fixture(autouse=True)
def verify_tpm_lockout_counter_is_zero(engines, check_tpm_ready_for_testing):
    tpm_tool = TpmTool(engines.dut)
    with allure.step('verify that tpm lockout counter is zeroed'):
        is_counter_cleared, counter_val = tpm_tool.is_tpm_lockout_counter_cleared()
        if not is_counter_cleared:
            with allure.step(f'TPM lockout counter is not zeroed - {counter_val}'):
                tpm_tool.clear_tpm_lockout_counter()
                pytest.fail(f'TPM lockout counter is not zeroed - {counter_val}')
    yield
    with allure.step('verify that tpm lockout counter is zeroed'):
        is_counter_cleared, counter_val = tpm_tool.is_tpm_lockout_counter_cleared()
        if not is_counter_cleared:
            with allure.step(f'TPM lockout counter is not zeroed - {counter_val}'):
                tpm_tool.clear_tpm_lockout_counter()
                pytest.fail(f'TPM lockout counter is not zeroed - {counter_val}')


@pytest.fixture(scope='session', autouse=True)
def check_tpm_ready_for_testing(engines):
    tpm_tool = TpmTool(engines.dut)
    if not tpm_tool.is_tpm_attestation_ready():
        pytest.skip('TPM is not ready for testing on current setup')
    assert tpm_tool.is_host_tpm_dir_exists(), f'TPM dir /host/tpm does not exist. failing the test'


@pytest.fixture(scope='session')
def remote_engine(engines, check_tpm_ready_for_testing):
    with allure.step('check sonic-mgmt is reachable'):
        sonic_mgmt_engine = engines[NvosConst.SONIC_MGMT]
        sonic_mgmt_engine.run_cmd('')
    return sonic_mgmt_engine


@pytest.fixture(scope='session', autouse=True)
def clear_tpm_dir(engines, check_tpm_ready_for_testing):
    tpm_tool = TpmTool(engines.dut)
    tpm_tool.remove_quote_files_from_tpm_dir()
    yield
    tpm_tool.remove_quote_files_from_tpm_dir()


@pytest.fixture()
def save_local_timezone(engines):
    with allure.step(f'set local timezone to {LinuxConsts.JERUSALEM_TIMEZONE}'):
        System().datetime.set(ClockConsts.TIMEZONE, LinuxConsts.JERUSALEM_TIMEZONE).verify_result()
    with allure.step('save configurations'):
        NvueGeneralCli.save_config(engines.dut)

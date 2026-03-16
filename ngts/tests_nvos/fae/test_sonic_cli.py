import logging
import pytest

from infra.tools.connection_tools.proxy_ssh_engine import ProxySshEngine
from ngts.nvos_constants.constants_nvos import ApiType, ActionConsts
from ngts.nvos_tools.infra.Fae import Fae
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit

logger = logging.getLogger()


@pytest.mark.simx
def test_sonic_cli_disabled(engines):
    """
        Check sonic_cli is unresponsive
        Fae sonic_cli action should be disabled
    """
    switch: ProxySshEngine = engines.dut
    sonic_cmd = 'show clock'

    with allure.step("Check sonic_cli is not responsive"):
        output = check_cmd_for_error(switch, sonic_cmd, should_fail=True)
        return output


@pytest.mark.simx
@pytest.mark.parametrize('state', [ActionConsts.ENABLE, ActionConsts.DISABLE])
def test_change_sonic_cli_state(engines, random_api, state):
    """
        1. Disable sonic_cli through action
        2. Check sonic_cli is unresponsive
    """
    switch: ProxySshEngine = engines.dut
    sonic_cmd = 'show clock'
    fae = Fae()

    with allure.step(f"{state} sonic_cli"):
        fae.sonic_cli.action_general(state).verify_result()

    with allure.step(f"Check sonic_cli is {state}d"):
        output = check_cmd_for_error(switch, sonic_cmd, state == ActionConsts.DISABLE)
        logger.info(f"sonic-cli {sonic_cmd}: {output}")
        return output


def check_cmd_for_error(engine, cmd, should_fail):
    output = engine.run_cmd(cmd)
    exit_code_cmd = "echo $?"
    exit_code = engine.run_cmd(exit_code_cmd)
    # Workaround to get only the exit code as number
    exit_code = int(exit_code.split('\n')[-1])
    logger.info(f"The resulted error code: {exit_code}")
    if should_fail:
        assert exit_code != 0, f'{cmd} should fail but got {output}'
    else:
        assert exit_code == 0, f'{cmd} should succeed but got {output} with {exit_code}'
    return output

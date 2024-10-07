import pytest

from infra.tools.connection_tools.linux_ssh_engine import LinuxSshEngine
from ngts.nvos_tools.infra.TpmTool import TpmTool
from ngts.nvos_tools.system.System import System
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='function')
def sed_default_password(engines):
    switch: LinuxSshEngine = engines.dut
    tpm_tool = TpmTool(switch)
    with allure.step("Get SED password from tpm"):
        sed_password: str = tpm_tool.get_sed_password_primary_bank().strip()
    try:
        yield sed_password
    finally:
        with allure.step(f"Set default SED password {sed_password}"):
            system = System()
            system.security.action_change_sed_password(sed_password)

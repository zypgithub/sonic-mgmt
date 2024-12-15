import pytest
import logging
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.ib.InterfaceConfiguration.MgmtPort import MgmtPort

logger = logging.getLogger()


@pytest.fixture(scope='function', autouse=True)
def acl_cleanup(engines):
    """
    clean ACL configurations
    """
    yield
    with allure.step("ACL cleanup"):
        try:
            Acl().unset()
            MgmtPort('').interface.unset(apply=True, ask_for_confirmation=True)
        except ValueError as e:
            if 'Unable to find prompt' in str(e):
                logger.info("Killing SSH session (which was terminated by the ACL rule change)")
                engines.dut.disconnect()
            else:
                raise

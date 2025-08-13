import pytest
import logging

from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.acl.acl import Acl
from ngts.nvos_tools.ib.InterfaceConfiguration.Port import Port

logger = logging.getLogger()


@pytest.fixture(scope='function')
def apply_default_config(engines):
    acl_cleanup(engines)


@pytest.fixture(scope='function', autouse=True)
def cleanup(engines):
    """
    clean ACL configurations
    """
    yield
    acl_cleanup(engines)


def acl_cleanup(engines):
    """
    clean ACL configurations
    """
    with allure.step("ACL cleanup"):
        try:
            Acl().unset()
            Port('').interface.unset(apply=True, ask_for_confirmation=True)
        except ValueError as e:
            if 'Unable to find prompt' in str(e):
                pass  # the connection died because of the rule-change. we do engine.disconnect() anyway.
            else:
                raise

        logger.info("Killing SSH session (which was terminated by the ACL rule change)")
        engines.dut.disconnect()

import pytest
import logging

logger = logging.getLogger()


@pytest.fixture(scope='session', autouse=True)
def get_els_list(engines, devices):
    els_list = devices.dut.els_list

    if not els_list:
        pytest.skip("No ELS transceivers found in the system")

    return els_list

import pytest

from ngts.nvos_tools.infra.Fae import Fae
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='session', autouse=True)
def erots(devices):
    fae = Fae()
    fae.platform.firmware.create_erot_components(devices.dut)
    return fae.platform.firmware.erot_id


@pytest.fixture()
def clear_erot_files(erots):
    for name, component in erots.items():
        with allure.step(f'delete fetched firmware image files for {name}'):
            component.files.delete_all_existing_files()

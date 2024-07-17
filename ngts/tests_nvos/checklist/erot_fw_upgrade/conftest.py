import pytest

from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure


@pytest.fixture(scope='module', autouse=True)
def clear_files_non_fae():
    platform = Platform()
    with allure.step('delete fetched firmware image files'):
        files = platform.firmware.erot.files.get_files()
        platform.firmware.erot.files.delete_files(files_to_delete=files)


@pytest.fixture(scope='module', autouse=True)
def erots(devices):
    fae = Fae()
    fae.platform.firmware.create_erot_components(devices.dut)
    return fae.platform.firmware.erots


@pytest.fixture(scope='module', autouse=True)
def clear_files_fae(erots):
    for name, component in erots.itmes():
        with allure.step(f'delete fetched firmware image files of {name}'):
            files = component.files.get_files()
            component.files.delete_files(files_to_delete=files)
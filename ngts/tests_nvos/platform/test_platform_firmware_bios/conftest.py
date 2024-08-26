import pytest

from ngts.nvos_tools.infra.ConnectionTool import ConnectionTool
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.system.System import System
from ngts.tests_nvos.platform.test_platform_firmware_bios.helpers import *


@pytest.fixture(scope='module', autouse=True)
def clear_files():
    yield
    fae = Fae()
    system = System()
    with allure.step('delete fetched firmware image files'):
        files = fae.platform.firmware.bios.show_files_as_list()
        for file in files:
            fae.platform.firmware.bios.action_delete(file).verify_result()

    with allure.step('delete fetched system image files'):
        files = system.image.files.get_files()
        system.image.files.delete_files(files_to_delete=files)


@pytest.fixture(scope='function')
def get_image_data_and_fetch_image(target_version_realpath):
    system = System()
    original_image_partition = get_image_data(system)

    with allure.step(f"Fetch image {target_version_realpath}"):
        player = TestToolkit.engines['sonic_mgmt']
        system.image.action_fetch(ImageConsts.SCP_PATH_SERVER.format(username=player.username, password=player.password,
                                                                     ip=player.ip, path=target_version_realpath))
    image_name = target_version_realpath.split("/")[-1]
    return original_image_partition, image_name

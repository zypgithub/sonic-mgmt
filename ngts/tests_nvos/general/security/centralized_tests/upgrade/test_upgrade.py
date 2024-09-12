from typing import Dict, Generator

import pytest

from ngts.cli_wrappers.nvue.nvue_general_clis import NvueGeneralCli
from ngts.nvos_constants.constants_nvos import ImageConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.tests_nvos.system.factory_reset.helpers import *
from ngts.tests_nvos.system.gnmi.helpers import get_scp_player
from ngts.tools.test_utils import allure_utils as allure

UPGRADE_CHECKERS: Dict[str, Generator[None, None, None]] = {
}


@pytest.mark.security
@pytest.mark.upgrade
def test_downgrade_upgrade(base_version_realpath, target_version_realpath, devices, engines, topology_obj):
    """
    Validate upgrade scenario
    """

    checkers = UPGRADE_CHECKERS
    if not checkers:
        pytest.skip('test skipped: no checkers registered for this test')
    logging.info(f'checkers names for upgrade: {list(checkers.keys())}')

    system = System()

    target_version_name = target_version_realpath.split("/")[-1]

    assert is_cur_version_as_expected(system,
                                      target_version_realpath), f'cur running version is not as given target version: {target_version_name}'

    need_recovery = False

    try:
        with allure.step(f'upgrade test'):
            with allure.step(f'downgrade to base version: {base_version_realpath}'):
                with allure.step('install base version'):
                    fetch_install_img(system, base_version_realpath, engines)
                    need_recovery = True
                with allure.step('uninstall orig version'):
                    system.image.action_uninstall('force')

            with allure.independent_step('pre upgrade steps'):
                for name, checker in checkers.items():
                    with allure.independent_step(name):
                        next(checker)

            with allure.step(f"Run upgrade: {target_version_name}"):
                fetch_install_img(system, target_version_realpath, engines)

            with allure.step('post upgrade steps'):
                for name, checker in checkers.items():
                    with allure.independent_step(name):
                        next(checker)

    finally:
        with allure.step('upgrade test cleanup'):
            if need_recovery:
                if is_cur_version_as_expected(system, target_version_realpath):
                    with allure.step('uninstall base version'):
                        system.image.action_uninstall('force')
                else:
                    with allure.step('recovery: manufacture to target (orig) version'):
                        NvueGeneralCli(engines.dut, devices.dut).install_image_via_onie(topology_obj,
                                                                                        target_version_realpath)
            with allure.step('delete fetched images'):
                system.image.files.delete_all_existing_files()


def is_cur_version_as_expected(system: System, expected_version: str) -> bool:
    expected_version = expected_version.split('/')[-1].replace('.bin', '').replace('arm64-', '').replace('amd64-', '')
    out = OutputParsingTool.parse_json_str_to_dictionary(system.version.show()).get_returned_value()
    cur_version = out['image']
    with allure.step(f'check if {expected_version} (orig) == {cur_version} (cur)'):
        return expected_version == cur_version


def fetch_install_img(system: System, img_path: str, engines):
    img_name = img_path.split("/")[-1]
    with allure.step(f"fetch image: {img_name}"):
        scp_player = get_scp_player(engines)
        system.image.action_fetch(
            ImageConsts.SCP_PATH_SERVER.format(username=scp_player.username, password=scp_player.password,
                                               ip=scp_player.ip, path=img_path))
    with allure.step(f'install image: {img_name}'):
        system.image.files.file_name[img_name].action_file_install_with_reboot()
    with allure.step('disconnect dut engine'):
        engines.dut.disconnect()

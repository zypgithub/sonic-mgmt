import random

import pytest

from ngts.tests_nvos.checklist.erot_fw_upgrade.BaseFWUpgradeTest import BaseFWUpgradeTest
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.Fae import Fae
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tools.test_utils import allure_utils as allure


@pytest.mark.erot
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_erot_upgrade_all(engines, devices, topology_obj, test_api, test_name, clear_files_non_fae):
    """
    Test 'nv {show | fetch | install | delete} platform firmware EROT
    Bad BMC erot fw - hardware limitation, therefore removing 'ERoT_BMC_0' from install verification
    This function tests the process of fetching, installing, and verifying firmware images on a switch,
    The test includes steps for fetching previous and current firmware images, installing them,
    and verifying the installation on all relevant firmware components.


    Steps:
    1. Fetch the previous firmware image and verify its presence.
    2. Set the firmware source to custom.
    3. Install the previous firmware image and recover the device with a remote reboot.
    4. Verify the installation on all firmware components except 'ERoT_BMC_0'.
    5. Fetch the current firmware image and verify its presence.
    6. Install the current firmware image and recover the device with a remote reboot.
    7. Verify the installation on all firmware components except 'ERoT_BMC_0'.
    8. Finally, reset the firmware source to default and delete the firmware image files.

    """
    with allure.step('Create Test and system objects'):
        platform = Platform()
        test = BaseFWUpgradeTest(firmware_component=platform.firmware.erot)

    with allure.step(f"Fetch, install and assert prev & curr versions (through {test_api})"):
        test.test(engines=engines, switch=devices.dut, topology_obj=topology_obj, test_api=test_api)


@pytest.mark.erot
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_erot_upgrade_all_badflow(engines, devices, topology_obj, test_api, test_name):
    """
    Test bad flow scenarios for platform firmware EROT.

    Steps:
    1. Fetch the previous firmware image.
    2. Verify the fetched image file exists.
    3. Delete the fetched image file.
    4. Attempt to delete the now non-existent image file (should fail).
    5. Attempt to install the now non-existent image file (should fail).

    """
    with allure.step('Create Test and system objects'):
        platform = Platform()
        test = BaseFWUpgradeTest(firmware_component=platform.firmware.erot)

    with allure.step(f"Bad flow (through {test_api})"):
        test.test_badflow(engines=engines, switch=devices.dut, topology_obj=topology_obj,
                          test_api=test_api, force=False)


@pytest.mark.erot
@pytest.mark.parametrize('test_api', random.sample(ApiType.ALL_TYPES, 1))
def test_erot_upgrade_fae(engines, devices, topology_obj, test_api, test_name, clear_files_fae):
    """
    Test 'nv {show | fetch | install | delete} fae platform firmware <EROT-Component>
    Bad BMC erot fw - hardware limitation, therefore removing 'ERoT_BMC_0' from install verification
    This function tests the process of fetching, installing, and verifying firmware images on a switch,
    The test includes steps for fetching previous and current firmware images, installing them,
    and verifying the installation on all relevant firmware components.


    Steps:
    1. Fetch the previous firmware image and verify its presence.
    2. Set the firmware source to custom.
    3. Install the previous firmware image and recover the device with a remote reboot.
    4. Verify the installation on all firmware components except 'ERoT_BMC_0'.
    5. Fetch the current firmware image and verify its presence.
    6. Install the current firmware image and recover the device with a remote reboot.
    7. Verify the installation on all firmware components except 'ERoT_BMC_0'.
    8. Finally, reset the firmware source to default and delete the firmware image files.

    """
    with allure.step('Create Test and system objects'):
        fae = Fae()
        fae.platform.firmware.create_erot_components(devices.dut)
        test = BaseFWUpgradeTest(firmware_component=fae.platform.firmware.erots)

    with allure.step(f"Fetch, install and assert prev & curr versions (through {test_api})"):
        test.test_list(engines=engines, switch=devices.dut, topology_obj=topology_obj, test_api=test_api, fae=fae)


@pytest.mark.erot
@pytest.mark.parametrize('test_api', [ApiType.NVUE])
def test_erot_upgrade_fae_badlflow(engines, devices, topology_obj, test_api, test_name, erots):
    """
    Test bad flow scenarios for fae platform firmware <EROT-COMPONENT>, for all erots in board.

    Steps:
    1. Fetch the previous firmware image.
    2. Verify the fetched image file exists.
    3. Delete the fetched image file.
    4. Attempt to delete the now non-existent image file (should fail).
    5. Attempt to install the now non-existent image file (should fail).

    """
    for name, component in erots.items():
        with allure.step(f"Bad flow on {name} (through {test_api})"):
            test = BaseFWUpgradeTest(firmware_component=component)
            test.test_badflow(engines=engines, switch=devices.dut, topology_obj=topology_obj,
                              test_api=test_api, force=True)

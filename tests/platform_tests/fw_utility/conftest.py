import io
import os
import yaml
import random
import pytest

from fwutil_helper import PLATFORM_COMP_PATH_TEMPLATE
from fwutil_helper import OnieComponent, SsdComponent, BiosComponent, CpldComponent
from fwutil_helper import set_default_boot, set_next_boot, reboot_to_image, generate_components_file

logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption("--config_file", action="store", default=None, help="name of configuration file (per each vendor)")
    parser.addoption("--binaries_path", action="store", default=None, help="path to binaries files")
    parser.addoption("--second_image_path", action="store", default=None, help="path to second image to be installed if there is no image available")


@pytest.fixture(scope='module')
def platform_components(request, duthost):
    """
    Fixture that returns platform components list
    according to the given config file.
    """
    config_file = request.config.getoption("--config_file")
    # config file contains platform string identifier and components separated by ','.
    # e.g.: x86_64-mlnx_msn2010-r0: BIOS,CPLD
    config_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), config_file)

    with io.open(config_file_path, 'rb') as config_file:
        platform_dict = yaml.safe_load(config_file)
        platform_type = duthost.facts['platform']
        components = platform_dict[platform_type]

    yield components.split(',')


@pytest.fixture(scope='function')
def component_object(platform_components):
    """
    Fixture that returns arbitrary firmware component object
    """
    comp_name = random.choice(platform_components)

    pattern = re.compile('^[A-Za-z]+')
    result = pattern.search(comp_name.capitalize())

    if not result:
        pytes.fail("Failed to detect component type: name={}".format(comp_name))

    yield globals()[result.group(0).lower().capitalize() + 'Component'](comp_name)


@pytest.fixture(scope='function')
def component_firmware(request, duthost, component_object):
    """
    Fixture that returns component firmware paths
    """
    binaries_path = request.config.getoption('--binaries_path')

    if not binaries_path:
        pytest.fail("Missing arguments: --binaries_path")

    yield component_object.process_versions(duthost, binaries_path, request.param)


@pytest.fixture(scope='function')
def skip_if_no_update(component_object, component_firmware):
    """
    Fixture that skips test execution in case no firmware updates: previous = latest
    """
    if component_firmware['latest_version'] == component_firmware['previous_version']:
        if component_firmware['is_latest_installed']:
            pytest.skip("Latest {} firmware is already installed".format(component_object.get_name()))


@pytest.fixture(scope='function')
def setup_images(request, duthost, component_firmware):
    """"
    Setup part of 'update from next image test' case.
    Backup both image files and generate new json files
    """
    set_default_boot(request)
    set_next_boot(request)

    image_info = duthost.image_facts()['ansible_facts']['ansible_image_facts']
    current_image = image_info['current']
    next_image = image_info['next']

    logger.info("Configure SONiC images (setup): current={}, next={}".format(current_image, next_image))

    hostname = duthost.hostname
    platform_type = duthost.facts['platform']

    platform_comp_path = PLATFORM_COMP_PATH_TEMPLATE.format(platform_type)
    backup_path = tempfile.mkdtemp(prefix='json-')

    # backup current image platform file
    current_backup_path = os.path.join(backup_path, 'current_platform_component_backup.json')
    msg = "Fetch 'platform_components.json' from {}: remote_path={}, local_path={}"
    logger.info(msg.format(hostname, platform_comp_path, current_backup_path))
    duthost.fetch(src=platform_comp_path, dest=current_backup_path, flat='yes')

    # reboot to next image
    logger.info("Reboot to next SONiC image: version={}".format(next_image))
    reboot_to_image(request, next_image)

    # backup next image platform file
    next_backup_path = os.path.join(backup_path, 'next_platform_component_backup.json')
    msg = "Fetch 'platform_components.json' from {}: remote_path={}, local_path={}"
    logger.info(msg.format(hostname, platform_comp_path, next_backup_path))
    duthost.fetch(src=platform_comp_path, dest=next_backup_path, flat='yes')

    # generate component file for the next image
    fw_path = component_firmware['latest_firmware']
    remote_fw_path = os.path.join('/home/admin', os.path.basename(fw_path))
    fw_version = component_firmware['latest_version']
    generate_components_file(request, remote_fw_path, fw_version)

    # copy fw to dut (next image)
    msg = "Copy firmware to {}: local_path={}, remote_path={}"
    logger.info(msg.format(hostname, fw_path, remote_fw_path))
    duthost.copy(src=fw_path, dest=remote_fw_path)

    # reboot to first image
    logger.info("Reboot to current SONiC image: version={}".format(current_image))
    reboot_to_image(request, current_image)

    yield

    new_image_info = duthost.image_facts()['ansible_facts']['ansible_image_facts']
    new_current_image = new_image_info['current']
    new_next_image = new_image_info['next']

    logger.info("Configure SONiC images (teardown): current={}, next={}".format(new_current_image, new_next_image))

    if new_current_image == next_image:
        logger.info("Remove firmware from {}: remote_path={}".format(hostname, remote_fw_path))
        duthost.file(path=remote_fw_path, state='absent')

        msg = "Copy 'platform_components.json' to {}: local_path={}, remote_path={}"
        logger.info(msg.format(hostname, next_backup_path, platform_comp_path))
        duthost.copy(src=next_backup_path, dest=platform_comp_path)

        logger.info("Reboot to current SONiC image: version={}".format(current_image))
        reboot_to_image(request, current_image)

        msg = "Copy 'platform_components.json' to {}: local_path={}, remote_path={}"
        logger.info(msg.format(hostname, current_backup_path, platform_comp_path))
        duthost.copy(src=current_backup_path, dest=platform_comp_path)
    else:
        msg = "Copy 'platform_components.json' to {}: local_path={}, remote_path={}"
        logger.info(msg.format(hostname, current_backup_path, platform_comp_path))
        duthost.copy(src=current_backup_path, dest=platform_comp_path)

        logger.info("Reboot to next SONiC image: version={}".format(next_image))
        reboot_to_image(request, next_image)

        logger.info("Remove firmware from {}: remote_path={}".format(hostname, remote_fw_path))
        duthost.file(path=remote_fw_path, state='absent')

        msg = "Copy 'platform_components.json' to {}: local_path={}, remote_path={}"
        logger.info(msg.format(hostname, next_backup_path, platform_comp_path))
        duthost.copy(src=next_backup_path, dest=platform_comp_path)

        logger.info("Reboot to current SONiC image: version={}".format(current_image))
        reboot_to_image(request, current_image)

    logger.info("Remove 'platform_components.json' backups from localhost: path={}".format(backup_path))
    os.remove(current_backup_path)
    os.remove(next_backup_path)
    os.rmdir(backup_path)

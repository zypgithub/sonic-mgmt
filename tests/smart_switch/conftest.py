import logging
import pytest
import os


logger = logging.getLogger(__name__)
SMARTSWITCH_PLATFORMS = ['x86_64-nvidia_sn4280-r0']


@pytest.fixture(scope="session", autouse=True)
def platform(duthost):
    return duthost.facts["platform"]


@pytest.fixture(scope="session", autouse=True)
def skip_unsupported_platform(duthost, platform):
    if platform not in SMARTSWITCH_PLATFORMS and 'nvda_bf' not in platform:
        pytest.skip("BYO is only supported on DPU or smartswitch platforms")


@pytest.fixture(scope="session")
def copy_proxy_ssh(duthost, platform):
    user = os.getenv('SONIC_SWITCH_USER')
    password = os.getenv('SONIC_SWITCH_PASSWORD')
    duthost.shell(f'echo {user} >> SONIC_USER')
    duthost.shell(f'echo {password} >> SONIC_PASSWORD')
    result = duthost.shell('ls /usr/local/bin/proxy_ssh.py', module_ignore_errors=True)
    if result['rc'] == 2:
        duthost.copy(src='smart_switch/proxy_ssh.py',
                     dest='/usr/local/bin/proxy_ssh.py')
        duthost.shell("sudo chmod 777 /usr/local/bin/proxy_ssh.py")
        logger.info("The proxy_ssh.py is copied to /usr/local/bin/proxy_ssh.py")

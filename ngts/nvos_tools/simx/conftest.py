import logging
import pytest

logger = logging.getLogger()


def pytest_addoption(parser):
    """
    Parse pytest options for simx tests
    :param parser: pytest builtin
    """
    logger.info('Parsing simx pytest options')
    parser.addoption('--use_bin_image', action='store_true', default=False,
                     help='Provide to use bin image instead of disk image')
    parser.addoption('--use_master_script', action='store_true', default=False,
                     help='Use master script instead of release script')
    parser.addoption('--is_regression_run', action='store_true', default=False,
                     help='Use regression run instead of ci run')
    parser.addoption('--chip', type=str, action='store', default=None, help='Chip Type, e.g. QTM4/QTM5/...')
    parser.addoption('--platform-from-noga', action='store_true', default=False, help='Start SimX with platform '
                                                                                      'information from NOGA')
    parser.addoption('--chipsim-version', type=str, action='store', default=None, help='ChipSim version, e.g. master-1.3.149')
    parser.addoption('--custom-flags', type=str, action='store', default=None, help='Custom flags for chipsim')
    parser.addoption('--chipsim-script-branch', type=str, action='store', default=None,
                     help='Override the chipsim branch/release name for regression runs, e.g. 25-03-0400')


@pytest.fixture(scope="session", autouse=True)
def is_regression_run(request):
    return request.config.getoption('--is_regression_run')


@pytest.fixture(scope="session", autouse=True)
def use_bin_image(request):
    return request.config.getoption('--use_bin_image')


@pytest.fixture(scope="session", autouse=True)
def use_master_script(request):
    return request.config.getoption('--use_master_script')


@pytest.fixture(scope="session", autouse=True)
def chip(request):
    return request.config.getoption('--chip')


@pytest.fixture(scope="session", autouse=True)
def platform(request, topology_obj):
    if request.config.getoption('--platform-from-noga'):
        return topology_obj.players['dut']['attributes'].noga_query_data['attributes']['Specific']['SUB_TYPE']
    return ''


@pytest.fixture(scope="session", autouse=True)
def chipsim_version(request):
    return request.config.getoption('--chipsim-version')


@pytest.fixture(scope="session", autouse=True)
def custom_flags(request):
    return request.config.getoption('--custom-flags')


@pytest.fixture(scope="session", autouse=True)
def chipsim_script_branch(request):
    return request.config.getoption('--chipsim-script-branch')

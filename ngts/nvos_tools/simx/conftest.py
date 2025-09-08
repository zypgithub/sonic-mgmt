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


@pytest.fixture(scope="session", autouse=True)
def is_regression_run(request):
    return request.config.getoption('--is_regression_run')


@pytest.fixture(scope="session", autouse=True)
def use_bin_image(request):
    return request.config.getoption('--use_bin_image')


@pytest.fixture(scope="session", autouse=True)
def use_master_script(request):
    return request.config.getoption('--use_master_script')

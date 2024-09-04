"""

conftest.py

Defines the methods and fixtures which will be used by pytest

"""

import pytest


def pytest_addoption(parser):
    """
    Parse pytest options
    :param parser: pytest builtin
    """
    parser.addoption('--onyx_image_url', action='store', required=False, default=None,
                     help='Provide onyx image url if upgrade of fanout needed,'
                          ' Example  http://fit69.mtl.labs.mlnx/mswg/release/sx_mlnx_os/lastrc_3_9_3000/X86_64/image-X86_64-3.9.3004-002.img')


@pytest.fixture(scope="module")
def onyx_image_url(request):
    """
    Method for getting base version from pytest arguments
    :param request: pytest builtin
    :return: onyx_image_url
    """
    return request.config.getoption('--onyx_image_url')

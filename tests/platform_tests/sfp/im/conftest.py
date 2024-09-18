import pytest

from tests.common.utilities import skip_release
from tests.platform_tests.sfp.im.helpers import im_supported, im_ms_sku, PLATFORM_GENERATION


@pytest.fixture(autouse=True, scope="module")
def check_image_version_support(duthost):
    """
    @summary: This fixture is for skip test in SONiC release
    @param: duthost: duthost fixture
    """
    skip_release(duthost, ["201911", "202012", "202205", "202305"])


@pytest.fixture(autouse=True, scope="module")
def check_platform_support(duthost):
    """
    @summary: This fixture is for skip test if case run not in specific platform
    @param: duthost: duthost fixture
    """
    if not im_supported(duthost):
        pytest.skip(f"Independent module feature supported only from spectrum 3 and above")


@pytest.fixture(autouse=True, scope="module")
def check_ms_sku(duthost):
    """
    @summary: This fixture is for skip test if case run not in specific platform
    @param: duthost: duthost fixture
    """
    if not im_ms_sku(duthost):
        pytest.skip(f"Independent module feature supported only at Microsoft SKU {PLATFORM_GENERATION}")

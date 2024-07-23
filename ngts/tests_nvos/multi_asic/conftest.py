import logging

import pytest

from ngts.nvos_tools.infra.RandomizationTool import RandomizationTool
from ngts.tools.test_utils import allure_utils as allure

logger = logging.getLogger()


@pytest.fixture
def random_asic() -> int:
    ret = RandomizationTool.select_random_asics().get_returned_value()[0]
    with allure.step(f"Test will be performed on randomly-chosen ASIC{ret}"):  # show chosen ASIC in allure
        pass
    return ret

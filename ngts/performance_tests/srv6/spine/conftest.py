import allure
import pytest
from ngts.constants.performance_constants import MRCConsts
from ngts.constants.constants import SonicConst
from ngts.helpers.performance.performance_setup_helpers import apply_test_configuration


@pytest.fixture(scope='class', autouse=True)
def conf_args(chip_type, players):
    sku = MRCConsts.HWSKU_BY_CHIP_TYPE[chip_type]["spine"]
    conf_args = {
        "is_ipv6": True,
        "packet_size": 4096,
        "scenario": "srv6",
        "speed": SonicConst.HWSKU_DOWNSTREAM_PORTS_SPEED[sku],
        "hwsku": sku,
        "dut_mac": players['dut']['cli'].performance.get_mac(),
        "dut": "spine",
        "chip_type": chip_type
    }
    return conf_args


@pytest.fixture(scope='class', autouse=True)
def basic_setup_configuration(players, conf_args):
    with allure.step("Apply Test configuration on all Players"):
        apply_test_configuration(players, scenario=conf_args["scenario"], conf_args=conf_args)
    yield

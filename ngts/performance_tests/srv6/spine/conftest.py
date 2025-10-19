import allure
import pytest
from ngts.constants.performance_constants import MRCConsts, Cl_Consts
from ngts.constants.constants import SonicConst
from ngts.helpers.performance.performance_setup_helpers import apply_test_configuration, restore_basic_configuration, save_base_configuration


@pytest.fixture(scope='class', autouse=True)
def conf_args(chip_type, players):
    sku = MRCConsts.HWSKU_BY_CHIP_TYPE[chip_type]["spine"]
    is_cumulus = players["dut"].get("is_cumulus", False)
    conf_args = {
        "is_ipv6": True,
        "packet_size": 4096,
        "scenario": "srv6",
        "hwsku": sku,
        "split_left": Cl_Consts.SRV6_SPLIT_LEFT_BY_CHIP_TYPE[chip_type],
        "split_right": Cl_Consts.SRV6_SPLIT_RIGHT_BY_CHIP_TYPE[chip_type],
        "dut_mac": players['dut']['cli'].performance.mac,
        "dut": "spine",
        "chip_type": chip_type,
        "split_left": Cl_Consts.SRV6_SPLIT_LEFT_BY_CHIP_TYPE[chip_type],
        "split_right": Cl_Consts.SRV6_SPLIT_RIGHT_BY_CHIP_TYPE[chip_type],
        "speed": Cl_Consts.SRV6_SPEED_BY_CHIP_TYPE[chip_type] if is_cumulus else SonicConst.HWSKU_DOWNSTREAM_PORTS_SPEED[sku]
    }
    return conf_args


@pytest.fixture(scope='class', autouse=True)
def basic_setup_configuration(players, conf_args):
    try:
        with allure.step('Save Players initial Configuration'):
            save_base_configuration(players)
        with allure.step("Apply Test configuration on all Players"):
            apply_test_configuration(players, scenario=conf_args["scenario"], conf_args=conf_args)
        yield
    except Exception as e:
        raise e
    finally:
        with allure.step('Restore Base Configuration on all Players'):
            restore_basic_configuration(players)
            pass

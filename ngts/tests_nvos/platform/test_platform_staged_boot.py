import logging
import pytest
import random

from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.constants import MINUTE
from ngts.tools.test_utils import allure_utils as allure
from ngts.nvos_tools.platform.Platform import Platform
from ngts.nvos_constants.constants_nvos import PlatformConsts
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.nvos_tools.infra.BmcTool import BmcTool
from ngts.tests_nvos.general.security.bmc.constants import BootPolicy

logger = logging.getLogger()
BOOT_POLICY_REDFISH_API_ENDPOINT_PATH = "/Systems/System_0/"


@pytest.mark.platform
@pytest.mark.bmc
@pytest.mark.parametrize('test_api', ApiType.ALL_TYPES)
@pytest.mark.timeout(MINUTE, func_only=True)
def test_show_set_platform_boot_policy(engines, devices, topology_obj, test_api, output_format):
    """
    in this case we will run show command and send curl GET request to BMC and validate both have default values

    :param engines:
    :param devices:
    :param test_api:
    :param output_format:
    :return:
    """
    TestToolkit.tested_api = test_api
    with allure.step("Create Platform object"):
        platform = Platform()

    with allure.step("get BMC ip address"):
        ip_addresses = BmcTool.get_bmc_ip_addresses(engines, topology_obj)
        get_ip_addresses = random.choice(list(ip_addresses.keys()))
        patch_ip_addresses = next(ip_add for ip_add in ip_addresses if ip_add != get_ip_addresses)

    with allure.step("Testing GET and PATCH"):
        with allure.independent_step("Run show command and send curl GET request to BMC and validate both have default "
                                     "values"):
            expected_output = {
                'boot-policy': "always-on",
                'timeout': 0,
                'last state': "on",
            }
            with allure.step("Test default values of nv show platform boot-policy"):
                with allure.step("run show command"):
                    show_output = OutputParsingTool.parse_show_output_to_dict(platform.boot_policy.show(
                        output_format=output_format), output_format=output_format,
                        field_name_dict=PlatformConsts.FW_FIELD_NAME_DICT).get_returned_value()

                validate_show_and_bmc_outputs(engine=engines.dut, show_output=show_output, expected_output=expected_output,
                                              ip_addresses=get_ip_addresses)

        with allure.independent_step("Run different curl PATCH requests to BMC and validate GET and show command will "
                                     "have same expected values"):

            expected_output = {
                'boot-policy': "always-off",
                'timeout': 300,
                'last state': "on",
            }

            with allure.step("Test nv show platform boot-policy after sending curl request to change the power policy"):

                with allure.step("change power policy using BMC"):
                    sec_delay = 300
                    new_values = {BootPolicy.POWER_RESTORE_POLICY: {BootPolicy.ALWAYS_OFF}, {BootPolicy.POWER_ON_DELAY_SECONDS}: {sec_delay}}
                    BmcTool.send_patch_request(engines.dut, patch_ip_addresses, BOOT_POLICY_REDFISH_API_ENDPOINT_PATH, new_values, expected_value="NEED TO UPDATE").verify_result()

                with allure.step("run show command"):
                    show_output = OutputParsingTool.parse_show_output_to_dict(platform.boot_policy.show(
                        output_format=output_format), output_format=output_format,
                        field_name_dict=PlatformConsts.FW_FIELD_NAME_DICT).get_returned_value()

                validate_show_and_bmc_outputs(engine=engines.dut, show_output=show_output, xpected_output=expected_output,
                                              ip_addresses=patch_ip_addresses)


def validate_show_and_bmc_outputs(engine, show_output, expected_output, bmc_ip_address):
    """

    :param engine:
    :param show_output:
    :param expected_output:
    :param bmc_ip_address:
    :return:
    """

    with allure.step(f"Validate the show output and BMC values both are: {expected_output}"):
        with allure.step("Get power policy from BMC"):
            curl_get_output = BmcTool.send_get_request(engine, bmc_ip_address, BOOT_POLICY_REDFISH_API_ENDPOINT_PATH).verify_result()

        with allure.step("compare both values"):
            ValidationTool.validate_set_equal(show_output, curl_get_output).verify_result()

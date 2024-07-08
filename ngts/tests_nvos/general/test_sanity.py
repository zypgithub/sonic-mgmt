import logging
import random

import pytest
import time
from ngts.tools.test_utils import allure_utils as allure
from ngts.tests_nvos.platform.test_platform import test_show_platform
from ngts.nvos_constants.constants_nvos import ApiType
from ngts.nvos_tools.system.System import System
from ngts.nvos_tools.platform.Platform import Platform
from ngts.tests_nvos.checklist.test_checklist_ipv6 import test_checklist_ipv6
from ngts.nvos_constants.constants_nvos import SystemConsts, HealthConsts
from ngts.nvos_tools.infra.OutputParsingTool import OutputParsingTool
from ngts.nvos_tools.infra.ValidationTool import ValidationTool
from ngts.tests_nvos.general.security.test_aaa_ldap.test_ldap_ci import test_ldap_auth_ci
from ngts.tests_nvos.general.security.security_test_tools.constants import AddressingType
from ngts.tests_nvos.general.security.tacacs.test_tacacs_ci import test_tacacs_auth
from ngts.tests_nvos.system.aaa.test_capability_functionality import test_capability_functionality
from ngts.nvos_tools.infra.NvosTestToolkit import TestToolkit
from ngts.tests_nvos.acl.test_acl_basic import test_show_acls

logger = logging.getLogger()


@pytest.mark.simx
@pytest.mark.nvos_chipsim_ci
@pytest.mark.nvos_ci
@pytest.mark.parametrize('addressing_type', [random.choice(AddressingType.ALL_TYPES)])
def test_ci_sanity(engines, topology_obj, addressing_type, request, devices):
    with allure.step("Test OpenApi"):
        test_show_platform(engines, ApiType.OPENAPI, devices)

    TestToolkit.tested_api = ApiType.NVUE

    with allure.step("Test ACL"):
        test_show_acls(engines, ApiType.NVUE)

    with allure.step("Test IPV6"):
        test_checklist_ipv6(engines)

    with allure.step("Test 'set' command"):
        system = System()
        new_pre_login_msg = "test_msg"
        system.message.set(op_param_name=SystemConsts.PRE_LOGIN_MESSAGE, op_param_value=f'"{new_pre_login_msg}"',
                           apply=True, dut_engine=engines.dut).verify_result()
        time.sleep(3)
        message_output = OutputParsingTool.parse_json_str_to_dictionary(system.message.show()).get_returned_value()
        ValidationTool.verify_field_value_in_output(message_output, SystemConsts.PRE_LOGIN_MESSAGE,
                                                    new_pre_login_msg).verify_result()
        system.message.unset(op_param=SystemConsts.PRE_LOGIN_MESSAGE, apply=True)

    with allure.step("Test action fetch"):
        platform = Platform()
        new_fw_file = "sec_issu_46_120_10011_dev_signed.bin"
        fw_path = f"{SystemConsts.GENERAL_TRANSCEIVER_FIRMWARE_FILES}/{new_fw_file}"
        player_engine = engines['sonic_mgmt']
        scp_path = 'scp://{}:{}@{}'.format(player_engine.username, player_engine.password, player_engine.ip)
        platform.firmware.transceiver.action_fetch(fw_path, base_url=scp_path).verify_result()
        with allure.step("Run the show command and verify that all expected files are correct"):
            platform.firmware.transceiver.files.verify_show_files_output(expected_files=[new_fw_file])

    with allure.step("Test security"):
        test_ldap_auth_ci(test_api=ApiType.NVUE, addressing_type=addressing_type, engines=engines,
                          topology_obj=topology_obj, request=request)
        test_tacacs_auth(test_api=ApiType.NVUE, addressing_type=addressing_type, engines=engines,
                         topology_obj=topology_obj, request=request)
        test_capability_functionality(engines)

    with allure.step("Test Health"):
        health_output = OutputParsingTool.parse_json_str_to_dictionary(system.health.show()).get_returned_value()
        ValidationTool.validate_all_values_exists_in_list([HealthConsts.STATUS, HealthConsts.STATUS_LED],
                                                          health_output.keys()).verify_result()
        system.validate_health_status(HealthConsts.OK)

    with allure.step("Show SNMP"):
        system_snmp_output = OutputParsingTool.parse_json_str_to_dictionary(system.snmp_server.show()) \
            .get_returned_value()

        with allure.step("Verify default values"):
            ValidationTool.validate_fields_values_in_output(SystemConsts.SNMP_OUTPUT_FIELDS,
                                                            SystemConsts.SNMP_DEFAULT_VALUES,
                                                            system_snmp_output).verify_result()
            logging.info("All expected values were found")
